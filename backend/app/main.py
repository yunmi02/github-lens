import asyncio
import base64
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from io import BytesIO
import ipaddress
from pathlib import Path
import secrets
import socket
import time
from uuid import uuid4
from urllib.parse import urlparse
from fastapi import FastAPI, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, SecretStr
import qrcode
from sqlalchemy import func, or_, select, case
from sqlalchemy.orm import load_only
from .config import settings, ROOT
from .db import Base, engine, Session, utcnow
from .models import Config, Batch, ImageRecord, Repository, ImageLink, Job, UploadSession, Snapshot, ImageResearch, ProjectTrash, ProjectOrganization, PERFORMANCE_INDEXES
from .research import agent_available, enqueue_research
from .github import ServiceError
from .security import init_security, hash_password, check_password, serializer, require_admin, is_admin, phone_session, digest, login_limiter
from .github import normalize_repo, safe_url
from .jobs import enqueue, worker_loop, DEFAULT_RULE
from .ocr import ocr_status
from .review import repair_linked_reviews
from .github_settings import configure_github_token
from .computer_research import router as computer_router, executor_state, execution_prompt, enqueue_project, ACTIVE
from .summary import detail_summary, summary_health, repair_overview_from_claims
from .library import organization, save_organization, search_score, LABELS
from .curation import enqueue_curation
from .queries import library_rows, job_rows


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    # create_all does not add indexes to existing tables. These additive,
    # idempotent migrations are applied to upgraded databases as well.
    for index in PERFORMANCE_INDEXES:
        index.create(engine, checkfirst=True)
    init_security()
    with Session.begin() as db:
        if settings.research_backend in ('computer_use', 'browser'):
            from .computer_research import prepare
            for pending in db.query(Job).filter(Job.kind.in_(['research', 'auto_confirm']), Job.status.in_(['queued', 'running'])):
                prepare(db, pending)
            if settings.research_backend == 'browser':
                for pending in db.query(Job).filter_by(status='waiting_browser'):
                    if pending.payload.get('executor') != 'browser_service':
                        pending.available_at, pending.error, pending.stage = utcnow(), '', '等待后台浏览器服务自动领取'
        repair_linked_reviews(db)
    worker = asyncio.create_task(worker_loop()) if settings.worker_enabled else None
    browser_service = None
    if settings.worker_enabled and settings.research_backend == 'browser' and settings.browser_service_enabled:
        from .browser_service import service
        browser_service = service
        service.start()
    yield
    if browser_service:
        await asyncio.to_thread(browser_service.stop)
    if worker:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


app = FastAPI(title='GitHub Lens · 项目情报库', version='0.1.0', lifespan=lifespan)
app.include_router(computer_router)
app.add_middleware(RequestBodyLimitMiddleware, max_body_size=21 * 1024 * 1024)


@app.middleware('http')
async def boundaries(request: Request, call_next):
    # No wildcard CORS. Mutation requests must originate from this host.
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        expected = {request.headers.get('host', '')}
        if settings.public_base_url:
            expected.add(urlparse(settings.public_base_url).netloc)
        if origin and urlparse(origin).netloc not in expected:
            return JSONResponse({'detail': '请求来源不受信任'}, status_code=403)
        length = request.headers.get('content-length')
        if length:
            try:
                size = int(length)
            except ValueError:
                return JSONResponse({'detail': '无效的请求长度'}, status_code=400)
            if size < 0:
                return JSONResponse({'detail': '无效的请求长度'}, status_code=400)
            if size > 21 * 1024 * 1024:
                return JSONResponse({'detail': '请求超过 20 MB 限制，请逐张上传'}, status_code=413)
        # FastAPI parses multipart before calling the endpoint. Authenticate and
        # verify ownership here, before accepting/spooling any uploaded bytes.
        parts = request.url.path.strip('/').split('/')
        if request.method == 'POST' and len(parts) == 4 and parts[:2] == ['api', 'import-batches'] and parts[3] == 'images':
            try:
                with Session() as db:
                    authorized_batch(db, parts[2], request)
            except HTTPException as exc:
                return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Cache-Control'] = 'no-store' if request.url.path.startswith('/api/') else 'no-cache'
    return response


class PasswordInput(BaseModel):
    password: str = Field(min_length=10, max_length=200)


@app.get('/api/auth/status')
def auth_status(request: Request):
    with Session() as db:
        return {'authenticated': is_admin(request), 'setup_required': db.get(Config, 'admin') is None}


@app.post('/api/auth/setup')
def setup(body: PasswordInput, request: Request, response: Response):
    if request.client.host not in ('127.0.0.1', '::1', 'testclient'):
        raise HTTPException(403, '首次设置请在服务器本机打开，或配置 ADMIN_PASSWORD 环境变量')
    with Session.begin() as db:
        if db.get(Config, 'admin'):
            raise HTTPException(409, '管理员密码已设置，请登录')
        db.add(Config(key='admin', value={'hash': hash_password(body.password)}))
    response.set_cookie('lens_auth', serializer().dumps('admin'), httponly=True, secure=settings.cookie_secure, samesite='strict', max_age=604800)
    return {'ok': True}


