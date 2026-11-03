import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.orm import load_only
from .db import Session, utcnow
from .models import Config, Job, ImageRecord, Repository, Snapshot, ImageLink, ImageResearch
from .github import GitHub, ServiceError, extract_repos, discovery_query
from .ocr import read_image
from .summary import build_summary, preserve_summary
from .config import settings
from .review import update_review_status

logger = logging.getLogger(__name__)
DEFAULT_RULE = {'enabled': True, 'days': 30, 'min_stars': 100, 'language': '', 'topic': '', 'limit': 100, 'hour': 9}


def enqueue(db, kind, payload):
    job = Job(id=str(uuid4()), kind=kind, payload=payload)
    db.add(job)
    return job.id


def stage(job_id, label):
    with Session.begin() as db:
        job = db.get(Job, job_id)
        job.stage = label


def upsert_repo(db, data, collected=False):
    repo = db.get(Repository, data['id'])
    if repo is None:
        repo = Repository(id=data['id'], full_name=data['full_name'])
        db.add(repo)
    repo.full_name = data['full_name']
    repo.description = data.get('description') or ''
    repo.language = data.get('language') or ''
    repo.stars = data.get('stargazers_count', 0)
    repo.forks = data.get('forks_count', 0)
    repo.archived = data.get('archived', False)
    repo.collected = collected or repo.collected or False
    repo.fetched_at = utcnow()
    metadata = dict(repo.metadata_json or {})
    metadata.update({k: data.get(k) for k in ('html_url', 'homepage', 'topics', 'license', 'created_at', 'pushed_at', 'open_issues_count', 'default_branch')})
    repo.metadata_json = metadata
    db.flush()
    date = datetime.now(timezone.utc).date().isoformat()
    snap = db.query(Snapshot).filter_by(repo_id=repo.id, date=date).first()
    if not snap:
        db.add(Snapshot(repo_id=repo.id, date=date, stars=repo.stars))
    return repo


def collect_repo(full_name, image_id=None, force=False, collected=True, web_sources=None, summarize=True):
    with Session() as db:
        existing = db.query(Repository).filter(Repository.full_name.ilike(full_name)).first()
        if force and web_sources is None and existing:
            web_sources = existing.metadata_json.get('web_evidence')
        fresh = existing and existing.readme and datetime.fromisoformat(existing.fetched_at) > datetime.now(timezone.utc) - timedelta(hours=24)
        if fresh and not force:
            repo_id = existing.id
        else:
            repo_id = None
    if repo_id is None:
        with GitHub() as api:
            data, readme, extra = api.bundle(full_name)
        if not summarize:
            summary = build_summary(data, readme, extra['readme_url'], allow_ai=False)
        else:
            summary = build_summary(data, readme, extra['readme_url']) if web_sources is None else build_summary(data, readme, extra['readme_url'], web_sources=web_sources)
        with Session.begin() as db:
            repo = upsert_repo(db, data, collected=collected)
            repo.readme = readme
            repo.metadata_json = {**repo.metadata_json, **extra}
            repo.summary = preserve_summary(repo.summary, summary)
            repo_id = repo.id
    elif web_sources is not None:
        with Session() as db:
            repo = db.get(Repository, repo_id)
            summary = build_summary({'full_name': repo.full_name, 'description': repo.description,
                                     'html_url': repo.metadata_json.get('html_url') or 'https://github.com/' + repo.full_name},
                                    repo.readme, repo.metadata_json.get('readme_url') or 'https://github.com/' + repo.full_name + '#readme',
                                    web_sources=web_sources)
        with Session.begin() as db:
            current = db.get(Repository, repo_id)
            current.summary = preserve_summary(current.summary, summary)
    with Session.begin() as db:
        from .library import save_organization
        save_organization(db, db.get(Repository, repo_id))
        if web_sources is not None:
            repo = db.get(Repository, repo_id)
            repo.metadata_json = {**repo.metadata_json, 'web_evidence': web_sources, 'web_researched_at': utcnow()}
        if collected:
            db.get(Repository, repo_id).collected = True
        if collected and image_id and not db.query(ImageLink).filter_by(image_id=image_id, repo_id=repo_id).first():
            db.add(ImageLink(image_id=image_id, repo_id=repo_id))
        if summarize and collected and all((settings.ai_base_url, settings.ai_api_key, settings.ai_model)):
            from .curation import enqueue_curation
            enqueue_curation(db, repo_id)
    return repo_id


