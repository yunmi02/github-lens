"""Run one queued task with the application's isolated Chrome research runtime."""
import argparse
import asyncio
from contextlib import suppress
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


async def execute(receipt):
    from playwright.async_api import async_playwright
    from app.browser_service import BrowserReader, BrowserService, research_task, release, health, public_url
    from app.browser_policy import BrowserCooling
    task, lease = receipt['task'], receipt['lease']
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True)
        context = await browser.new_context(accept_downloads=False, service_workers='block')
        async def restrict(route):
            if route.request.method in ('GET', 'HEAD') and public_url(route.request.url):
                await route.continue_()
            else:
                await route.abort()
        await context.route('**/*', restrict)
        pulse = asyncio.create_task(BrowserService().pulse(task['job_id'], lease))
        try:
            await research_task(task, lease, BrowserReader(context, task['job_id']))
        except BrowserCooling as exc:
            release(task['job_id'], lease, str(exc), True, exc.retry_after, count_failure=False)
            raise
        except Exception as exc:
            release(task['job_id'], lease, str(exc), True)
            raise
        finally:
            pulse.cancel()
            with suppress(asyncio.CancelledError):
                await pulse
            await browser.close()
            health('stopped')


def main():
    from app.computer_research import claim, ClaimRequest
    from app.db import Session
    from app.models import Job, Repository
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', required=True)
    args = parser.parse_args()
    receipt = claim(ClaimRequest(job_id=args.job, executor='browser_service'))
    if not receipt.get('task'):
        raise SystemExit('该任务当前不可领取')
    print('Browser task claimed:', receipt['task'].get('full_name') or receipt['task'].get('filename'), flush=True)
    asyncio.run(execute(receipt))
    for _ in range(45):
        with Session() as db:
            job = db.get(Job, args.job)
            if job.status in ('completed', 'failed'):
                repo = db.get(Repository, job.payload.get('repo_id')) if job.payload.get('repo_id') else None
                print(json.dumps({'status': job.status, 'error': job.error,
                      'project': repo.full_name if repo else None,
                      'mode': repo.summary.get('mode') if repo else None,
                      'fields': {k: len(repo.summary.get(k, [])) for k in ('functions', 'innovations', 'use_cases', 'requirements')} if repo else {},
                      'sources': len(repo.summary.get('web_sources', [])) if repo else 0}, ensure_ascii=False))
                if job.status == 'failed':
                    raise SystemExit(1)
                return
        time.sleep(2)
    raise SystemExit('浏览器结果已提交，资料入库仍在处理中')


if __name__ == '__main__':
    main()