@app.post('/api/auth/login')
def login(body: PasswordInput, request: Request, response: Response):
    key = ('login', request.client.host)
    login_limiter.reserve(key)
    with Session() as db:
        row = db.get(Config, 'admin')
        if not row or not check_password(body.password, row.value['hash']):
            raise HTTPException(401, '密码不正确')
    login_limiter.clear(key)
    response.set_cookie('lens_auth', serializer().dumps('admin'), httponly=True, secure=settings.cookie_secure, samesite='strict', max_age=604800)
    return {'ok': True}


@app.post('/api/auth/logout')
def logout(response: Response):
    response.delete_cookie('lens_auth')
    return {'ok': True}


admin = [Depends(require_admin)]


class PasswordChange(BaseModel):
    current_password: SecretStr = Field(min_length=1, max_length=200)
    new_password: SecretStr = Field(min_length=10, max_length=200)


@app.post('/api/auth/password', dependencies=admin)
def change_password(body: PasswordChange, request: Request, response: Response):
    key = ('password', request.client.host)
    login_limiter.reserve(key)
    with Session() as db:
        record = db.get(Config, 'admin')
        if not record:
            raise HTTPException(401, '请先设置管理员密码')
        old_hash = record.value['hash']
    if not check_password(body.current_password.get_secret_value(), old_hash):
        raise HTTPException(401, '当前密码不正确')
    if body.current_password.get_secret_value() == body.new_password.get_secret_value():
        raise HTTPException(422, '新密码应与当前密码不同')
    new_hash = hash_password(body.new_password.get_secret_value())
    with Session.begin() as db:
        changed = db.query(Config).filter(Config.key == 'admin', Config.value['hash'].as_string() == old_hash).update(
            {Config.value: {'hash': new_hash}}, synchronize_session=False)
        if not changed:
            raise HTTPException(409, '密码已被更新，请重新登录后操作')
        db.get(Config, 'session_secret').value = {'secret': secrets.token_hex(32)}
    login_limiter.clear(key)
    response.set_cookie('lens_auth', serializer().dumps('admin'), httponly=True, secure=settings.cookie_secure, samesite='strict', max_age=604800)
    return {'ok': True, 'message': '密码已修改，其他设备的旧登录已失效'}


@app.get('/api/health')
def health():
    return {'status': 'ok', 'version': '0.1.0'}


@app.get('/api/settings', dependencies=admin)
def get_settings():
    with Session() as db:
        rule = db.get(Config, 'discovery_rule')
        return {'ocr': ocr_status(), 'github_authenticated': bool(settings.github_token), 'ai_configured': bool(settings.ai_base_url and settings.ai_api_key and settings.ai_model),
                'ai_daily_limit': settings.ai_daily_limit, 'public_base_url': settings.public_base_url, 'discovery_rule': rule.value if rule else DEFAULT_RULE,
                'max_image_mb': 20, 'max_batch_files': 100, 'storage': 'PostgreSQL' if settings.database_url.startswith('postgres') else 'SQLite', 'worker': '持久化队列 · 单 Worker' if settings.worker_enabled else '后台 Worker 未启动',
                'worker_enabled': settings.worker_enabled, 'schedule_enabled': settings.schedule_enabled,
                'research_agent': {'available': agent_available(), 'automatic': settings.agent_auto_research, 'auto_confirm': settings.agent_auto_confirm, 'provider': settings.research_backend, 'executor': executor_state(db), 'search_daily_limit': settings.agent_search_daily_limit},
                'privacy': '本地 OCR；后台专用 Chrome 检索网页，图片线索和页面正文发送至配置的模型作理解与中文归纳，不调用搜索 API。' if settings.research_backend == 'browser' else '普通 OCR 在本机完成；computer-use 任务由已授权的 Codex 桌面会话操作浏览器检索，网页服务负责派发和保存来源。原图可按批次删除。' if settings.research_backend == 'computer_use' else '研究会将截图和线索发送至配置的 AI 服务。'}


@app.get('/api/browser-service/status', dependencies=admin)
def browser_service_status():
    with Session() as db:
        return executor_state(db)


@app.get('/api/stats', dependencies=admin)
def stats():
    with Session() as db:
        active = db.query(Repository).filter_by(collected=True).filter(Repository.id.not_in(select(ProjectTrash.repo_id)))
        return {'projects': active.count(), 'favorites': active.filter_by(favorite=True).count(), 'trashed': db.query(ProjectTrash).count(),
                'images': db.query(ImageRecord).count(), 'needs_review': db.query(ImageRecord).filter(ImageRecord.status.in_(['needs_review', 'failed', 'researching'])).count(),
                'pending': db.query(Job).filter(Job.status.in_(ACTIVE)).count()}