def process_image(job):
    image_id = job.payload['image_id']
    with Session.begin() as db:
        image = db.get(ImageRecord, image_id)
        image.status, image.error = 'recognizing', ''
        path = image.path
        duplicate = db.query(ImageRecord).filter(ImageRecord.sha256 == image.sha256, ImageRecord.id != image.id, ImageRecord.status == 'completed').first()
        if duplicate:
            links = db.query(ImageLink).filter_by(image_id=duplicate.id).all()
            for link in links:
                if not db.query(ImageLink).filter_by(image_id=image_id, repo_id=link.repo_id).first():
                    db.add(ImageLink(image_id=image_id, repo_id=link.repo_id))
            image.text, image.candidates, image.status = duplicate.text, duplicate.candidates, 'completed'
            return
    stage(job.id, 'PaddleOCR 识别中（首次运行需下载模型）')
    text, regions = read_image(path)
    candidates = extract_repos(text)
    with Session.begin() as db:
        image = db.get(ImageRecord, image_id)
        image.text, image.candidates, image.regions = text, candidates, regions
        if settings.research_backend in ('computer_use', 'browser'):
            update_review_status(db, image)
            return
    stage(job.id, '核对 GitHub 仓库')
    if not candidates and text.strip():
        keywords = re_search_keywords(text)
        if keywords:
            with GitHub() as api:
                matches = api.search(keywords, limit=5)
            candidates = [{'full_name': r['full_name'], 'description': r.get('description'), 'stars': r['stargazers_count'], 'evidence': '关键词搜索候选，需要确认', 'auto': False} for r in matches['items']]
    for candidate in candidates:
        if candidate['auto']:
            try:
                collect_repo(candidate['full_name'], image_id)
                candidate['confirmed'] = True
            except ServiceError as exc:
                if exc.retryable:
                    raise
                candidate['auto'] = False
                candidate['error'] = str(exc)
    with Session.begin() as db:
        image = db.get(ImageRecord, image_id)
        image.candidates = candidates
        update_review_status(db, image)
        if not text.strip():
            image.error = '未识别到文字，请尝试更清晰的截图或手动填写链接'


def re_search_keywords(text):
    import re
    words = re.findall(r'[A-Za-z][A-Za-z0-9_-]{3,40}', text)
    ignore = {'github', 'https', 'readme', 'stars', 'forks', 'issues', 'license', 'code', 'pull', 'requests', 'settings', 'main', 'about'}
    unique = list(dict.fromkeys(w for w in words if w.lower() not in ignore))
    return ' '.join(unique[:3])


def discover(job):
    with Session() as db:
        config = db.get(Config, 'discovery_rule')
        rule = dict(config.value) if config else DEFAULT_RULE.copy()
    query = discovery_query(rule)
    stage(job.id, '搜索近期高星项目')
    with GitHub() as api:
        data = api.search(query, rule['limit'])
    ids = []
    with Session.begin() as db:
        for item in data['items']:
            ids.append(upsert_repo(db, item).id)
        result = {'repo_ids': ids, 'query': query, 'fetched_at': utcnow(), 'total_count': data['total_count'], 'incomplete': data.get('incomplete_results', False), 'limit': rule['limit']}
        config = db.get(Config, 'discovery_result')
        if config:
            config.value = result
        else:
            db.add(Config(key='discovery_result', value=result))


