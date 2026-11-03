from datetime import datetime, timedelta, timezone
import pytest
from app.config import settings
from app.db import Session
from app.models import Batch, ImageRecord, ImageResearch, Job, Repository, ImageLink
from app.jobs import run_job

URL = 'https://github.com/owner/tv'
README = '# Features\n- Disable unwanted TV apps over Wi-Fi.\n\n# Why this tool\n- Reversible changes without root access.\n\n# Supported devices\n- Android TV and Google TV devices.\n\n# Requirements\n- An Android TV with network access.\n'


@pytest.fixture
def computer_ready(client, monkeypatch):
    monkeypatch.setattr(settings, 'research_backend', 'computer_use')
    def forbidden(*args, **kwargs):
        raise AssertionError('Computer-use research must not invoke a search API or model')
    monkeypatch.setattr('app.research.search_web', forbidden)
    monkeypatch.setattr('app.research.inspect_image', forbidden)
    monkeypatch.setattr('app.github.GitHub.search', forbidden)
    with Session.begin() as db:
        db.add(Batch(id='batch'))
        db.add(Repository(id=900, full_name='owner/tv', readme=README, description='TV cleanup over Wi-Fi', collected=True,
                          notes='my note', tags=['TV'], favorite=True, metadata_json={'html_url': URL, 'readme_url': URL + '#readme'},
                          summary={'mode': 'source', 'functions': [], 'notice': 'AI 生成失败'}))
        db.flush()
        db.add(ImageRecord(id='image', batch_id='batch', filename='tv.png', path='unused.png', sha256='a'*64,
                           status='needs_review', text='A television cleanup project', candidates=[{'full_name': 'owner/tv', 'confirmed': False}]))
    return client


def result():
    return {'executor': 'computer_use', 'sources': [{'url': URL, 'title': 'TV project', 'role': 'repository',
            'content': 'TV cleanup over Wi-Fi. Disable unwanted TV apps over Wi-Fi. Reversible changes without root access.'}],
            'projects': [{'full_name': 'owner/tv', 'source_urls': [URL], 'summary': {
                'overview': {'text': '通过无线网络清理电视应用', 'quote': 'TV cleanup over Wi-Fi', 'source': URL},
                'functions': [{'text': '禁用不需要的电视应用', 'quote': 'Disable unwanted TV apps over Wi-Fi.', 'source': 'readme'},
                              {'text': '没有来源的能力应丢弃', 'quote': 'An unsupported feature', 'source': URL}],
                'innovations': [{'text': '资料归纳：无需 root，可恢复变更', 'quote': 'Reversible changes without root access.', 'source': URL}]}}]}


def claim_image(client, auto=True):
    route = 'auto-confirm' if auto else 'research'
    job_id = client.post(f'/api/recognitions/image/{route}').json()['job_id']
    receipt = client.post('/api/computer-use/claim', json={'job_id': job_id}).json()
    return job_id, receipt['lease']


def test_research_waits_for_real_executor_without_network_fallback(computer_ready):
    client = computer_ready
    first = client.post('/api/recognitions/image/research').json()['job_id']
    assert client.post('/api/recognitions/image/research').json()['job_id'] == first
    state = client.get('/api/recognitions/image/research').json()
    assert state['provider'] == 'computer_use'
    assert state['research']['status'] == 'waiting_browser'
    assert state['research']['report']['projects'] == []
    assert state['execution']['requires_desktop_session']
    assert client.post('/api/recognitions/image/confirm', json={'full_name': 'owner/tv'}).status_code == 409
    assert client.post('/api/recognitions/image/ignore').status_code == 409
    assert client.get('/api/stats').json()['pending'] == 1
    run_job(first)
    assert client.get('/api/recognitions/image/research').json()['research']['status'] == 'waiting_browser'


def test_results_are_validated_saved_and_auto_associated_idempotently(computer_ready):
    client = computer_ready
    job_id, lease = claim_image(client)
    assert client.post('/api/computer-use/claim', json={}).json()['task'] is None
    payload = {'lease': lease, 'result': result()}
    assert client.post(f'/api/computer-use/jobs/{job_id}/complete', json=payload).status_code == 200
    assert client.post(f'/api/computer-use/jobs/{job_id}/complete', json=payload).json()['duplicate']
    run_job(job_id)
    assert client.post(f'/api/computer-use/jobs/{job_id}/complete', json=payload).json()['duplicate']
    data = client.get('/api/projects/900').json()
    assert data['summary']['mode'] == 'computer_use'
    assert data['summary']['functions'] == [{'text': '禁用不需要的电视应用', 'quote': 'Disable unwanted TV apps over Wi-Fi.', 'source': URL + '#readme'}]
    assert data['notes'] == 'my note' and data['tags'] == ['TV'] and data['favorite']
    assert data['summary']['web_sources'][0]['url'] == URL
    assert client.get('/api/recognitions/image/research').json()['image']['status'] == 'completed'
    with Session() as db:
        assert db.query(ImageLink).filter_by(image_id='image', repo_id=900).count() == 1