class GitHubTokenInput(BaseModel):
    token: SecretStr


@app.post('/api/settings/github-token', dependencies=admin)
def update_github_token(body: GitHubTokenInput):
    return configure_github_token(body.token.get_secret_value())


def repo_json(repo, trashed_at=None, org=None, compact=False):
    summary = repair_overview_from_claims(repo.summary or {})
    health = summary_health(summary)
    organized = organization(repo, org)
    return {'id': repo.id, 'full_name': repo.full_name, 'description': repo.description, 'language': repo.language, 'stars': repo.stars, 'forks': repo.forks,
            'favorite': repo.favorite, 'collected': repo.collected, 'tags': repo.tags, 'notes': repo.notes, 'study_status': repo.study_status,
            'archived': repo.archived, 'metadata': {k: v for k, v in repo.metadata_json.items() if not compact or k != 'web_evidence'}, 'summary': summary, 'fetched_at': repo.fetched_at, 'trashed_at': trashed_at,
            'display_description': summary.get('overview', {}).get('text') if health['overview_zh'] else '中文简介待补全，请在详情中查看来源并生成归纳。',
            'summary_health': health, 'categories': organized['categories'], 'category_labels': organized['labels'],
            'keywords': organized['keywords'], 'classification_method': organized['method']}


@app.get('/api/projects', dependencies=admin)
def projects(q: str = '', language: str = '', favorite: bool = False, sort: str = 'recent', page: int = 1, trash: bool = False, category: str = '', summary_state: str = ''):
    with Session() as db:
        query = db.query(Repository).filter_by(collected=True)
        active_total = query.filter(Repository.id.not_in(select(ProjectTrash.repo_id))).count()
        trash_total = db.query(ProjectTrash).count()
        if trash:
            query = query.join(ProjectTrash, ProjectTrash.repo_id == Repository.id)
        else:
            query = query.filter(Repository.id.not_in(select(ProjectTrash.repo_id)))
        if language:
            query = query.filter(Repository.language == language)
        if favorite:
            query = query.filter(Repository.favorite.is_(True))
        org_rows = {o.repo_id: o for o in db.query(ProjectOrganization)}
        rows = list(library_rows(query))
        ranked = []
        for repo in rows:
            org = organization(repo, org_rows.get(repo.id))
            score = search_score(repo, org, q[:200])
            complete = summary_health(repair_overview_from_claims(repo.summary or {}))['complete']
            if score and (not summary_state or complete == (summary_state == 'complete')):
                ranked.append((repo, org, score))
        facets = [{'id': key, 'label': label, 'count': sum(key in org['categories'] for _, org, _ in ranked)} for key, label in LABELS.items()]
        ranked = [entry for entry in ranked if not category or category in entry[1]['categories']]
        removed = {t.repo_id: t.trashed_at for t in db.query(ProjectTrash)} if trash else {}
        ranked.sort(key=lambda entry: (entry[0].stars if sort == 'stars' else entry[2] if q and sort != 'recent' else 0,
                    removed.get(entry[0].id, '') if trash else entry[0].fetched_at), reverse=True)
        total = len(ranked)
        rows = [r for r, _, _ in ranked[(max(page, 1) - 1) * 24:max(page, 1) * 24]]
        languages_query = db.query(Repository.language).filter_by(collected=True).filter(Repository.id.in_(select(ProjectTrash.repo_id)) if trash else Repository.id.not_in(select(ProjectTrash.repo_id)))
        languages = [v[0] for v in languages_query.distinct() if v[0]]
        task = db.query(Job).filter(Job.kind == 'curate_library').order_by(Job.created_at.desc()).first()
        return {'items': [repo_json(r, removed.get(r.id), org_rows.get(r.id), compact=True) for r in rows], 'total': total, 'languages': sorted(languages), 'active_total': active_total, 'trash_total': trash_total,
                'categories': facets, 'curation_task': {'job_id': task.id, 'status': task.status, 'stage': task.stage, 'error': task.error} if task else None}


@app.post('/api/projects/curate', dependencies=admin)
def curate_projects():
    with Session.begin() as db:
        job_id, created = enqueue_curation(db)
        return {'job_id': job_id, 'created': created}


