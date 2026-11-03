import base64
from datetime import datetime, timezone
from uuid import uuid4
import httpx
import pytest
from app.github import GitHub, extract_repos, normalize_repo, ServiceError
from app.jobs import upsert_repo, collect_repo, run_job
from app.db import Session
from app.models import ImageRecord, ImageLink, Job, Repository, Snapshot, Batch


def test_extract_and_normalize():
    result = extract_repos('链接 https://github.com/PaddlePaddle/PaddleOCR 。 另一个 foo/bar')
    assert result[0]['full_name'] == 'PaddlePaddle/PaddleOCR' and result[0]['auto']
    assert result[1]['full_name'] == 'foo/bar' and not result[1]['auto']
    assert normalize_repo('https://github.com/owner/repo/tree/main') == 'owner/repo'
    assert normalize_repo('owner/repo.git') == 'owner/repo'
    with pytest.raises(ValueError):
        normalize_repo('https://github.com.evil.example/owner/repo')


def github_transport(request):
    if request.url.path.endswith('/readme'):
        return httpx.Response(200, json={'content': base64.b64encode(b'# Test project').decode(), 'sha': 'abc', 'html_url': 'https://github.com/owner/repo/blob/main/README.md'})
    if request.url.path.endswith('/releases'):
        return httpx.Response(200, json=[{'tag_name': 'v3-rc', 'published_at': '2025-01-01T00:00:00Z', 'prerelease': True}, {'tag_name': 'v2', 'published_at': '2024-01-01T00:00:00Z'}, {'tag_name': 'v1', 'published_at': '2023-01-01T00:00:00Z'}])
    return httpx.Response(200, json={'id': 1, 'full_name': 'owner/repo', 'html_url': 'https://github.com/owner/repo', 'created_at': '2022-01-01T00:00:00Z'})


def test_release_dates_exclude_prereleases_and_use_published_at():
    with GitHub() as api:
        api.client.close()
        api.client = httpx.Client(transport=httpx.MockTransport(github_transport), base_url='https://api.github.com')
        repo, readme, meta = api.bundle('owner/repo')
        assert meta['first_release']['tag_name'] == 'v1'
        assert meta['latest_release']['tag_name'] == 'v2'
        assert meta['first_release']['published_at'] != repo['created_at']
        assert readme == '# Test project'


def test_no_releases_not_filled_with_created_date():
    def transport(request):
        if request.url.path.endswith('/releases'):
            return httpx.Response(200, json=[])
        return github_transport(request)
    with GitHub() as api:
        api.client.close()
        api.client = httpx.Client(transport=httpx.MockTransport(transport), base_url='https://api.github.com')
        _, _, meta = api.bundle('owner/repo')
        assert meta['first_release'] is None and meta['latest_release'] is None


def test_stable_repo_id_and_daily_snapshot_dedup(client):
    with Session.begin() as db:
        upsert_repo(db, {'id': 88, 'full_name': 'old/name', 'stargazers_count': 10}, True)
    with Session.begin() as db:
        upsert_repo(db, {'id': 88, 'full_name': 'new/name', 'stargazers_count': 20})
    with Session() as db:
        assert db.get(Repository, 88).full_name == 'new/name'
        assert db.get(Repository, 88).collected
        assert db.query(Snapshot).filter_by(repo_id=88).count() == 1


def test_collect_preserves_personal_data_and_links_idempotently(client, monkeypatch):
    monkeypatch.setattr(GitHub, 'bundle', lambda *args: ({'id': 55, 'full_name': 'owner/repo', 'description': 'updated', 'html_url': 'https://github.com/owner/repo'}, '# README', {'readme_url': 'https://github.com/owner/repo#readme'}))
    with Session.begin() as db:
        db.add(Repository(id=55, full_name='owner/repo', notes='keep', favorite=True, tags=['mine']))
        db.add(Batch(id='batch'))
        db.flush()
        db.add(ImageRecord(id='image', batch_id='batch', filename='test.png', sha256='a'*64, path='unused'))
    collect_repo('owner/repo', 'image', True)
    collect_repo('owner/repo', 'image', True)
    with Session() as db:
        repo = db.get(Repository, 55)
        assert repo.notes == 'keep' and repo.tags == ['mine'] and repo.favorite
        assert db.query(ImageLink).count() == 1


def test_retryable_jobs_remain_durable(client, monkeypatch):
    def fail(*args, **kwargs):
        raise ServiceError('rate limited', True, 60)
    monkeypatch.setattr('app.jobs.collect_repo', fail)
    with Session.begin() as db:
        db.add(Job(id='job', kind='collect', payload={'full_name': 'owner/repo'}, status='running', attempts=1))
    run_job('job')
    with Session() as db:
        job = db.get(Job, 'job')
        assert job.status == 'queued' and job.error == 'rate limited'
        assert datetime.fromisoformat(job.available_at) > datetime.now(timezone.utc)


def test_ai_discards_unverifiable_claims(client, monkeypatch):
    import app.summary as module
    from app.config import settings
    monkeypatch.setattr(settings, 'ai_base_url', 'https://provider.invalid/v1')
    monkeypatch.setattr(settings, 'ai_api_key', 'test')
    monkeypatch.setattr(settings, 'ai_model', 'test-model')
    real_client = httpx.Client
    def transport(request):
        return httpx.Response(200, json={'choices': [{'message': {'content': __import__('json').dumps({
            'overview': {'text': '一个真实的工具', 'quote': 'A real toolkit', 'source': 'description'},
            'functions': [{'text': '可被验证', 'quote': 'Extract text from images', 'source': 'readme'}, {'text': '虚构功能', 'quote': 'An invented capability', 'source': 'readme'}],
            'innovations': [], 'use_cases': [], 'requirements': []})}}]})
    monkeypatch.setattr(module.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(transport)))
    result = module.build_summary({'description': 'A real toolkit', 'html_url': 'https://github.com/owner/repo'}, 'Extract text from images', 'https://github.com/owner/repo#readme')
    assert result['mode'] == 'ai' and len(result['functions']) == 1
    assert result['functions'][0]['text'] == '可被验证'
