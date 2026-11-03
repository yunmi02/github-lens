"""Repair Chinese project knowledge from saved evidence, without web search."""
from .db import Session, utcnow
from .models import Repository, ProjectTrash, ProjectOrganization, Job
from .github import ServiceError
from .library import classify_batch, save_organization

ACTIVE = ('queued', 'running')


def enqueue_curation(db, repo_id=None):
    from .jobs import enqueue
    kind = 'curate_project' if repo_id else 'curate_library'
    for job in db.query(Job).filter(Job.kind.in_(('curate_project', 'curate_library')), Job.status.in_(ACTIVE)):
        if job.kind == kind and job.payload.get('repo_id') == repo_id:
            return job.id, False
        if repo_id and job.kind == 'curate_library':
            included = job.payload.get('repo_ids')
            repo = db.get(Repository, repo_id)
            if repo_id in (included or []) or included is None and repo and repo.collected:
                return job.id, False
    return enqueue(db, kind, {'repo_id': repo_id} if repo_id else {}), True


def curate_repo(repo_id):
    from .summary import build_summary, repair_overview_from_claims, needs_chinese_summary, summary_health
    with Session() as db:
        repo = db.get(Repository, repo_id)
        if not repo or db.get(ProjectTrash, repo_id):
            return False
        old = repair_overview_from_claims(repo.summary or {})
        data = {'full_name': repo.full_name, 'description': repo.description,
                'html_url': repo.metadata_json.get('html_url') or 'https://github.com/' + repo.full_name}
        readme, source = repo.readme, repo.metadata_json.get('readme_url') or data['html_url'] + '#readme'
        evidence = repo.metadata_json.get('web_evidence', [])
    summary = old
    generation_error = None
    if needs_chinese_summary(old) and (readme.strip() or data['description'].strip() or evidence):
        generated = build_summary(data, readme, source, web_sources=evidence)
        if '额度' in generated.get('notice', ''):
            from .auto_confirm import defer_budget
            defer_budget(ServiceError(generated['notice']))
        if generated.get('generation_status') in ('failed', 'invalid'):
            generation_error = ServiceError('中文归纳暂未成功，已保留已有资料；将自动重试',
                generated.get('generation_retryable', True), generated.get('generation_retry_after', 60))
        summary = {**old, **generated}
        # A generation failure or a missing source must not erase good Chinese
        # claims already saved by a successful browser research operation.
        old_health, new_health = summary_health(old), summary_health(generated)
        for key in ('overview', 'functions', 'innovations', 'use_cases', 'requirements', 'date_facts'):
            valid = new_health.get('overview_zh') if key == 'overview' else key in new_health.get('verified_fields', [])
            if not valid and old.get(key):
                summary[key] = old[key]
        if old_health.get('complete') and not new_health.get('complete'):
            summary['mode'] = old.get('mode', 'ai')
    summary = repair_overview_from_claims(summary)
    state = summary_health(summary)
    summary['health'] = state
    summary['chinese_status'] = 'complete' if state['complete'] else 'partial' if state['verified_count'] else 'missing'
    summary['curated_at'] = utcnow()
    if not state['complete']:
        summary['curation_notice'] = '已有中文资料已保留，部分栏目仍缺少可核验来源。' if state['verified_count'] else '保存的资料不足或中文生成未成功，可补充来源后重试。'
    else:
        summary.pop('curation_notice', None)
    with Session.begin() as db:
        repo = db.get(Repository, repo_id)
        if not repo or db.get(ProjectTrash, repo_id):
            return False
        repo.summary = summary
        save_organization(db, repo)
    if generation_error and not state['complete']:
        raise generation_error
    return state['complete']


def run_curation(job):
    with Session.begin() as db:
        current = db.get(Job, job.id)
        ids = current.payload.get('repo_ids')
        if ids is None:
            query = db.query(Repository).filter(Repository.id.not_in(db.query(ProjectTrash.repo_id)))
            if job.payload.get('repo_id'):
                query = query.filter_by(id=job.payload['repo_id'])
            else:
                query = query.filter(Repository.collected.is_(True))
            ids = [r.id for r in query.order_by(Repository.id)]
            current.payload = {**current.payload, 'repo_ids': ids}
        done = list(current.payload.get('summary_done', []))
        organized = list(current.payload.get('organized', []))
    failures = {}
    for start in range(0, len(ids), 12):
        batch = ids[start:start + 12]
        for repo_id in batch:
            if repo_id in done:
                continue
            with Session.begin() as db:
                db.get(Job, job.id).stage = f'中文资料智能体：整理 {len(done) + 1}/{len(ids)} 个项目'
            try:
                curate_repo(repo_id)
            except ServiceError as exc:
                if getattr(exc, 'deferred', False):
                    raise
                failures[str(repo_id)] = {'error': str(exc), 'retryable': exc.retryable}
                with Session.begin() as db:
                    current = db.get(Job, job.id)
                    current.payload = {**current.payload, 'summary_failures': failures}
                continue  # One incomplete document must not block other projects.
            done.append(repo_id)
            with Session.begin() as db:
                current = db.get(Job, job.id)
                current.payload = {**current.payload, 'summary_done': done}
        with Session() as db:
            rows = [r for r in db.query(Repository).filter(Repository.id.in_(batch))
                    if r.id not in organized and not db.get(ProjectTrash, r.id)
                    and (not db.get(ProjectOrganization, r.id) or db.get(ProjectOrganization, r.id).method not in ('manual', 'ai'))]
        if rows:
            with Session.begin() as db:
                db.get(Job, job.id).stage = f'用途分类智能体：整理 {start + 1}–{start + len(batch)}/{len(ids)} 个项目'
            classifications = classify_batch(rows)
            with Session.begin() as db:
                for repo in rows:
                    current_repo = db.get(Repository, repo.id)
                    if current_repo and not db.get(ProjectTrash, repo.id):
                        save_organization(db, current_repo, classifications[repo.id])
        organized = list(dict.fromkeys(organized + batch))
        with Session.begin() as db:
            current = db.get(Job, job.id)
            current.payload = {**current.payload, 'organized': organized}
    if failures and any(v['retryable'] for v in failures.values()) and job.attempts < 3:
        raise ServiceError(f'{len(failures)} 个项目的中文归纳需重试；其他项目已继续整理并保存', True, 60)
    from .summary import summary_health
    with Session.begin() as db:
        valid = [r for r in db.query(Repository).filter(Repository.id.in_(ids)) if not db.get(ProjectTrash, r.id)]
        complete = sum(summary_health(r.summary or {})['complete'] for r in valid)
        current = db.get(Job, job.id)
        current.status, current.finished_at = 'completed', utcnow()
        current.stage = f'已整理 {len(valid)} 个项目；中文资料完整 {complete} 个，待补充 {len(valid) - complete} 个'
        current.payload = {**current.payload, 'summary_failures': failures,
                           'result': {'total': len(valid), 'complete': complete, 'partial': len(valid) - complete}}