@app.get('/api/projects/{repo_id}', dependencies=admin)
def project(repo_id: int):
    with Session() as db:
        repo = db.get(Repository, repo_id)
        if not repo:
            raise HTTPException(404, '项目不存在')
        removed = db.get(ProjectTrash, repo_id)
        result = repo_json(repo, removed.trashed_at if removed else None, db.get(ProjectOrganization, repo_id))
        result['summary'] = repair_overview_from_claims(detail_summary(repo))
        task = db.query(Job).options(load_only(Job.id, Job.status, Job.stage, Job.error)).filter(
            Job.kind == 'computer_use', Job.payload['repo_id'].as_integer() == repo.id).order_by(Job.created_at.desc()).first()
        result['research_task'] = {'job_id': task.id, 'status': task.status, 'stage': task.stage, 'error': task.error, 'prompt': execution_prompt(task.id)} if task else None
        result['research_provider'] = settings.research_backend
        summary_task = next((j for j in db.query(Job).filter(Job.kind.in_(('curate_project', 'curate_library'))).order_by(Job.created_at.desc())
                             if j.payload.get('repo_id') == repo_id or repo_id in j.payload.get('repo_ids', [])), None)
        result['summary_task'] = {'job_id': summary_task.id, 'status': summary_task.status, 'stage': summary_task.stage, 'error': summary_task.error} if summary_task else None
        result['readme'] = repo.readme
        result['category_options'] = [{'id': key, 'label': label} for key, label in LABELS.items()]
        result['images'] = [{'id': i.id, 'filename': i.filename} for i in db.query(ImageRecord).join(ImageLink, ImageLink.image_id == ImageRecord.id).filter(ImageLink.repo_id == repo_id)]
        result['snapshots'] = [{'date': s.date, 'stars': s.stars} for s in db.query(Snapshot).filter_by(repo_id=repo_id).order_by(Snapshot.date).limit(90)]
        return result


class ProjectPatch(BaseModel):
    favorite: bool | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=10000)
    study_status: str | None = Field(default=None, pattern='^(待研究|已读|已使用)$')
    collected: bool | None = None
    categories: list[str] | None = Field(default=None, max_length=3)
    keywords: list[str] | None = Field(default=None, max_length=24)


@app.patch('/api/projects/{repo_id}', dependencies=admin)
def patch_project(repo_id: int, body: ProjectPatch):
    with Session.begin() as db:
        repo = db.get(Repository, repo_id)
        if not repo:
            raise HTTPException(404, '项目不存在')
        if db.get(ProjectTrash, repo_id):
            raise HTTPException(409, '项目在回收站中，请先恢复')
        for key, value in body.model_dump(exclude_none=True).items():
            if key in ('categories', 'keywords'):
                continue
            if key == 'tags':
                value = list(dict.fromkeys(t.strip()[:50] for t in value if t.strip()))
            setattr(repo, key, value)
        if body.categories is not None or body.keywords is not None:
            previous = organization(repo, db.get(ProjectOrganization, repo_id))
            if body.categories is not None and any(c not in LABELS for c in body.categories):
                raise HTTPException(422, '请选择已有的用途分类')
            save_organization(db, repo, {'categories': body.categories if body.categories is not None else previous['categories'],
                                      'keywords': body.keywords if body.keywords is not None else previous['keywords']}, manual=True)
        if body.collected:
            enqueue(db, 'collect', {'full_name': repo.full_name})
        return repo_json(repo, org=db.get(ProjectOrganization, repo_id))


@app.post('/api/projects/{repo_id}/curate', dependencies=admin)
def curate_project(repo_id: int):
    with Session.begin() as db:
        repo = db.get(Repository, repo_id)
        if not repo:
            raise HTTPException(404, '项目不存在')
        if db.get(ProjectTrash, repo_id):
            raise HTTPException(409, '项目在回收站中，请先恢复')
        job_id, created = enqueue_curation(db, repo_id)
        return {'job_id': job_id, 'created': created}


@app.delete('/api/projects/{repo_id}', dependencies=admin)
def trash_project(repo_id: int):
    with Session.begin() as db:
        repo = db.get(Repository, repo_id)
        if not repo or not repo.collected:
            raise HTTPException(404, '项目不存在')
        removed = db.get(ProjectTrash, repo_id)
        if not removed:
            removed = ProjectTrash(repo_id=repo_id)
            db.add(removed)
            db.flush()
        return {'id': repo_id, 'trashed_at': removed.trashed_at, 'message': '项目已移入回收站'}


@app.post('/api/projects/{repo_id}/restore', dependencies=admin)
def restore_project(repo_id: int):
    with Session.begin() as db:
        repo = db.get(Repository, repo_id)
        if not repo or not repo.collected:
            raise HTTPException(404, '项目不存在')
        removed = db.get(ProjectTrash, repo_id)
        if removed:
            db.delete(removed)
        return {'id': repo_id, 'message': '项目已恢复到项目库'}


class RepoInput(BaseModel):
    full_name: str = Field(max_length=500)


@app.post('/api/projects/import', dependencies=admin)
def import_repo(body: RepoInput):
    try:
        name = normalize_repo(body.full_name)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    with Session.begin() as db:
        existing = db.query(Repository).filter(Repository.full_name.ilike(name)).first()
        if existing and db.get(ProjectTrash, existing.id):
            raise HTTPException(409, '项目在回收站中，请先恢复')
        return {'job_id': enqueue(db, 'collect', {'full_name': name})}


