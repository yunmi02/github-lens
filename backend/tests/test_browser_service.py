import asyncio
import threading
import httpx
import pytest
from app.config import settings
from app.db import Session
from app.models import Repository, Job, Config, Batch, ImageRecord
from app.jobs import run_job
from app.computer_research import ClaimRequest, claim, executor_state
from app.browser_service import BrowserService, BrowserReader, BrowserBlocked, research_task, release, public_url, health, model_json, search_queries
from app.research import ResearchPlan


def queued(client, monkeypatch):
    monkeypatch.setattr(settings, 'research_backend', 'browser')
    with Session.begin() as db:
        db.add(Repository(id=900, full_name='owner/tv', collected=True, readme='Disable unwanted TV apps over Wi-Fi.',
                          description='TV cleanup', metadata_json={'html_url': 'https://github.com/owner/tv', 'readme_url': 'https://github.com/owner/tv#readme'}))
    job_id = client.post('/api/projects/900/refresh').json()['job_id']
    return job_id, claim(ClaimRequest(job_id=job_id, executor='browser_service'))


def test_background_browser_result_is_verified_and_labelled_as_the_actual_runtime(client, monkeypatch):
    job_id, receipt = queued(client, monkeypatch)
    def forbidden(*args, **kwargs):
        raise AssertionError('Browser research cannot use search APIs')
    monkeypatch.setattr('app.research.search_web', forbidden)
    monkeypatch.setattr('app.github.GitHub.search', forbidden)
    monkeypatch.setattr('app.jobs.collect_repo', lambda *args, **kwargs: 900)
    monkeypatch.setattr('app.browser_service.model_json', lambda *args: {
        'functions': [{'text': '通过无线网络禁用不需要的电视应用', 'quote': 'Disable unwanted TV apps over Wi-Fi.', 'source': 'https://github.com/owner/tv'},
                      {'text': '无证据的说明', 'quote': 'This claim was invented.', 'source': 'https://github.com/owner/tv'}]})
    class Reader:
        def __init__(self):
            self.sources, self.visited = {}, []
        async def read(self, url, role):
            self.visited.append(url)
            source = {'url': url, 'role': role, 'title': 'TV', 'content': 'Disable unwanted TV apps over Wi-Fi.'}
            self.sources[url] = source
            return source, []
    reader = Reader()
    asyncio.run(research_task(receipt['task'], receipt['lease'], reader))
    assert reader.visited == ['https://github.com/owner/tv', 'https://github.com/owner/tv/releases']
    run_job(job_id)
    with Session() as db:
        repo = db.get(Repository, 900)
        assert db.get(Job, job_id).status == 'completed'
        assert '已核对 1 个项目' in db.get(Job, job_id).stage
        assert repo.summary['mode'] == 'browser'
        assert repo.metadata_json['research_provider'] == 'browser'
        assert len(repo.summary['functions']) == 1
        assert repo.summary['functions'][0]['text'] == '通过无线网络禁用不需要的电视应用'
        assert db.get(Config, 'computer_use_executor') is None


def test_cancelled_browser_job_cannot_be_requeued_by_a_late_error(client, monkeypatch):
    job_id, receipt = queued(client, monkeypatch)
    assert client.post(f'/api/computer-use/jobs/{job_id}/cancel').status_code == 200
    release(job_id, receipt['lease'], 'late timeout', True)
    with Session() as db:
        assert db.get(Job, job_id).status == 'cancelled'


def test_budget_deferral_keeps_task_and_does_not_consume_network_retry_limit(client, monkeypatch):
    job_id, receipt = queued(client, monkeypatch)
    release(job_id, receipt['lease'], 'AI budget exhausted', True, 3600, True)
    with Session() as db:
        job = db.get(Job, job_id)
        assert job.status == 'waiting_browser'
        assert job.stage == '等待 AI 额度恢复'
        assert job.payload['browser_failures'] == 0
    assert claim(ClaimRequest(job_id=job_id, executor='browser_service'))['task'] is None


def test_restarting_service_does_not_exhaust_task_retry_budget(client, monkeypatch):
    job_id, receipt = queued(client, monkeypatch)
    for _ in range(4):
        release(job_id, receipt['lease'], 'Service restarted', True, 0, count_failure=False)
        receipt = claim(ClaimRequest(job_id=job_id, executor='browser_service'))
        assert receipt['task']
    with Session() as db:
        assert db.get(Job, job_id).payload['browser_failures'] == 0


def test_service_health_exposes_offline_and_failure_instead_of_claiming_progress(client, monkeypatch):
    monkeypatch.setattr(settings, 'research_backend', 'browser')
    health('error', error='Chrome unavailable')
    with Session() as db:
        state = executor_state(db)
        assert not state['online'] and not state['requires_desktop_session']
        assert state['error'] == 'Chrome unavailable'
    health('idle')
    assert client.get('/api/browser-service/status').json()['online']


def test_active_browser_tasks_remain_visible_before_recent_completed_history(client, monkeypatch):
    monkeypatch.setattr(settings, 'research_backend', 'browser')
    with Session.begin() as db:
        db.add_all(Job(id=f'history-{i}', kind='collect', status='completed', created_at='2026-11-02T00:00:00Z') for i in range(105))
        db.add(Job(id='active', kind='computer_use', status='browser_running', created_at='2026-10-01T00:00:00Z'))
        db.add(Job(id='waiting', kind='auto_confirm', status='waiting_browser', attempts=3, payload={'provider': 'computer_use'}, created_at='2026-10-01T00:00:00Z'))
    jobs = client.get('/api/jobs').json()
    assert len(jobs) == 100
    assert [j['id'] for j in jobs[:2]] == ['active', 'waiting']
    assert jobs[1]['browser_attempts'] == 0


