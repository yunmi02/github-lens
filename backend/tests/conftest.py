import os
import tempfile
from pathlib import Path

_temp = tempfile.TemporaryDirectory(prefix='github-lens-test-')
os.environ['DATA_DIR'] = _temp.name
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(_temp.name) / 'test.db').replace('\\', '/')
os.environ['ADMIN_PASSWORD'] = 'test-password-12345'
os.environ['AI_API_KEY'] = ''
os.environ['WORKER_ENABLED'] = 'false'
os.environ['RESEARCH_BACKEND'] = 'deepseek'

import pytest
from fastapi.testclient import TestClient
from app.db import Base, engine, Session
from app.models import Config
from app.main import app


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    _temp.cleanup()


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session.begin() as db:
        db.add(Config(key='discovery_rule', value={'enabled': False}))
    with TestClient(app) as client:
        response = client.post('/api/auth/login', json={'password': 'test-password-12345'})
        assert response.status_code == 200
        yield client


@pytest.fixture
def image_bytes():
    from io import BytesIO
    from PIL import Image
    buf = BytesIO()
    Image.new('RGB', (300, 100), 'white').save(buf, format='PNG')
    return buf.getvalue()
