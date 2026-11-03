import httpx
import pytest
from dotenv import dotenv_values
from app.config import settings
from app.github import GitHub
from app import github_settings
from app.db import Session
from app.models import Job

FAKE_TOKEN = 'github_pat_test_only_not_a_real_credential_12345'
RATES = {'core': {'limit': 5000, 'remaining': 4999, 'reset': 2000000000},
         'search': {'limit': 30, 'remaining': 29, 'reset': 2000000000}}


@pytest.fixture
def token_setup(client, tmp_path, monkeypatch):
    path = tmp_path / '.env'
    path.write_text('AI_API_KEY=keep-test-value\nGITHUB_TOKEN=\nADMIN_PASSWORD=keep-test-password\n', encoding='utf-8')
    monkeypatch.setattr(github_settings, 'CONFIG_PATH', path)
    monkeypatch.setattr(settings, 'github_token', '')
    return client, path


def transport(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(github_settings.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(handler)))


def test_token_is_verified_persisted_and_immediately_used_without_echo(token_setup, monkeypatch):
    client, path = token_setup
    with Session.begin() as db:
        db.add(Job(id='github-wait', kind='discovery', payload={}, status='queued', available_at='2099-01-01T00:00:00+00:00', error='GitHub 请求受限'))
        db.add(Job(id='other-wait', kind='discovery', payload={}, status='queued', available_at='2099-01-01T00:00:00+00:00', error='DeepSeek 请求受限'))
    def handler(request):
        assert str(request.url) == 'https://api.github.com/rate_limit'
        assert request.headers['authorization'] == 'Bearer ' + FAKE_TOKEN
        return httpx.Response(200, json={'resources': RATES})
    with monkeypatch.context() as patch:
        transport(patch, handler)
        result = client.post('/api/settings/github-token', json={'token': FAKE_TOKEN})
    assert result.status_code == 200
    assert FAKE_TOKEN not in result.text
    assert result.json()['rate_limit'] == RATES
    assert result.json()['resumed_jobs'] == 1
    with Session() as db:
        assert db.get(Job, 'github-wait').available_at < '2099'
        assert db.get(Job, 'other-wait').available_at.startswith('2099')
    saved = dotenv_values(path)
    assert saved['GITHUB_TOKEN'] == FAKE_TOKEN
    assert saved['AI_API_KEY'] == 'keep-test-value' and saved['ADMIN_PASSWORD'] == 'keep-test-password'
    assert client.get('/api/settings').json()['github_authenticated']
    assert FAKE_TOKEN not in client.get('/api/settings').text
    with GitHub() as api:
        assert api.client.headers['authorization'] == 'Bearer ' + FAKE_TOKEN


@pytest.mark.parametrize('status', [401, 429, 500])
def test_failed_verification_preserves_file_and_existing_token(token_setup, monkeypatch, status):
    client, path = token_setup
    monkeypatch.setattr(settings, 'github_token', 'existing-test-token')
    before = path.read_bytes()
    transport(monkeypatch, lambda request: httpx.Response(status, json={'message': FAKE_TOKEN}))
    result = client.post('/api/settings/github-token', json={'token': FAKE_TOKEN})
    assert result.status_code in (422, 429, 502)
    assert FAKE_TOKEN not in result.text
    assert path.read_bytes() == before
    assert settings.github_token == 'existing-test-token'


def test_token_configuration_is_private_and_rejects_header_injection(token_setup):
    client, path = token_setup
    before = path.read_bytes()
    result = client.post('/api/settings/github-token', json={'token': FAKE_TOKEN + '\nInjected: value'})
    assert result.status_code == 422 and FAKE_TOKEN not in result.text
    assert path.read_bytes() == before
    client.post('/api/auth/logout')
    assert client.post('/api/settings/github-token', json={'token': FAKE_TOKEN}).status_code == 401
