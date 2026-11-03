from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
import pytest
from fastapi import HTTPException
from sqlalchemy import event
from app.db import Session, engine
from app.models import Repository, Batch, ImageRecord, ImageResearch, Job
from app.security import LoginLimiter
from app.summary import summary_health


def test_upload_identity_is_checked_before_multipart_parsing(client, monkeypatch):
    batch = client.post('/api/import-batches').json()['id']
    client.cookies.clear()
    async def forbidden(*a, **kw):
        raise AssertionError('Unauthenticated uploads must not reach the multipart parser')
    monkeypatch.setattr('starlette.formparsers.MultiPartParser.parse', forbidden)
    response = client.post(f'/api/import-batches/{batch}/images', content=b'untrusted body',
                          headers={'Content-Type': 'multipart/form-data; boundary=abc'})
    assert response.status_code == 401


def test_chunked_upload_without_content_length_is_limited(client):
    batch = client.post('/api/import-batches').json()['id']
    def body():
        yield b'--abc\r\nContent-Disposition: form-data; name="file"; filename="big.png"\r\nContent-Type: image/png\r\n\r\n'
        for _ in range(22):
            yield b'x' * (1024 * 1024)
        yield b'\r\n--abc--\r\n'
    response = client.post(f'/api/import-batches/{batch}/images', content=body(),
                           headers={'Content-Type': 'multipart/form-data; boundary=abc'})
    assert response.status_code == 413
    with Session() as db:
        assert db.query(ImageRecord).count() == 0


def test_login_attempt_reservations_are_concurrent_and_bounded():
    limiter = LoginLimiter(limit=3, capacity=4)
    def attempt(_):
        try:
            limiter.reserve('one-client')
            return True
        except HTTPException as error:
            assert error.status_code == 429
            return False
    with ThreadPoolExecutor(max_workers=12) as pool:
        assert sum(pool.map(attempt, range(30))) == 3
    for i in range(20):
        limiter.reserve(str(i))
    assert len(limiter.entries) == 4


def test_qr_token_can_only_be_claimed_once_under_concurrency(client):
    qr = client.post('/api/upload-sessions', json={'base_url': 'http://testserver'}).json()
    token = parse_qs(urlparse(qr['url']).fragment)['token'][0]
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post('/api/upload-sessions/exchange', json={'token': token}), range(4)))
    assert sum(r.status_code == 200 for r in responses) == 1
    assert all(r.status_code in (200, 401) for r in responses)


def test_password_change_invalidates_old_sessions_and_keeps_current_session(client):
    old_cookie = client.cookies.get('lens_auth')
    result = client.post('/api/auth/password', json={'current_password': 'test-password-12345', 'new_password': 'changed-password-12345'})
    assert result.status_code == 200
    assert client.get('/api/stats').status_code == 200
    assert client.get('/api/stats', headers={'Cookie': 'lens_auth=' + old_cookie}).status_code == 401
    assert client.post('/api/auth/login', json={'password': 'test-password-12345'}).status_code == 401
    assert client.post('/api/auth/login', json={'password': 'changed-password-12345'}).status_code == 200


def test_wrong_current_password_and_cross_origin_cannot_change_credentials(client):
    request = {'current_password': 'wrong-password-123', 'new_password': 'changed-password-12345'}
    assert client.post('/api/auth/password', json=request).status_code == 401
    request['current_password'] = 'test-password-12345'
    assert client.post('/api/auth/password', json=request, headers={'Origin': 'https://attacker.example'}).status_code == 403
    assert client.post('/api/auth/login', json={'password': 'test-password-12345'}).status_code == 200


def obsolete_jobs():
    with Session.begin() as db:
        db.add(Batch(id='batch')); db.flush()
        db.add(ImageRecord(id='image', batch_id='batch', filename='shot.png', path='unused', sha256='a' * 64))
        db.add(Job(id='old', kind='computer_use', status='failed', payload={'image_id': 'image'}, finished_at='2026-01-01'))
        db.add(Job(id='new', kind='research', status='completed', payload={'image_id': 'image'})); db.flush()
        db.add(ImageResearch(image_id='image', job_id='new', status='completed'))


def test_retrying_obsolete_research_cannot_reset_newer_results(client):
    obsolete_jobs()
    assert client.post('/api/jobs/old/retry').status_code == 409
    with Session() as db:
        assert db.get(Job, 'old').status == 'failed'
        assert db.get(ImageResearch, 'image').job_id == 'new'
        assert db.get(ImageResearch, 'image').status == 'completed'