def test_user_retry_resets_failure_limit_but_preserves_actual_browser_run_count(client, monkeypatch):
    job_id, receipt = queued(client, monkeypatch)
    release(job_id, receipt['lease'], 'network failure')
    with Session.begin() as db:
        job = db.get(Job, job_id)
        job.payload = {**job.payload, 'browser_failures': 3, 'browser_runs': 3}
    assert client.post(f'/api/jobs/{job_id}/retry').status_code == 200
    with Session() as db:
        payload = db.get(Job, job_id).payload
        assert payload['browser_failures'] == 0 and payload['browser_runs'] == 3


def test_model_response_accepts_only_a_complete_json_object_and_ignores_trailing_annotations(client, monkeypatch):
    monkeypatch.setattr('app.browser_service.post_json', lambda *args: {'choices': [{'message': {'content': '{"functions": []}\nSource annotations'}}]})
    assert model_json('Return JSON', {}) == {'functions': []}
    monkeypatch.setattr('app.browser_service.post_json', lambda *args: {'choices': [{'message': {'content': '```json\n\n  {"functions": []}\n```'}}]})
    assert model_json('Return JSON', {}) == {'functions': []}


def test_structured_deepseek_requests_disable_thinking_without_changing_other_providers(client, monkeypatch):
    from app.research import post_json
    requests = []
    def handler(request):
        import json
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'ok': True})
    original = httpx.Client
    monkeypatch.setattr('app.research.httpx.Client', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    payload = {'model': 'deepseek-flash'}
    post_json('https://api.deepseek.com/chat/completions', payload)
    post_json('https://compatible.example/v1/chat/completions', payload)
    post_json('https://api.deepseek.com/v1/tools/search', payload)
    assert requests[0]['thinking'] == {'type': 'disabled'}
    assert 'thinking' not in requests[1] and 'thinking' not in requests[2]
    assert payload == {'model': 'deepseek-flash'}


def test_reader_stops_on_site_verification_without_accepting_a_source(client):
    class Page:
        closed = False
        url = 'https://github.com/owner/tv'
        async def goto(self, *args, **kwargs):
            return type('Response', (), {'status': 200})()
        async def title(self):
            return 'Verify you are human'
        def locator(self, *args):
            return self
        async def inner_text(self, **kwargs):
            return 'Solve the CAPTCHA to continue'
        async def close(self):
            self.closed = True
    page = Page()
    class Context:
        async def new_page(self):
            return page
    reader = BrowserReader(Context(), 'verification')
    with pytest.raises(BrowserBlocked):
        asyncio.run(reader.read(page.url, 'repository'))
    assert page.closed and reader.sources == {}


def test_browser_targets_cannot_navigate_to_local_files_or_private_services():
    for url in ('file:///C:/secret', 'http://github.com/owner/tv', 'https://127.0.0.1', 'https://10.0.0.1', 'https://localhost', 'https://user:pass@github.com', 'https://github.com:8000', 'https://untrusted.example/track'):
        assert not public_url(url)
    assert public_url('https://github.com/owner/tv')


def test_exact_project_name_is_searched_even_if_the_ocr_owner_is_misspelled():
    plan = ResearchPlan(project_names=['esp32-c3-adblock'], repository_hints=['M-Abozad/esp32-c3-adblock'],
                        search_queries=['M-Abozad esp32-c3-adblock', 'esp32-c3-adblock GitHub'])
    queries = search_queries(plan)
    assert queries[0] == 'esp32-c3-adblock'
    assert queries.count('esp32-c3-adblock') == 1


def test_browser_matches_real_search_hit_and_rejects_nonexistent_ocr_hint(client, monkeypatch):
    from app.research import enqueue_research
    monkeypatch.setattr(settings, 'research_backend', 'browser')
    with Session.begin() as db:
        db.add(Batch(id='batch'))
        db.flush()
        image = ImageRecord(id='shot', batch_id='batch', filename='shot.png', path='unused.png', sha256='a' * 64)
        db.add(image)
        db.flush()
        job_id, _ = enqueue_research(db, image, auto_confirm=True)
    receipt = claim(ClaimRequest(job_id=job_id, executor='browser_service'))
    monkeypatch.setattr('app.browser_service.inspect_image', lambda *a: ResearchPlan(project_names=['tv'], repository_hints=['typo/tv']))
    def match(plan, candidates, sources):
        assert candidates == [{'full_name': 'real/tv'}]
        return ['real/tv']
    monkeypatch.setattr('app.auto_confirm.select_web_repositories', match)
    monkeypatch.setattr('app.browser_service.model_json', lambda *a: {})
    class Reader:
        sources = {}
        async def read(self, url, role):
            if url == 'https://github.com/typo/tv':
                return None, []
            source = {'url': url, 'role': role, 'title': 'TV', 'content': 'Official TV project.'}
            self.sources[url] = source
            return source, [{'url': 'https://github.com/real/tv', 'title': 'real/tv'}] if role == 'search' else []
    asyncio.run(research_task(receipt['task'], receipt['lease'], Reader()))
    with Session() as db:
        job = db.get(Job, job_id)
        assert job.status == 'queued'  # Results are ready for metadata import.
        assert [p['full_name'] for p in job.payload['browser_result']['projects']] == ['real/tv']


def test_browser_thread_owns_its_event_loop_and_can_be_stopped(client):
    ready = threading.Event()
    service = BrowserService()
    async def idle():
        ready.set()
        await asyncio.sleep(300)
    service.run = idle
    service.start()
    assert ready.wait(3)
    service.stop()
    assert not service.thread.is_alive()
