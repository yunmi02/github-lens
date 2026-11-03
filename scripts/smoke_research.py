"""Real DeepSeek vision/search + GitHub research, with a synthetic screenshot.

Uses temporary data and the configured AI provider; never sends existing user images.
"""
import json
import argparse
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--auto-confirm', action='store_true')
    automatic = parser.parse_args().auto_confirm
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='lens-agent-smoke-') as temp:
        os.environ.update(DATA_DIR=temp, DATABASE_URL='sqlite:///' + str(Path(temp) / 'smoke.db').replace('\\', '/'),
                          ADMIN_PASSWORD='smoke-research-password-123', WORKER_ENABLED='false', AGENT_AUTO_RESEARCH='false')
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
                    upload = client.post(f'/api/import-batches/{batch}/images', files={'file': ('sample.png', image, 'image/png')}).json()
                # This smoke test starts at the pending handoff, not the OCR stage.
                with Session.begin() as db:
                    db.get(Job, upload['job_id']).status = 'completed'
                route = 'auto-confirm' if automatic else 'research'
                request = client.post(f'/api/recognitions/{upload["id"]}/{route}')
                assert request.status_code == 200, request.text
                job_id = request.json()['job_id']
                with Session.begin() as db:
                    db.get(Job, job_id).attempts = 1
                run_job(job_id)
                state = client.get(f'/api/recognitions/{upload["id"]}/research').json()
                research = state['research']
                report = research['report']
                output = {'status': research['status'], 'error': research['error'], 'useful_info': report.get('plan', {}).get('useful_info'),
                          'search_queries': report.get('searched_queries', []) + list(report.get('project_searches', {})), 'source_count': len(report.get('sources', [])),
                          'projects': [p['full_name'] for p in report.get('projects', [])], 'warnings': report.get('warnings', []),
                          'image_status': state['image']['status'], 'confirmed_count': report.get('confirmed_count'),
                          'web_source_counts': {p['full_name']: len(p.get('summary', {}).get('web_sources', [])) for p in report.get('projects', [])},
                          'summary_modes': {p['full_name']: p.get('summary', {}).get('mode') for p in report.get('projects', [])},
                          'function_counts': {p['full_name']: len(p.get('summary', {}).get('functions', [])) for p in report.get('projects', [])},
                          'elapsed_seconds': round(time.monotonic() - started, 2)}
                target = ROOT / ('data/qa/auto-confirm-real-result.json' if automatic else 'data/qa/research-real-result.json')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps(output, ensure_ascii=False))
                assert research['status'] == 'completed', 'Research did not complete'
                assert report.get('searched_queries') or report.get('project_searches'), 'The real web search was not successful'
                assert 'PaddlePaddle/PaddleOCR' in output['projects'], 'Expected repo not found'
                if automatic:
                    assert state['image']['status'] == 'completed'
                    assert any(c['full_name'] == 'PaddlePaddle/PaddleOCR' and c.get('confirmed') for c in state['image']['candidates'])
                    assert output['web_source_counts']['PaddlePaddle/PaddleOCR'] > 0
                    assert output['summary_modes']['PaddlePaddle/PaddleOCR'] == 'ai'
                    assert output['function_counts']['PaddlePaddle/PaddleOCR'] > 0
        finally:
            engine.dispose()


if __name__ == '__main__':
    main()
