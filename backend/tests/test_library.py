import pytest
from app.db import Session
from app.models import Repository, ProjectOrganization, ProjectTrash, Job
from app.library import save_organization, search_score, organization
from app.curation import run_curation
from app.github import ServiceError
from app.config import settings


def claim(text):
    return {'text': text, 'quote': 'Translate academic papers into Chinese.', 'source': 'https://github.com/owner/papers'}


@pytest.fixture
def library(client):
    with Session.begin() as db:
        first = Repository(id=1, full_name='owner/papers', description='An academic toolkit', language='Python', collected=True,
            notes='保留我的笔记', tags=['待读'], metadata_json={'topics': None},
            summary={'mode': 'browser', 'functions': [claim('将论文翻译成中文并保留公式')], 'use_cases': [claim('适合阅读外语学术论文')]})
        second = Repository(id=2, full_name='owner/video', description='A video editor', language='TypeScript', collected=True)
        removed = Repository(id=3, full_name='owner/trashed', description='Hidden paper translator', collected=True)
        db.add_all([first, second, removed]); db.flush()
        save_organization(db, first, {'categories': ['research', 'documents'], 'keywords': ['论文翻译', 'LaTeX'], 'method': 'ai'})
        save_organization(db, second, {'categories': ['video'], 'keywords': ['视频剪辑', 'video editing'], 'method': 'ai'})
        db.add(ProjectTrash(repo_id=3))
    return client


def test_search_uses_chinese_claims_keywords_and_multiterm_queries(library):
    data = library.get('/api/projects', params={'q': '论文 公式', 'sort': 'relevance'}).json()
    assert [r['id'] for r in data['items']] == [1]
    assert data['items'][0]['display_description'].startswith('功能概述：')
    assert data['items'][0]['summary_health']['complete']
    assert library.get('/api/projects', params={'q': 'LaTeX'}).json()['total'] == 1
    assert library.get('/api/projects', params={'q': '视频剪辑'}).json()['items'][0]['id'] == 2
    assert library.get('/api/projects', params={'q': 'paper', 'trash': True}).json()['items'][0]['id'] == 3


def test_category_filters_facets_and_language_combine_without_trash_leaks(library):
    data = library.get('/api/projects', params={'category': 'research', 'language': 'Python'}).json()
    assert data['total'] == 1 and data['items'][0]['categories'] == ['research', 'documents']
    facets = {c['id']: c['count'] for c in data['categories']}
    assert facets['research'] == 1 and facets['video'] == 0
    pending = library.get('/api/projects', params={'summary_state': 'pending'}).json()['items'][0]
    assert pending['id'] == 2 and '中文' in pending['display_description']


def test_equivalent_search_terms_do_not_expand_to_every_project_in_a_broad_category(library):
    with Session.begin() as db:
        db.add(Repository(id=4, full_name='owner/reader', description='OCR document parser', collected=True))
    data = library.get('/api/projects', params={'q': '文字识别', 'sort': 'relevance'}).json()
    assert [r['id'] for r in data['items']] == [4]
    # Sharing the documents category does not make a paper translator an OCR tool.
    assert library.get('/api/projects', params={'q': 'OCR'}).json()['total'] == 1


def test_project_list_is_compact_but_detail_and_export_keep_source_evidence(library):
    with Session.begin() as db:
        repo = db.get(Repository, 1)
        repo.metadata_json = {**repo.metadata_json, 'web_evidence': [{'url': 'https://github.com/owner/papers', 'content': 'Saved original text'}]}
    listed = library.get('/api/projects').json()['items'][0]
    assert 'web_evidence' not in listed['metadata']
    assert library.get('/api/projects/1').json()['metadata']['web_evidence'][0]['content'] == 'Saved original text'
    exported = library.get('/api/export').json()
    first = next(r for r in exported['projects'] if r['id'] == 1)
    assert first['categories'] == ['research', 'documents']
    assert first['metadata']['web_evidence']


def test_manual_categories_keywords_survive_automatic_reorganization_and_keep_notes(library):
    result = library.patch('/api/projects/1', json={'categories': ['development'], 'keywords': ['中文写作', 'writing']})
    assert result.status_code == 200 and result.json()['classification_method'] == 'manual'
    with Session.begin() as db:
        save_organization(db, db.get(Repository, 1), {'categories': ['models'], 'keywords': ['llm'], 'method': 'ai'})
    saved = library.get('/api/projects/1').json()
    assert saved['categories'] == ['development'] and saved['keywords'] == ['中文写作', 'writing']
    assert saved['notes'] == '保留我的笔记' and saved['tags'] == ['待读']
    assert saved['display_description'] != saved['description']
    assert library.patch('/api/projects/1', json={'categories': ['invented']}).status_code == 422
    assert library.post('/api/projects/3/curate').status_code == 409


def test_curation_is_deduplicated_and_admin_only(library):
    first = library.post('/api/projects/curate').json()
    second = library.post('/api/projects/curate').json()
    assert first['created'] and not second['created'] and first['job_id'] == second['job_id']
    single = library.post('/api/projects/1/curate').json()
    assert single['job_id'] == first['job_id'] and not single['created']
    library.post('/api/auth/logout')
    assert library.post('/api/projects/curate').status_code == 401


def test_new_collection_automatically_schedules_one_curation_without_overwriting_classification(library, monkeypatch):
    from app.jobs import collect_repo
    monkeypatch.setattr(settings, 'ai_api_key', 'test-key')
    monkeypatch.setattr(settings, 'ai_base_url', 'https://compatible.example')
    monkeypatch.setattr(settings, 'ai_model', 'test-model')
    with Session.begin() as db:
        db.get(Repository, 1).readme = 'Translate academic papers into Chinese.'
    collect_repo('owner/papers')
    collect_repo('owner/papers')
    with Session() as db:
        jobs = db.query(Job).filter_by(kind='curate_project').all()
        assert len(jobs) == 1 and jobs[0].payload['repo_id'] == 1
        assert db.get(ProjectOrganization, 1).method == 'ai'


def test_bulk_curation_continues_past_one_bad_summary_and_preserves_progress(library, monkeypatch):
    calls = []
    def repair(repo_id):
        calls.append(repo_id)
        if repo_id == 1:
            raise ServiceError('Temporary model failure', True)
        return False
    monkeypatch.setattr('app.curation.curate_repo', repair)
    monkeypatch.setattr('app.curation.classify_batch', lambda rows: {r.id: {'categories': ['documents'], 'keywords': [], 'method': 'ai'} for r in rows})
    job_id = library.post('/api/projects/curate').json()['job_id']
    with Session() as db:
        job = db.get(Job, job_id)
    with pytest.raises(ServiceError, match='其他项目已继续整理'):
        run_curation(job)
    assert calls == [1, 2]
    with Session() as db:
        job = db.get(Job, job_id)
        assert job.payload['summary_done'] == [2]
        assert job.payload['summary_failures']['1']['retryable']
        assert 3 not in job.payload['repo_ids']