def run_job(job_id):
    with Session() as db:
        job = db.get(Job, job_id)
    try:
        if job.kind == 'recognize':
            process_image(job)
        elif job.kind == 'collect':
            stage(job.id, '获取 GitHub 资料并生成档案')
            collect_repo(job.payload['full_name'], job.payload.get('image_id'), job.payload.get('force', False))
            if job.payload.get('image_id'):
                with Session.begin() as db:
                    image = db.get(ImageRecord, job.payload['image_id'])
                    update_review_status(db, image)
                    image.error = ''
        elif job.kind == 'discovery':
            discover(job)
        elif job.kind in ('curate_project', 'curate_library'):
            from .curation import run_curation
            run_curation(job)
        elif job.kind in ('research', 'auto_confirm'):
            from .research import run_research
            run_research(job)
        elif job.kind == 'computer_use':
            from .computer_research import run_collection
            if job.payload.get('browser_result'):
                run_collection(job)
            else:
                from .computer_research import prepare
                with Session.begin() as db:
                    prepare(db, db.get(Job, job.id))
        with Session.begin() as db:
            current = db.get(Job, job_id)
            if current.status in ('waiting_browser', 'browser_running', 'cancelled', 'completed'):
                return
            current.status, current.stage, current.finished_at = 'completed', '处理完成', utcnow()
            if job.kind == 'recognize':
                maybe_research(db, job.payload['image_id'])
    except Exception as exc:
        logger.warning('Job %s failed: %s', job_id, type(exc).__name__)
        with Session.begin() as db:
            current = db.get(Job, job_id)
            retry = isinstance(exc, ServiceError) and exc.retryable and (getattr(exc, 'deferred', False) or current.attempts < 3)
            current.status = 'queued' if retry else 'failed'
            current.error = str(exc) if isinstance(exc, ServiceError) else f'处理失败（{type(exc).__name__}），请重试或检查服务端运行环境'
            current.stage = '等待每日额度恢复' if getattr(exc, 'deferred', False) else '等待重试' if retry else '处理失败'
            delay = getattr(exc, 'retry_after', 30)
            if not getattr(exc, 'deferred', False):
                delay = max(delay, 15 * 2 ** min(current.attempts, 8))
            current.available_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
            if job.kind == 'recognize':
                image = db.get(ImageRecord, job.payload['image_id'])
                image.status, image.error = ('queued' if retry else 'failed'), current.error
                if not retry:
                    maybe_research(db, image.id)
            elif job.kind in ('research', 'auto_confirm', 'computer_use') and job.payload.get('image_id'):
                row = db.get(ImageResearch, job.payload['image_id'])
                row.status, row.stage, row.error = current.status, current.stage, current.error
                row.updated_at = utcnow()
                image = db.get(ImageRecord, row.image_id)
                if retry:
                    image.status = 'researching'
                else:
                    update_review_status(db, image)
            elif job.kind == 'collect' and job.payload.get('image_id'):
                image = db.get(ImageRecord, job.payload['image_id'])
                if retry:
                    image.status = 'collecting'
                else:
                    update_review_status(db, image)
                image.error = current.error


def maybe_research(db, image_id):
    from .research import agent_available, enqueue_research
    image = db.get(ImageRecord, image_id)
    if settings.agent_auto_research and agent_available() and (image.status in ('needs_review', 'failed') or settings.agent_auto_confirm and image.status == 'completed'):
        db.flush()
        enqueue_research(db, image, auto_confirm=settings.agent_auto_confirm)


def schedule_daily():
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    with Session.begin() as db:
        config = db.get(Config, 'discovery_rule')
        rule = config.value if config else DEFAULT_RULE
        last = db.get(Config, 'last_schedule')
        today = now.date().isoformat()
        if rule['enabled'] and now.hour >= rule['hour'] and (not last or last.value['date'] != today):
            if not db.query(Job).filter(Job.kind == 'discovery', Job.status.in_(['queued', 'running'])).first():
                enqueue(db, 'discovery', {})
            if last:
                last.value = {'date': today}
            else:
                db.add(Config(key='last_schedule', value={'date': today}))


async def worker_loop():
    # One worker per deployment. DB-backed jobs survive restart; no in-memory queue.
    with Session.begin() as db:
        for job in db.query(Job).filter_by(status='running'):
            job.status, job.stage = 'queued', '从上次中断继续'
    tick = 0
    while True:
        try:
            if settings.schedule_enabled and tick % 30 == 0:
                await asyncio.to_thread(schedule_daily)
            if tick % 15 == 0:
                from .computer_research import reap_leases
                with Session.begin() as db:
                    reap_leases(db)
            tick += 1
            with Session.begin() as db:
                job = db.scalars(select(Job).options(load_only(Job.id, Job.status, Job.attempts)).where(Job.status == 'queued', Job.available_at <= utcnow()).order_by(Job.created_at).limit(1)).first()
                job_id = job.id if job else None
                if job:
                    job.status, job.attempts = 'running', job.attempts + 1
            if job_id:
                await asyncio.to_thread(run_job, job_id)
            else:
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Worker loop error')
            await asyncio.sleep(5)
