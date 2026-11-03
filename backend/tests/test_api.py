from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs
from app.db import Session
from app.models import UploadSession, ImageRecord, Repository


def test_private_api_and_csrf(client):
    assert client.get('/api/stats').status_code == 200
    assert client.post('/api/import-batches', headers={'Origin': 'https://attacker.example'}).status_code == 403
    client.post('/api/auth/logout')
    for path in ('/api/projects', '/api/stats', '/api/jobs', '/api/settings', '/api/export'):
        assert client.get(path).status_code == 401


def test_first_setup_creates_password_and_logout_can_login(client):
    from app.models import Config
    with Session.begin() as db:
        db.delete(db.get(Config, 'admin'))
    client.post('/api/auth/logout')
    assert client.get('/api/auth/status').json()['setup_required']
    assert client.post('/api/auth/setup', json={'password': 'new-test-password-456'}).status_code == 200
    assert not client.get('/api/auth/status').json()['setup_required']
    assert client.post('/api/auth/setup', json={'password': 'other-test-password-789'}).status_code == 409
    client.post('/api/auth/logout')
    assert client.post('/api/auth/login', json={'password': 'new-test-password-456'}).status_code == 200


def test_upload_validation_and_per_file_failure(client, image_bytes):
    batch = client.post('/api/import-batches').json()['id']
    assert client.post(f'/api/import-batches/{batch}/images', files={'file': ('bad.png', b'not an image', 'image/png')}).status_code == 415
    import base64
    broken = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a/jkAAAAASUVORK5CYII=')
    assert client.post(f'/api/import-batches/{batch}/images', files={'file': ('broken.png', broken)}).status_code == 415
    good = client.post(f'/api/import-batches/{batch}/images', files={'file': ('../../safe.png', image_bytes, 'image/png')})
    assert good.status_code == 200
    rows = client.get(f'/api/import-batches/{batch}').json()['images']
    assert len(rows) == 1 and rows[0]['filename'] == 'safe.png'
    assert client.get(f'/api/images/{rows[0]["id"]}/file').content == image_bytes


def test_mobile_session_cannot_read_library_and_can_be_revoked(client, image_bytes):
    desktop_batch = client.post('/api/import-batches').json()['id']
    qr = client.post('/api/upload-sessions', json={'base_url': 'http://testserver'}).json()
    token = parse_qs(urlparse(qr['url']).fragment)['token'][0]
    credential = client.post('/api/upload-sessions/exchange', json={'token': token}).json()['credential']
    assert client.post('/api/upload-sessions/exchange', json={'token': token}).status_code == 401
    admin_cookie = client.cookies.get('lens_auth')
    client.cookies.clear()
    headers = {'X-Upload-Credential': credential}
    assert client.get('/api/projects', headers=headers).status_code == 401
    assert client.get(f'/api/import-batches/{desktop_batch}', headers=headers).status_code == 404
    own = client.post('/api/import-batches', headers=headers).json()['id']
    assert client.post(f'/api/import-batches/{own}/images', headers=headers, files={'file': ('phone.png', image_bytes)}).status_code == 200
    assert client.get(f'/api/import-batches/{own}', headers=headers).status_code == 200
    client.cookies.set('lens_auth', admin_cookie)
    assert client.delete('/api/upload-sessions/' + qr['id']).status_code == 200
    client.cookies.clear()
    assert client.post('/api/import-batches', headers=headers).status_code == 401


def test_expired_mobile_token_rejected(client):
    qr = client.post('/api/upload-sessions', json={'base_url': 'http://testserver'}).json()
    token = parse_qs(urlparse(qr['url']).fragment)['token'][0]
    with Session.begin() as db:
        db.get(UploadSession, qr['id']).expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    assert client.post('/api/upload-sessions/exchange', json={'token': token}).status_code == 401


def test_phone_upload_quota(client, image_bytes):
    qr = client.post('/api/upload-sessions', json={'base_url': 'http://testserver'}).json()
    token = parse_qs(urlparse(qr['url']).fragment)['token'][0]
    credential = client.post('/api/upload-sessions/exchange', json={'token': token}).json()['credential']
    with Session.begin() as db:
        db.get(UploadSession, qr['id']).file_count = 100
    client.cookies.clear()
    headers = {'X-Upload-Credential': credential}
    batch = client.post('/api/import-batches', headers=headers).json()['id']
    assert client.post(f'/api/import-batches/{batch}/images', headers=headers, files={'file': ('over.png', image_bytes)}).status_code == 413


def test_manual_patch_preserves_annotations(client):
    with Session.begin() as db:
        db.add(Repository(id=123, full_name='owner/repo', collected=True, tags=['initial'], notes='my note'))
    updated = client.patch('/api/projects/123', json={'favorite': True, 'tags': ['OCR', 'OCR', '']})
    assert updated.status_code == 200
    assert updated.json()['notes'] == 'my note'
    assert updated.json()['tags'] == ['OCR']
    assert client.get('/api/projects?q=owner').json()['total'] == 1


def test_import_rejects_non_github_hosts(client):
    for value in ('https://evil.example/owner/repo', 'https://github.com@evil.example/owner/repo', 'http://127.0.0.1/secrets'):
        assert client.post('/api/projects/import', json={'full_name': value}).status_code == 422