def test_manual_browser_research_prepares_candidate_until_user_confirms(computer_ready):
    client = computer_ready
    job_id, lease = claim_image(client, auto=False)
    assert client.post(f'/api/computer-use/jobs/{job_id}/complete', json={'lease': lease, 'result': result()}).status_code == 200
    run_job(job_id)
    state = client.get('/api/recognitions/image/research').json()['image']
    assert state['status'] == 'needs_review' and state['candidates'][0]['full_name'] == 'owner/tv'
    with Session() as db:
        assert db.query(ImageLink).count() == 0


def test_expired_lease_is_reclaimed_and_old_executor_cannot_overwrite(computer_ready):
    client = computer_ready
    job_id, old_lease = claim_image(client)
    with Session.begin() as db:
        db.get(Job, job_id).available_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    assert client.get('/api/computer-use/queue').json()['tasks'][0]['status'] == 'waiting_browser'
    new_lease = client.post('/api/computer-use/claim', json={'job_id': job_id}).json()['lease']
    assert old_lease != new_lease
    assert client.post(f'/api/computer-use/jobs/{job_id}/complete', json={'lease': old_lease, 'result': result()}).status_code == 409
    assert client.post(f'/api/computer-use/jobs/{job_id}/heartbeat', json={'lease': new_lease}).status_code == 200
    assert client.post(f'/api/computer-use/jobs/{job_id}/cancel').status_code == 200
    assert client.post(f'/api/computer-use/jobs/{job_id}/complete', json={'lease': new_lease, 'result': result()}).status_code == 409


def test_repository_page_evidence_and_admin_login_are_required(computer_ready):
    client = computer_ready
    job_id, lease = claim_image(client)
    invalid = result()
    invalid['sources'][0]['role'] = 'search'
    assert client.post(f'/api/computer-use/jobs/{job_id}/complete', json={'lease': lease, 'result': invalid}).status_code == 422
    assert lease not in client.get('/api/computer-use/queue').text
    client.post('/api/auth/logout')
    assert client.get('/api/computer-use/queue').status_code == 401
    assert client.post('/api/computer-use/claim', json={}).status_code == 401


def test_historical_empty_details_show_readme_content_and_queue_browser_refresh(computer_ready):
    client = computer_ready
    data = client.get('/api/projects/900').json()
    for key in ('functions', 'innovations', 'use_cases', 'requirements'):
        assert data['summary'][key]
        assert all(c['quote'] in README for c in data['summary'][key])
    job_id = client.post('/api/projects/900/refresh').json()['job_id']
    assert client.post('/api/projects/900/refresh').json()['job_id'] == job_id
    assert client.get('/api/projects/900').json()['research_task']['status'] == 'waiting_browser'
    lease = client.post('/api/computer-use/claim', json={'job_id': job_id}).json()['lease']
    assert client.post(f'/api/computer-use/jobs/{job_id}/complete', json={'lease': lease, 'result': result()}).status_code == 200
    run_job(job_id)
    assert client.get('/api/projects/900').json()['summary']['overview']['text'] == '通过无线网络清理电视应用'


def test_document_excerpts_keep_wrapped_sentences_and_render_entities(computer_ready):
    readme = '# Features\nControl the television over Wi-Fi\nwithout a USB cable or root access.\n\n| Step | Action |\n|---|---|\n| Back&amp;nbsp;up | Save the original settings. |\n'
    with Session.begin() as db:
        db.get(Repository, 900).readme = readme
    claims = computer_ready.get('/api/projects/900').json()['summary']['functions']
    assert claims[0]['text'] == 'Control the television over Wi-Fi without a USB cable or root access.'
    assert claims[0]['quote'] in readme
    assert claims[1]['text'] == 'Back up | Save the original settings.'
    assert all(c['quote'] in readme for c in claims)


def test_backend_switch_migrates_legacy_queued_research_without_api_calls(computer_ready):
    client = computer_ready
    with Session.begin() as db:
        db.add(Job(id='legacy', kind='research', status='queued', payload={'image_id': 'image'}))
        db.add(ImageResearch(image_id='image', job_id='legacy', status='queued', report={'sources': [{'url': URL, 'content': 'legacy'}]}))
    run_job('legacy')
    state = client.get('/api/recognitions/image/research').json()['research']
    assert state['status'] == 'waiting_browser'
    assert state['report']['sources'] == []
    assert state['report']['previous_report']['sources']
