import json
import httpx
import pytest
from app.config import settings
from app.db import Session
from app.github import GitHub, ServiceError, extract_repos
from app.jobs import run_job
from app.models import Batch, ImageRecord, ImageLink, ImageResearch, Job, Repository
from app.research import ResearchPlan


@pytest.fixture
def auto_ready(client, monkeypatch):
    monkeypatch.setattr(settings, 'ai_base_url', 'https://api.deepseek.com')
    monkeypatch.setattr(settings, 'ai_api_key', 'test-key')
    monkeypatch.setattr(settings, 'ai_model', 'test-model')
    names = [f'owner/repo{i}' for i in range(18)]
    monkeypatch.setattr('app.research.inspect_image', lambda *a: ResearchPlan(repository_hints=names + ['owner/deleted', 'macOS/Windows']))
    calls = []
    def search(query):
        calls.append(query)
        name = query.split()[0]
        return [{'title': name, 'url': 'https://github.com/' + name, 'content': 'Extract text from images', 'summary': '', 'snippet': ''}]
    monkeypatch.setattr('app.research.search_web', search)
    def bundle(self, name):
        if name == 'owner/deleted':
            raise ServiceError('未找到公开仓库')
        return ({'id': 100+int(name.split('repo')[-1]), 'full_name': name, 'html_url': 'https://github.com/' + name,
                 'description': 'Extract text from images'}, '# Extract text from images', {'readme_url': 'https://github.com/' + name + '#readme'})
    monkeypatch.setattr(GitHub, 'bundle', bundle)
    def summarize(repo, readme, source, web_sources=None, allow_ai=True):
        return {'mode': 'ai' if allow_ai else 'source', 'overview': {'text': '图片文字工具'}, 'functions': [],
                'web_sources': [{'title': s['title'], 'url': s['url']} for s in web_sources or []]}
    monkeypatch.setattr('app.jobs.build_summary', summarize)
    with Session.begin() as db:
        db.add(Batch(id='batch'))
        db.add(Repository(id=100, full_name='owner/repo0', notes='keep my notes', tags=['mine'], favorite=True))
        db.flush()
        db.add(ImageRecord(id='image', batch_id='batch', filename='all-projects.png', sha256='a'*64, path='unused',
                           status='needs_review', text='macOS/Windows', candidates=[{'full_name': 'macOS/Windows', 'confirmed': False}]))
    return client, calls


def test_auto_confirms_all_projects_without_old_limits_and_skips_invalid(auto_ready):
    client, calls = auto_ready
    first = client.post('/api/recognitions/image/auto-confirm').json()
    assert client.post('/api/recognitions/image/auto-confirm').json()['job_id'] == first['job_id']
    assert client.post('/api/recognitions/image/confirm', json={'full_name': 'owner/repo0'}).status_code == 409
    run_job(first['job_id'])
    state = client.get('/api/recognitions/image/research').json()
    assert state['image']['status'] == 'completed'
    assert sum(c.get('confirmed', False) for c in state['image']['candidates']) == 18
    assert state['research']['report']['confirmed_count'] == 18
    assert state['research']['report']['rejected']['macos/windows']
    assert state['research']['report']['outcomes']['owner/deleted']['status'] == 'failed'
    assert len(calls) == 18
    with Session() as db:
        assert db.query(ImageLink).count() == 18
        assert db.query(Repository).filter_by(collected=True).count() == 18
        assert all(r.summary['web_sources'] for r in db.query(Repository))
        saved = db.get(Repository, 100)
        assert saved.notes == 'keep my notes' and saved.tags == ['mine'] and saved.favorite
        assert saved.metadata_json['web_evidence']
    run_job(first['job_id'])
    assert len(calls) == 18
    assert client.get('/api/stats').json()['needs_review'] == 0


