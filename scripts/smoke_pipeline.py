"""Optional real-network smoke test: actual PaddleOCR + GitHub API, isolated data."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='lens-real-smoke-') as temp:
        os.environ.update(DATA_DIR=temp, DATABASE_URL='sqlite:///' + str(Path(temp) / 'smoke.db').replace('\\', '/'),
                          ADMIN_PASSWORD='smoke-local-password-123', WORKER_ENABLED='false', AI_API_KEY='', NO_PROXY='*', OCR_PROVIDER='paddle')
        sys.path.insert(0, str(ROOT / 'backend'))
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db import engine, Session
        from app.models import Job
        from app.jobs import run_job
        try:
            with TestClient(app) as client:
                assert client.post('/api/auth/login', json={'password': os.environ['ADMIN_PASSWORD']}).status_code == 200
                batch = client.post('/api/import-batches').json()['id']
                with (ROOT / 'frontend/e2e/fixtures/sample.png').open('rb') as image:
                    upload = client.post(f'/api/import-batches/{batch}/images', files={'file': ('sample.png', image, 'image/png')})
                assert upload.status_code == 200, upload.text
                job_id = upload.json()['job_id']
                with Session.begin() as db:
                    job = db.get(Job, job_id)
                    job.status, job.attempts = 'running', 1
                run_job(job_id)
                result = client.get(f'/api/import-batches/{batch}').json()['images'][0]
                assert result['status'] == 'completed', result
                projects = client.get('/api/projects').json()['items']
                assert len(projects) == 1 and projects[0]['full_name'] == 'PaddlePaddle/PaddleOCR'
                detail = client.get('/api/projects/' + str(projects[0]['id'])).json()
                assert detail['readme'] and detail['images'] and detail['metadata']['latest_release']
                report = {'success': True, 'ocr_text': result['text'], 'project': detail['full_name'], 'readme_chars': len(detail['readme']),
                          'first_release': detail['metadata']['first_release'], 'latest_release': detail['metadata']['latest_release'],
                          'elapsed_seconds': round(time.monotonic() - started, 2), 'summary_mode': detail['summary']['mode']}
                output = ROOT / 'data/qa/pipeline-result.json'
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps(report, ensure_ascii=False))
        finally:
            engine.dispose()


if __name__ == '__main__':
    main()