def test_stale_browser_result_is_cancelled_before_collection(client, monkeypatch):
    from app.computer_research import run_collection
    obsolete_jobs()
    def forbidden(*a, **kw):
        raise AssertionError('Stale results cannot call GitHub or update projects')
    monkeypatch.setattr('app.jobs.collect_repo', forbidden)
    with Session() as db:
        job = db.get(Job, 'old')
    run_collection(job)
    with Session() as db:
        assert db.get(Job, 'old').status == 'cancelled'
        assert db.get(ImageResearch, 'image').status == 'completed'


def test_list_projections_exclude_large_documents_and_batch_queries_are_constant(client):
    marker = 'large-source-marker-' * 5000
    with Session.begin() as db:
        db.add(Repository(id=1, full_name='owner/repo', collected=True, readme=marker,
                          metadata_json={'html_url': 'https://github.com/owner/repo', 'topics': ['ocr'], 'web_evidence': marker}))
        db.add(Job(id='reported', kind='collect', payload={'full_name': 'owner/repo', 'report': marker}))
        for i in range(5):
            db.add(Batch(id=f'b{i}'))
        db.flush()
        for i in range(5):
            db.add(ImageRecord(id=f'i{i}', batch_id=f'b{i}', filename='shot.png', sha256='a' * 64, path='unused', text=marker,
                               candidates=[{'full_name': 'owner/repo', 'confirmed': True, 'summary': marker, 'metadata': marker}]))
    statements = []
    def observe(conn, cursor, statement, *args):
        statements.append(statement)
    event.listen(engine, 'before_cursor_execute', observe)
    try:
        projects = client.get('/api/projects')
        jobs = client.get('/api/jobs')
        statements.clear()
        batches = client.get('/api/import-batches')
        assert len(statements) <= 6
    finally:
        event.remove(engine, 'before_cursor_execute', observe)
    assert marker not in projects.text and marker not in jobs.text and marker not in batches.text
    assert batches.json()[0]['images'][0]['candidates'][0]['confirmed']
    assert client.get('/api/recognitions/i0/research').json()['image']['text'] == marker


def test_failed_refresh_preserves_previous_chinese_summary_and_personal_data(client, monkeypatch):
    from app.jobs import collect_repo
    def claim(text):
        return {'text': text, 'quote': 'Translate academic papers.', 'source': 'https://github.com/owner/repo'}
    previous = {'mode': 'ai', 'overview': claim('用于翻译论文的资料工具'), 'functions': [claim('翻译学术论文')], 'use_cases': [claim('用于阅读外语论文')]}
    with Session.begin() as db:
        db.add(Repository(id=1, full_name='owner/repo', collected=True, summary=previous, notes='keep', tags=['mine']))
    monkeypatch.setattr('app.jobs.build_summary', lambda *a, **kw: {'mode': 'source', 'overview': {'text': 'English fallback'}, 'generated_at': '2026-11-03'})
    monkeypatch.setattr('app.github.GitHub.bundle', lambda *a: ({'id': 1, 'full_name': 'owner/repo', 'description': 'Updated', 'html_url': 'https://github.com/owner/repo'}, 'Updated README.', {'readme_url': 'https://github.com/owner/repo#readme'}))
    collect_repo('owner/repo', force=True)
    with Session() as db:
        repo = db.get(Repository, 1)
        assert summary_health(repo.summary)['complete']
        assert repo.summary['overview'] == previous['overview']
        assert '保留' in repo.summary['refresh_notice']
        assert repo.readme == 'Updated README.' and repo.notes == 'keep' and repo.tags == ['mine']


def test_missing_or_external_image_paths_return_404(client, tmp_path):
    outside = tmp_path / 'private.txt'; outside.write_text('not an image')
    with Session.begin() as db:
        db.add(Batch(id='batch')); db.flush()
        db.add(ImageRecord(id='missing', batch_id='batch', filename='missing.png', sha256='a' * 64, path=str(outside)))
    assert client.get('/api/images/missing/file').status_code == 404


def test_qr_address_rejects_query_and_fragment(client):
    for value in ('http://testserver?tracking=x', 'http://testserver/#wrong-fragment'):
        assert client.post('/api/upload-sessions', json={'base_url': value}).status_code == 422
