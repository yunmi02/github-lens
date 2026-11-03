from app.db import Session
from app.models import Repository, ProjectTrash, ImageLink, ImageRecord, Batch, Config
from app.jobs import upsert_repo


def seed():
    with Session.begin() as db:
        db.add(Repository(id=900, full_name='owner/kept', collected=True, favorite=True,
                          language='Python', notes='personal note', tags=['reading'], readme='Original documentation',
                          summary={'overview': {'text': 'Saved summary'}}, metadata_json={'html_url': 'https://github.com/owner/kept'}))
        db.add(Repository(id=901, full_name='owner/discovery', collected=False))
        db.add(Batch(id='source'))
        db.flush()
        db.add(ImageRecord(id='source-image', batch_id='source', filename='source.png', path='unused.png', sha256='a'*64))
        db.flush()
        db.add(ImageLink(image_id='source-image', repo_id=900))


def test_trash_and_restore_preserve_project_and_source_data(client):
    seed()
    moved = client.delete('/api/projects/900')
    assert moved.status_code == 200
    deleted_at = moved.json()['trashed_at']
    assert deleted_at
    assert client.delete('/api/projects/900').json()['trashed_at'] == deleted_at
    assert client.get('/api/projects').json()['total'] == 0
    assert client.get('/api/projects?favorite=true').json()['total'] == 0
    stats = client.get('/api/stats').json()
    assert (stats['projects'], stats['favorites'], stats['trashed']) == (0, 0, 1)
    recycled = client.get('/api/projects?trash=true&q=personal&language=Python&favorite=true').json()
    assert recycled['total'] == recycled['trash_total'] == 1
    item = recycled['items'][0]
    assert item['notes'] == 'personal note' and item['tags'] == ['reading'] and item['favorite']
    assert item['trashed_at'] == deleted_at
    detail = client.get('/api/projects/900').json()
    assert detail['readme'] == 'Original documentation' and detail['images'][0]['id'] == 'source-image'
    assert client.post('/api/projects/900/restore').status_code == 200
    assert client.post('/api/projects/900/restore').status_code == 200
    active = client.get('/api/projects').json()
    assert active['total'] == active['active_total'] == 1 and active['trash_total'] == 0
    assert active['items'][0]['trashed_at'] is None
    assert client.get('/api/projects/900').json()['notes'] == 'personal note'
    assert client.get('/api/stats').json()['favorites'] == 1


def test_trashed_project_is_hidden_from_export_and_discovery_and_cannot_be_edited(client):
    seed()
    with Session.begin() as db:
        db.add(Config(key='discovery_result', value={'repo_ids': [900, 901]}))
    client.delete('/api/projects/900')
    assert client.get('/api/export').json()['projects'] == []
    assert [r['id'] for r in client.get('/api/discoveries').json()['items']] == [901]
    assert client.patch('/api/projects/900', json={'notes': 'overwrite'}).status_code == 409
    assert client.post('/api/projects/900/refresh').status_code == 409
    assert client.post('/api/projects/import', json={'full_name': 'owner/kept'}).status_code == 409
    assert client.delete('/api/projects/901').status_code == 404
    assert client.delete('/api/projects/999').status_code == 404
    assert client.post('/api/projects/999/restore').status_code == 404


def test_background_metadata_updates_do_not_restore_trashed_projects(client):
    seed()
    client.delete('/api/projects/900')
    with Session.begin() as db:
        upsert_repo(db, {'id': 900, 'full_name': 'owner/kept', 'description': 'Fresh metadata', 'stargazers_count': 20}, collected=True)
        assert db.get(ProjectTrash, 900)
        assert db.query(ImageLink).filter_by(repo_id=900).count() == 1
    assert client.get('/api/projects').json()['total'] == 0
    assert client.get('/api/projects?trash=true').json()['items'][0]['stars'] == 20
    client.post('/api/projects/900/restore')
    assert client.get('/api/projects').json()['total'] == 1


def test_trash_routes_require_admin_and_reject_foreign_origins(client):
    seed()
    assert client.delete('/api/projects/900', headers={'Origin': 'https://attacker.example'}).status_code == 403
    assert client.get('/api/projects').json()['total'] == 1
    client.post('/api/auth/logout')
    assert client.delete('/api/projects/900').status_code == 401
    assert client.post('/api/projects/900/restore').status_code == 401
    assert client.get('/api/projects?trash=true').status_code == 401