@app.post('/api/projects/{repo_id}/refresh', dependencies=admin)
def refresh(repo_id: int):
    with Session.begin() as db:
        repo = db.get(Repository, repo_id)
        if not repo:
            raise HTTPException(404, '项目不存在')
        if db.get(ProjectTrash, repo_id):
            raise HTTPException(409, '项目在回收站中，请先恢复')
        if settings.research_backend in ('computer_use', 'browser'):
            return {'job_id': enqueue_project(db, repo), 'provider': 'computer_use'}
        return {'job_id': enqueue(db, 'collect', {'full_name': repo.full_name, 'force': True})}


def upload_identity(request):
    return None if is_admin(request) else phone_session(request)


@app.post('/api/import-batches')
def create_batch(request: Request):
    phone = upload_identity(request)
    with Session.begin() as db:
        batch = Batch(id=str(uuid4()), source='phone' if phone else 'desktop', session_id=phone.id if phone else None)
        db.add(batch)
        return {'id': batch.id}


def authorized_batch(db, batch_id, request):
    batch = db.get(Batch, batch_id)
    phone = upload_identity(request)
    if not batch or (phone and batch.session_id != phone.id):
        raise HTTPException(404, '批次不存在')
    return batch, phone


@app.post('/api/import-batches/{batch_id}/images')
async def upload_image(batch_id: str, request: Request, file: UploadFile = File(...)):
    with Session() as db:
        authorized_batch(db, batch_id, request)
    data = await file.read(settings.max_image_bytes + 1)
    await file.close()
    if len(data) > settings.max_image_bytes:
        raise HTTPException(413, '单张图片不能超过 20 MB')
    import hashlib
    image_id = str(uuid4())
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in ('PNG', 'JPEG', 'WEBP'):
                raise HTTPException(415, '仅支持 PNG、JPEG、WebP；请先转换 HEIC 图片')
            if image.width * image.height > settings.max_pixels:
                raise HTTPException(413, '图片像素过大，请裁剪后上传')
            image.verify()
            extension = {'PNG': '.png', 'JPEG': '.jpg', 'WEBP': '.webp'}[image.format]
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise HTTPException(415, '文件损坏或不是支持的图片')
    path = settings.data_dir / 'images' / (image_id + extension)
    path.write_bytes(data)
    try:
        with Session.begin() as db:
            batch, phone = authorized_batch(db, batch_id, request)
            # The upload API is serialized on one event loop; recheck limits inside transaction.
            if db.query(ImageRecord).filter_by(batch_id=batch_id).count() >= 100:
                raise HTTPException(413, '每批最多 100 张图片')
            batch_bytes = sum(Path(i.path).stat().st_size for i in db.query(ImageRecord).filter_by(batch_id=batch_id) if Path(i.path).exists())
            if batch_bytes + len(data) > 500 * 1024 * 1024:
                raise HTTPException(413, '每批图片累计不能超过 500 MB')
            if phone:
                session = db.get(UploadSession, phone.id)
                if session.file_count >= 100 or session.byte_count + len(data) > 500 * 1024 * 1024:
                    raise HTTPException(413, '本次扫码上传额度已用完')
                session.file_count += 1
                session.byte_count += len(data)
            db.add(ImageRecord(id=image_id, batch_id=batch_id, filename=Path(file.filename or 'image').name[:500], sha256=hashlib.sha256(data).hexdigest(), path=str(path)))
            db.flush()
            job_id = enqueue(db, 'recognize', {'image_id': image_id})
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {'id': image_id, 'job_id': job_id}


@app.get('/api/import-batches', dependencies=admin)
def batches():
    with Session() as db:
        rows = db.query(Batch).order_by(Batch.created_at.desc()).limit(30).all()
        grouped = {b.id: [] for b in rows}
        images = db.query(ImageRecord).options(load_only(ImageRecord.id, ImageRecord.batch_id, ImageRecord.filename,
            ImageRecord.status, ImageRecord.error, ImageRecord.created_at, ImageRecord.candidates)).filter(ImageRecord.batch_id.in_(grouped)).order_by(ImageRecord.created_at).all()
        research = {r.image_id: r for r in db.query(ImageResearch).options(load_only(ImageResearch.image_id,
            ImageResearch.status, ImageResearch.stage, ImageResearch.error)).filter(ImageResearch.image_id.in_([i.id for i in images]))}
        for image in images:
            grouped[image.batch_id].append(image_json(image, research.get(image.id), compact=True))
        return [{'id': b.id, 'source': b.source, 'created_at': b.created_at, 'images': grouped[b.id]} for b in rows]