def test_quota_wait_preserves_completed_projects_and_resumes_without_duplicates(auto_ready, monkeypatch):
    client, calls = auto_ready
    from app import research
    real_search = research.search_web
    def quota(query):
        if query.startswith('owner/repo1 '):
            raise ServiceError('今日智能体联网搜索额度已用完')
        return real_search(query)
    monkeypatch.setattr(research, 'search_web', quota)
    job_id = client.post('/api/recognitions/image/auto-confirm').json()['job_id']
    with Session.begin() as db:
        db.get(Job, job_id).attempts = 5
    run_job(job_id)
    with Session() as db:
        assert db.get(Job, job_id).status == 'queued'
        assert db.get(ImageResearch, 'image').report['outcomes']['owner/repo0']['status'] == 'completed'
        assert db.query(ImageLink).count() == 2
    monkeypatch.setattr(research, 'search_web', real_search)
    run_job(job_id)
    with Session() as db:
        assert db.get(Job, job_id).status == 'completed'
        assert db.query(ImageLink).count() == 18
    assert sum(c.startswith('owner/repo0 ') for c in calls) == 1


def test_auto_routes_require_admin_and_upgrade_queued_research(auto_ready):
    client, _ = auto_ready
    original = client.post('/api/recognitions/image/research').json()['job_id']
    assert client.post('/api/recognitions/image/auto-confirm').json()['job_id'] == original
    with Session() as db:
        assert db.get(Job, original).kind == 'auto_confirm'
    assert client.post('/api/auto-confirm-pending').json()['count'] == 0
    assert client.post('/api/recognitions/missing/auto-confirm').status_code == 404
    client.post('/api/auth/logout')
    assert client.post('/api/recognitions/image/auto-confirm').status_code == 401
    assert client.post('/api/auto-confirm-pending').status_code == 401


def test_extract_does_not_drop_projects_after_tenth_item():
    assert len(extract_repos(' '.join(f'https://github.com/owner/repo{i}' for i in range(25)))) == 25


def test_web_matching_cannot_invent_repository_names(auto_ready, monkeypatch):
    from app.auto_confirm import select_web_repositories
    monkeypatch.setattr('app.research.post_json', lambda *a: {'choices': [{'message': {'content': json.dumps({'full_names': ['owner/real', 'invented/project']})}}]})
    assert select_web_repositories(ResearchPlan(project_names=['Real']), [{'full_name': 'owner/real'}], []) == ['owner/real']


def test_search_summary_claims_require_quotes_from_provided_sources(client, monkeypatch):
    import app.summary as module
    monkeypatch.setattr(settings, 'ai_base_url', 'https://api.deepseek.com')
    monkeypatch.setattr(settings, 'ai_api_key', 'test')
    monkeypatch.setattr(settings, 'ai_model', 'test')
    real_client = httpx.Client
    url = 'https://docs.example/project'
    def transport(request):
        parsed = {'overview': {'text': '图片工具', 'quote': 'Extract text from images', 'source': 'description'},
                  'functions': [{'text': '搜索补全的真实功能', 'quote': 'Supports batch documents', 'source': url},
                                {'text': '不能引用未提供网页', 'quote': 'Supports batch documents', 'source': 'https://invented.example'}],
                  'innovations': [], 'use_cases': [], 'requirements': [],
                  'date_facts': [{'text': 'v1 于 2024 年发布', 'quote': 'v1 released on 2024-01-01', 'source': url}]}
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(parsed)}}]})
    monkeypatch.setattr(module.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(transport)))
    summary = module.build_summary({'full_name': 'owner/repo', 'html_url': 'https://github.com/owner/repo',
                                    'description': 'Extract text from images'}, 'README toolkit', 'https://github.com/owner/repo#readme',
                                   web_sources=[{'url': url, 'title': 'Project docs', 'content': 'Supports batch documents. v1 released on 2024-01-01'}])
    assert summary['mode'] == 'ai'
    assert len(summary['functions']) == 1 and summary['functions'][0]['source'] == url
    assert len(summary['date_facts']) == 1
    assert summary['web_sources'] == [{'url': url, 'title': 'Project docs'}]


def test_many_summary_claims_do_not_discard_other_valid_information():
    from app.summary import SummarySchema
    valid = {'text': '有依据的功能', 'quote': 'Extract text from images', 'source': 'readme'}
    parsed = SummarySchema.model_validate({'overview': None, 'innovations': [valid] * 12 + [{'text': '无引用'}], 'date_facts': [valid] * 15})
    assert parsed.overview is None
    assert len(parsed.innovations) == 12
    assert len(parsed.date_facts) == 15
