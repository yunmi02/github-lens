from pathlib import Path
import httpx
import pytest
from app.config import settings
from app.db import Session
from app.models import Batch, ImageRecord, ImageResearch, Repository, Job
from app.research import ResearchPlan, enqueue_research, search_web, image_blocks
from app.jobs import run_job, maybe_research, collect_repo
from app.github import GitHub, ServiceError


@pytest.fixture
def research_ready(client, monkeypatch, image_bytes, tmp_path):
    monkeypatch.setattr(settings, 'ai_api_key', 'test-key')
    monkeypatch.setattr(settings, 'ai_base_url', 'https://api.deepseek.com')
    monkeypatch.setattr(settings, 'ai_model', 'deepseek-flash')
    path = tmp_path / 'image.png'
    path.write_bytes(image_bytes)
    with Session.begin() as db:
        db.add(Batch(id='batch'))
        db.flush()
        db.add(ImageRecord(id='image', batch_id='batch', filename='image.png', path=str(path), sha256='a'*64, status='needs_review', text='A useful OCR toolkit'))
    return client


def test_research_queue_is_deduplicated_and_private(research_ready):
    client = research_ready
    first = client.post('/api/recognitions/image/research')
    second = client.post('/api/recognitions/image/research')
    assert first.json()['created'] and not second.json()['created']
    assert first.json()['job_id'] == second.json()['job_id']
    assert client.post('/api/recognitions/image/ignore').status_code == 409
    assert client.post('/api/recognitions/image/confirm', json={'full_name':'owner/repo'}).status_code == 409
    client.post('/api/auth/logout')
    assert client.get('/api/recognitions/image/research').status_code == 401
    assert client.post('/api/research-pending').status_code == 401


def test_agent_validates_repo_without_collecting_guess(research_ready, monkeypatch):
    from app import research
    monkeypatch.setattr(research, 'inspect_image', lambda *a: ResearchPlan(observed_text='OCR Toolkit', useful_info=['图片是 OCR 工具介绍'], project_names=['OCR Toolkit'], search_queries=['OCR Toolkit GitHub']))
    monkeypatch.setattr(research, 'search_web', lambda q: [{'title':'Official repo', 'url':'https://github.com/owner/repo', 'content':'Official OCR toolkit, dependency twine/6.1.0', 'summary':'', 'snippet':''}])
    monkeypatch.setattr(GitHub, 'bundle', lambda *a: ({'id':99,'full_name':'owner/repo','description':'Official OCR toolkit','html_url':'https://github.com/owner/repo','stargazers_count':123}, '# Official OCR toolkit', {'readme_url':'https://github.com/owner/repo#readme'}))
    # Keep summaries local to isolate the research plan/search from the summary model.
    monkeypatch.setattr('app.jobs.build_summary', lambda *a: {'mode':'source','overview':{'text':'OCR 工具'},'functions':[]})
    job_id = research_ready.post('/api/recognitions/image/research').json()['job_id']
    run_job(job_id)
    data = research_ready.get('/api/recognitions/image/research').json()
    assert data['research']['status'] == 'completed'
    assert data['research']['report']['projects'][0]['repo_id'] == 99
    assert len(data['research']['report']['projects'])==1
    assert data['image']['status'] == 'needs_review'
    assert not data['image']['candidates'][0]['confirmed']
    with Session() as db:
        assert not db.get(Repository, 99).collected
        assert db.get(Job, job_id).status == 'completed'
    confirmed = research_ready.post('/api/recognitions/image/confirm',json={'full_name':'owner/repo'}).json()['job_id']
    run_job(confirmed)
    with Session() as db:
        assert db.get(Repository,99).collected
    # Re-running research may add suggestions, but cannot undo a saved association.
    again = research_ready.post('/api/recognitions/image/research').json()['job_id']
    run_job(again)
    data = research_ready.get('/api/recognitions/image/research').json()
    assert data['image']['status'] == 'completed'
    assert data['image']['candidates'][0]['confirmed']
    assert data['research']['stage'] == '研究完成，已关联项目'


def test_agent_failure_preserves_image_and_can_retry(research_ready, monkeypatch):
    def fail(*args):
        raise ServiceError('DeepSeek 账户余额不足（HTTP 402）')
    monkeypatch.setattr('app.research.inspect_image',fail)
    job_id=research_ready.post('/api/recognitions/image/research').json()['job_id']
    run_job(job_id)
    data=research_ready.get('/api/recognitions/image/research').json()
    assert data['research']['status']=='failed'
    assert '402' in data['research']['error']
    assert data['image']['text']=='A useful OCR toolkit'
    assert research_ready.post(f'/api/jobs/{job_id}/retry').status_code==200
    assert research_ready.get('/api/recognitions/image/research').json()['research']['status']=='queued'


def test_automatic_pending_handoff_and_batch_dedup(research_ready):
    with Session.begin() as db:
        maybe_research(db,'image')
    assert research_ready.get('/api/recognitions/image/research').json()['image']['status']=='researching'
    assert research_ready.post('/api/research-pending').json()['count']==0
    with Session() as db:
        assert db.query(Job).filter_by(kind='auto_confirm').count()==1


def test_search_uses_official_endpoint_and_filters_unsafe_urls(client, monkeypatch):
    from app import research
    monkeypatch.setattr(settings,'ai_base_url','https://api.deepseek.com/v1')
    monkeypatch.setattr(settings,'ai_search_base_url','')
    monkeypatch.setattr(settings,'ai_api_key','test')
    captured=[]
    def post(url,body):
        captured.append((url,body))
        return {'results':[{'title':'valid','url':'https://github.com/owner/repo'}, {'url':'javascript:alert(1)'}, {'url':'https://user:pass@bad.example/'}]}
    monkeypatch.setattr(research,'post_json',post)
    assert len(search_web('OCR GitHub'))==1
    assert captured[0][0]=='https://api.deepseek.com/v1/tools/search'
    assert captured[0][1]['need_content'] is True


def test_missing_configuration_and_missing_image(client):
    assert client.post('/api/research-pending').status_code==422
    assert client.get('/api/recognitions/missing/research').status_code==404


def test_search_budget_is_enforced(client,monkeypatch):
    monkeypatch.setattr(settings,'ai_base_url','https://api.deepseek.com')
    monkeypatch.setattr(settings,'agent_search_daily_limit',0)
    with pytest.raises(ServiceError,match='额度'):
        search_web('OCR GitHub')


def test_image_encoding_is_bounded(image_bytes,tmp_path):
    path=tmp_path/'test.png'
    path.write_bytes(image_bytes)
    blocks=image_blocks(path)
    assert len(blocks)==1 and blocks[0]['image_url']['url'].startswith('data:image/jpeg;base64,')


def test_model_text_lines_can_be_normalized_without_inventing_content():
    plan=ResearchPlan.model_validate({'observed_text':['PaddleOCR','OCR toolkit']})
    assert plan.observed_text=='PaddleOCR\nOCR toolkit'