def image_json(image, research=None, compact=False):
    candidates = [{key: value for key, value in c.items() if key in ('full_name', 'confirmed', 'repo_id', 'auto', 'evidence', 'description', 'stars', 'language', 'rejected', 'confirmation_error')} for c in image.candidates] if compact else image.candidates
    return {'id': image.id, 'filename': image.filename, 'status': image.status, 'text': '' if compact else image.text, 'candidates': candidates, 'error': image.error, 'created_at': image.created_at,
            'research': {'status': research.status, 'stage': research.stage, 'error': research.error} if research else None}


def research_json(row):
    return {'job_id': row.job_id, 'status': row.status, 'stage': row.stage, 'report': row.report, 'error': row.error, 'updated_at': row.updated_at} if row else None


@app.get('/api/import-batches/{batch_id}')
def batch_detail(batch_id: str, request: Request):
    with Session() as db:
        batch, _ = authorized_batch(db, batch_id, request)
        return {'id': batch.id, 'images': [image_json(i) for i in db.query(ImageRecord).filter_by(batch_id=batch_id)]}


@app.delete('/api/import-batches/{batch_id}', dependencies=admin)
def delete_batch(batch_id: str):
    paths = []
    with Session.begin() as db:
        batch = db.get(Batch, batch_id)
        if not batch:
            raise HTTPException(404, '批次不存在')
        for image in db.query(ImageRecord).filter_by(batch_id=batch_id):
            jobs = [j for j in db.query(Job).filter(Job.kind.in_(['recognize', 'collect', 'research', 'auto_confirm', 'computer_use'])) if j.payload.get('image_id') == image.id]
            if any(j.status in ('running', 'browser_running') for j in jobs):
                raise HTTPException(409, '批次仍在处理，请完成后删除')
            for job in jobs:
                db.delete(job)
            db.query(ImageLink).filter_by(image_id=image.id).delete()
            db.query(ImageResearch).filter_by(image_id=image.id).delete()
            paths.append(image.path)
            db.delete(image)
        db.delete(batch)
    for path in paths:
        p = Path(path).resolve()
        if p.parent == (settings.data_dir / 'images').resolve():
            p.unlink(missing_ok=True)
    return {'ok': True}


@app.get('/api/images/{image_id}/file', dependencies=admin)
def image_file(image_id: str):
    with Session() as db:
        image = db.get(ImageRecord, image_id)
        if not image:
            raise HTTPException(404, '图片不存在')
        path = Path(image.path).resolve()
        if path.parent != (settings.data_dir / 'images').resolve() or not path.is_file():
            raise HTTPException(404, '原图文件不存在，请重新上传')
        return FileResponse(path)


@app.post('/api/recognitions/{image_id}/confirm', dependencies=admin)
def confirm(image_id: str, body: RepoInput):
    try:
        name = normalize_repo(body.full_name)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    with Session.begin() as db:
        image = db.get(ImageRecord, image_id)
        if not image:
            raise HTTPException(404, '图片不存在')
        ensure_research_idle(db, image_id)
        for job in db.query(Job).filter(Job.kind == 'collect', Job.status.in_(['queued', 'running'])):
            if job.payload.get('image_id') == image_id:
                if job.payload['full_name'].lower() == name.lower():
                    return {'job_id': job.id}
                raise HTTPException(409, '该图片正在关联项目，请完成后再补充')
        image.status, image.error = 'collecting', ''
        return {'job_id': enqueue(db, 'collect', {'image_id': image_id, 'full_name': name})}


@app.post('/api/recognitions/{image_id}/ignore', dependencies=admin)
def ignore(image_id: str):
    with Session.begin() as db:
        image = db.get(ImageRecord, image_id)
        if not image:
            raise HTTPException(404, '图片不存在')
        ensure_research_idle(db, image_id)
        if any(j.payload.get('image_id') == image_id for j in db.query(Job).filter(Job.kind == 'collect', Job.status.in_(['queued', 'running']))):
            raise HTTPException(409, '该图片正在关联项目，请完成后再操作')
        image.status = 'ignored'
    return {'ok': True}


def ensure_research_idle(db, image_id):
    row = db.get(ImageResearch, image_id)
    job = db.get(Job, row.job_id) if row else None
    if job and job.status in ACTIVE:
        raise HTTPException(409, '智能体仍在研究，请完成后确认或忽略')


@app.get('/api/recognitions/{image_id}/research', dependencies=admin)
def research_detail(image_id: str):
    with Session() as db:
        image = db.get(ImageRecord, image_id)
        if not image:
            raise HTTPException(404, '图片不存在')
        return {'image': image_json(image), 'research': research_json(db.get(ImageResearch, image_id)),
                'provider': settings.research_backend, 'execution': {**executor_state(db), 'prompt': execution_prompt(db.get(ImageResearch, image_id).job_id) if db.get(ImageResearch, image_id) else execution_prompt()}}


