import pytest
from app.db import Session
from app.models import Batch, ImageRecord, ImageLink, Repository, Job
from app.github import ServiceError
from app.jobs import run_job, process_image
from app.review import repair_linked_reviews


@pytest.fixture
def pending_image(client):
    with Session.begin() as db:
        db.add(Batch(id='batch'))
        db.add(Repository(id=99, full_name='owner/repo', readme='# Cached README'))
        db.flush()
        db.add(ImageRecord(id='image', batch_id='batch', filename='screenshot.png', path='unused', sha256='a'*64,
                           status='needs_review', candidates=[{'full_name': 'owner/repo'}, {'full_name': 'owner/alternative'}]))
    return client


@pytest.mark.parametrize('name', ['owner/repo', 'owner/manual'])
def test_one_confirmation_resolves_screenshot_and_preserves_alternatives(pending_image, name):
    if name.endswith('manual'):
        with Session.begin() as db:
            db.get(Repository, 99).full_name = name
    response = pending_image.post('/api/recognitions/image/confirm', json={'full_name': name})
    job_id = response.json()['job_id']
    assert pending_image.post('/api/recognitions/image/confirm', json={'full_name': name}).json()['job_id'] == job_id
    assert pending_image.post('/api/recognitions/image/confirm', json={'full_name': 'owner/other'}).status_code == 409
    assert pending_image.post('/api/recognitions/image/ignore').status_code == 409
    assert pending_image.get('/api/stats').json()['needs_review'] == 0
    run_job(job_id)
    image = pending_image.get('/api/recognitions/image/research').json()['image']
    assert image['status'] == 'completed'
    assert next(c for c in image['candidates'] if c['full_name'] == name)['confirmed']
    assert any(c['full_name'] == 'owner/alternative' and not c['confirmed'] for c in image['candidates'])
    assert pending_image.get('/api/stats').json()['needs_review'] == 0
    assert pending_image.get('/api/import-batches').json()[0]['images'][0]['status'] == 'completed'
    with Session() as db:
        assert db.query(ImageLink).filter_by(image_id='image', repo_id=99).count() == 1
        assert db.get(Repository, 99).collected


def test_auto_confirmed_link_resolves_other_search_candidates(pending_image, monkeypatch):
    monkeypatch.setattr('app.jobs.read_image', lambda path: ('https://github.com/owner/repo owner/alternative', []))
    with Session.begin() as db:
        db.add(Job(id='ocr', kind='recognize', payload={'image_id': 'image'}))
    with Session() as db:
        process_image(db.get(Job, 'ocr'))
    image = pending_image.get('/api/recognitions/image/research').json()['image']
    assert image['status'] == 'completed'
    assert len(image['candidates']) == 2
    assert image['candidates'][0]['confirmed'] and not image['candidates'][1]['confirmed']


def test_failed_confirmation_returns_to_pending_and_can_retry(pending_image, monkeypatch):
    def fail(*args):
        raise ServiceError('仓库暂不可用')
    with monkeypatch.context() as patch:
        patch.setattr('app.jobs.collect_repo', fail)
        job_id = pending_image.post('/api/recognitions/image/confirm', json={'full_name': 'owner/repo'}).json()['job_id']
        run_job(job_id)
    image = pending_image.get('/api/recognitions/image/research').json()['image']
    assert image['status'] == 'needs_review' and image['error'] == '仓库暂不可用'
    assert not any(c.get('confirmed') for c in image['candidates'])
    assert pending_image.get('/api/stats').json()['needs_review'] == 1
    assert pending_image.post(f'/api/jobs/{job_id}/retry').status_code == 200
    with Session() as db:
        assert db.get(ImageRecord, 'image').status == 'collecting'
    run_job(job_id)
    assert pending_image.get('/api/recognitions/image/research').json()['image']['status'] == 'completed'


def test_repair_only_linked_idle_pending_images(pending_image):
    with Session.begin() as db:
        db.get(Repository, 99).collected = True
        # A repository in the library alone is insufficient evidence of confirmation.
        assert repair_linked_reviews(db) == 0
        for name, status in [('linked', 'needs_review'), ('failed', 'failed'), ('busy', 'needs_review'), ('ignored', 'ignored')]:
            db.add(ImageRecord(id=name, batch_id='batch', filename=name, path='unused', sha256=name, status=status,
                               candidates=[{'full_name': 'owner/repo'}, {'full_name': 'owner/alternative'}]))
        db.flush()
        for name in ['linked', 'failed', 'busy', 'ignored']:
            db.add(ImageLink(image_id=name, repo_id=99))
        db.add(Job(id='busy-job', kind='research', status='running', payload={'image_id': 'busy'}))
        db.flush()
        assert repair_linked_reviews(db) == 2
        assert repair_linked_reviews(db) == 0
        assert db.get(ImageRecord, 'linked').status == 'completed'
        assert db.get(ImageRecord, 'failed').status == 'completed'
        assert db.get(ImageRecord, 'busy').status == 'needs_review'
        assert db.get(ImageRecord, 'ignored').status == 'ignored'
        assert db.get(ImageRecord, 'image').status == 'needs_review'