@app.post('/api/recognitions/{image_id}/research', dependencies=admin)
def research_image(image_id: str):
    if not agent_available():
        raise HTTPException(422, '请先配置支持图片理解的 AI 服务：AI_BASE_URL、AI_API_KEY、AI_MODEL')
    with Session.begin() as db:
        image = db.get(ImageRecord, image_id)
        if not image:
            raise HTTPException(404, '图片不存在')
        try:
            job_id, created = enqueue_research(db, image)
        except ServiceError as exc:
            raise HTTPException(409, str(exc))
        return {'job_id': job_id, 'created': created}


@app.post('/api/research-pending', dependencies=admin)
def research_pending():
    if not agent_available():
        raise HTTPException(422, '请先配置支持图片理解的 AI 服务')
    with Session.begin() as db:
        images = db.query(ImageRecord).filter(ImageRecord.status.in_(['needs_review', 'failed'])).order_by(ImageRecord.created_at.desc()).limit(20).all()
        ids = []
        for image in images:
            try:
                job_id, created = enqueue_research(db, image)
                if created:
                    ids.append(job_id)
            except ServiceError:
                continue
        return {'job_ids': ids, 'count': len(ids), 'limit': 20}


@app.post('/api/recognitions/{image_id}/auto-confirm', dependencies=admin)
def auto_confirm_image(image_id: str):
    if not agent_available():
        raise HTTPException(422, '请先配置 DeepSeek 图片理解及搜索服务')
    with Session.begin() as db:
        image = db.get(ImageRecord, image_id)
        if not image:
            raise HTTPException(404, '图片不存在')
        try:
            job_id, created = enqueue_research(db, image, auto_confirm=True)
        except ServiceError as exc:
            raise HTTPException(409, str(exc))
        return {'job_id': job_id, 'created': created}


@app.post('/api/auto-confirm-pending', dependencies=admin)
def auto_confirm_pending():
    if not agent_available():
        raise HTTPException(422, '请先配置 DeepSeek 图片理解及搜索服务')
    with Session.begin() as db:
        images = db.query(ImageRecord).filter(ImageRecord.status.in_(['needs_review', 'failed'])).order_by(ImageRecord.created_at).all()
        ids = []
        for image in images:
            try:
                job_id, created = enqueue_research(db, image, auto_confirm=True)
                if created:
                    ids.append(job_id)
            except ServiceError:
                continue
        return {'job_ids': ids, 'count': len(ids)}


@app.get('/api/jobs', dependencies=admin)
def jobs():
    with Session() as db:
        priority = case((Job.status.in_(('running', 'browser_running')), 0), (Job.status.in_(('queued', 'waiting_browser')), 1), else_=2)
        return [{'id': j.id, 'kind': j.kind, 'status': j.status, 'stage': j.stage, 'attempts': j.attempts,
                 'browser_attempts': (j.browser_runs or 0) if settings.research_backend == 'browser' and j.provider == 'computer_use' else j.browser_runs,
                 'error': j.error, 'created_at': j.created_at, 'available_at': j.available_at}
                for j in job_rows(db.query(Job).order_by(priority, Job.created_at.desc()).limit(100))]


@app.post('/api/jobs/{job_id}/retry', dependencies=admin)
def retry_job(job_id: str):
    with Session.begin() as db:
        job = db.get(Job, job_id)
        if not job or job.status != 'failed':
            raise HTTPException(409, '仅失败任务可以重试')
        image_id = job.payload.get('image_id')
        row = db.get(ImageResearch, image_id) if image_id else None
        if job.kind in ('research', 'auto_confirm', 'computer_use') and row and row.job_id != job.id:
            raise HTTPException(409, '该任务已由新的研究任务替代，请查看当前任务')
        repo_id = job.payload.get('repo_id')
        if not repo_id and job.payload.get('full_name'):
            repo = db.query(Repository).filter(Repository.full_name.ilike(job.payload['full_name'])).first()
            repo_id = repo.id if repo else None
        if repo_id and db.get(ProjectTrash, repo_id):
            raise HTTPException(409, '项目在回收站中，请先恢复')
        job.status, job.attempts, job.error, job.available_at = 'queued', 0, '', utcnow()
        job.finished_at, job.stage = None, '等待重试'
        if job.payload.get('provider') == 'computer_use':
            job.payload = {**job.payload, 'browser_failures': 0}
        if job.kind == 'recognize':
            image = db.get(ImageRecord, job.payload['image_id'])
            image.status, image.error = 'queued', ''
        elif job.kind in ('research', 'auto_confirm', 'computer_use') and job.payload.get('image_id'):
            row = db.get(ImageResearch, job.payload['image_id'])
            row.status, row.error, row.stage = 'queued', '', '等待智能体重试'
            db.get(ImageRecord, row.image_id).status = 'researching'
        elif job.kind == 'collect' and job.payload.get('image_id'):
            image = db.get(ImageRecord, job.payload['image_id'])
            image.status, image.error = 'collecting', ''
    return {'ok': True}


class SessionInput(BaseModel):
    base_url: str = Field(default='', max_length=300)


@app.post('/api/upload-sessions', dependencies=admin)
def create_upload_session(body: SessionInput, request: Request):
    base = (body.base_url or settings.public_base_url or str(request.base_url)).rstrip('/')
    parsed = urlparse(base)
    if not safe_url(base) or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise HTTPException(422, '请输入不带路径的 http/https 服务地址')
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    session_id = str(uuid4())
    with Session.begin() as db:
        db.add(UploadSession(id=session_id, token_hash=digest(token), expires_at=expires))
    url = base + '/mobile#token=' + token
    img = qrcode.make(url)
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return {'id': session_id, 'url': url, 'expires_at': expires, 'qr': 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode(),
            'loopback': urlparse(base).hostname in ('127.0.0.1', 'localhost', '::1')}


@app.get('/api/network', dependencies=admin)
def network(request: Request):
    ips = []
    try:
        ips = sorted({item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET) if not item[4][0].startswith('127.')})
    except OSError:
        pass
    return {'suggestions': [f'http://{ip}:8000' for ip in ips], 'configured': settings.public_base_url}


class ExchangeInput(BaseModel):
    token: str = Field(min_length=20, max_length=200)


@app.post('/api/upload-sessions/exchange')
def exchange(body: ExchangeInput):
    with Session.begin() as db:
        row = db.query(UploadSession).filter_by(token_hash=digest(body.token)).first()
        if not row or row.revoked or row.credential_hash or datetime.fromisoformat(row.expires_at) <= datetime.now(timezone.utc):
            raise HTTPException(401, '二维码已使用、过期或撤销，请重新扫码')
        credential = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        changed = db.query(UploadSession).filter(UploadSession.id == row.id, UploadSession.credential_hash.is_(None),
            UploadSession.revoked.is_(False), UploadSession.expires_at > utcnow()).update(
            {UploadSession.credential_hash: digest(credential), UploadSession.expires_at: expires_at}, synchronize_session=False)
        if not changed:
            raise HTTPException(401, '二维码已使用、过期或撤销，请重新扫码')
        return {'credential': credential, 'expires_at': expires_at}


@app.delete('/api/upload-sessions/{session_id}', dependencies=admin)
def revoke(session_id: str):
    with Session.begin() as db:
        row = db.get(UploadSession, session_id)
        if row:
            row.revoked = True
    return {'ok': True}


class RuleInput(BaseModel):
    enabled: bool = True
    days: int = Field(default=30, ge=1, le=365)
    min_stars: int = Field(default=100, ge=0, le=1000000)
    language: str = Field(default='', max_length=30, pattern=r'^[A-Za-z0-9+#. -]*$')
    topic: str = Field(default='', max_length=50, pattern=r'^[a-z0-9-]*$')
    limit: int = Field(default=100, ge=1, le=100)
    hour: int = Field(default=9, ge=0, le=23)


@app.put('/api/discovery-rule', dependencies=admin)
def save_rule(body: RuleInput):
    with Session.begin() as db:
        row = db.get(Config, 'discovery_rule')
        if row:
            row.value = body.model_dump()
        else:
            db.add(Config(key='discovery_rule', value=body.model_dump()))
    return {'ok': True}


@app.post('/api/discoveries/refresh', dependencies=admin)
def discover_refresh():
    with Session.begin() as db:
        existing = db.query(Job).filter(Job.kind == 'discovery', Job.status.in_(['queued', 'running'])).first()
        return {'job_id': existing.id if existing else enqueue(db, 'discovery', {})}


@app.get('/api/discoveries', dependencies=admin)
def discoveries():
    with Session() as db:
        row = db.get(Config, 'discovery_result')
        if not row:
            return {'items': [], 'fetched_at': None, 'total_count': 0}
        result = dict(row.value)
        result['items'] = [repo_json(r) for r in db.query(Repository).filter(Repository.id.in_(result['repo_ids']), Repository.id.not_in(select(ProjectTrash.repo_id))).order_by(Repository.stars.desc())]
        return result


@app.get('/api/export', dependencies=admin)
def export():
    with Session() as db:
        return JSONResponse({'exported_at': utcnow(), 'projects': [repo_json(r, org=db.get(ProjectOrganization, r.id)) for r in db.query(Repository).filter_by(collected=True).filter(Repository.id.not_in(select(ProjectTrash.repo_id)))]}, headers={'Content-Disposition': 'attachment; filename="github-lens-export.json"'})


dist = ROOT / 'frontend' / 'dist'
if dist.exists():
    app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

    @app.get('/{path:path}')
    def frontend(path: str):
        if path.startswith('api/'):
            raise HTTPException(404, '接口不存在')
        return FileResponse(dist / 'index.html')
