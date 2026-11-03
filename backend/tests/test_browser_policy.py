import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import pytest
from app.browser_policy import limited, before_navigation, policy_state, timestamp, BrowserCooling, KEY
from app.browser_service import BrowserReader, release, health
from app.computer_research import claim, ClaimRequest, executor_state
from app.config import settings
from app.db import Session
from app.models import Config, Job


def enqueue(job_id):
    with Session.begin() as db:
        db.add(Job(id=job_id, kind='computer_use', status='waiting_browser', payload={'provider': 'computer_use'}))


def test_limit_pauses_every_job_without_consuming_project_failure_budget(client, monkeypatch):
    monkeypatch.setattr(settings, 'research_backend', 'browser')
    enqueue('first')
    receipt = claim(ClaimRequest(job_id='first', executor='browser_service'))
    exc = limited(429, {}, 'github.com')
    release('first', receipt['lease'], str(exc), True, exc.retry_after, count_failure=False)
    enqueue('next')
    assert claim(ClaimRequest(job_id='next', executor='browser_service'))['task'] is None
    assert claim(ClaimRequest(executor='browser_service'))['task'] is None
    health('idle')
    with Session() as db:
        assert db.get(Job, 'first').status == 'waiting_browser'
        assert db.get(Job, 'first').payload['browser_failures'] == 0
        assert db.get(Job, 'next').payload.get('browser_runs', 0) == 0
        state = executor_state(db)
        assert state['online'] and state['status'] == 'cooldown' and state['cooldown_until']
    class NoNavigation:
        async def new_page(self):
            raise AssertionError('No new page or request is allowed during cooldown')
    with pytest.raises(BrowserCooling):
        asyncio.run(BrowserReader(NoNavigation(), 'next').read('https://github.com/owner/tv', 'repository'))


def test_retry_after_date_and_repeated_limits_extend_persistent_cooldown(client, monkeypatch):
    monkeypatch.setattr(settings, 'browser_cooldown_seconds', 60)
    monkeypatch.setattr(settings, 'browser_max_cooldown_seconds', 3600)
    first = limited(429, {}, 'github.com')
    second = limited(429, {}, 'github.com')
    assert first.retry_after == 60 and second.retry_after >= 120
    deadline = datetime.now(timezone.utc) + timedelta(hours=2)
    third = limited(429, {'retry-after': format_datetime(deadline, usegmt=True)}, 'github.com')
    assert third.retry_after >= 7199  # Site's longer Retry-After takes precedence.
    with Session() as db:
        saved = db.get(Config, KEY).value
    with Session() as db:  # A fresh session/service sees exactly the same deadline.
        state = policy_state(db)
        assert state['cooling'] and state['cooldown_until'] == saved['cooldown_until']
        assert state['limit_count'] == 3


def test_pacing_is_shared_across_jobs_and_search_uses_longer_interval(client, monkeypatch):
    waits = []
    async def elapsed(seconds):
        waits.append(seconds)
        with Session.begin() as db:
            row = db.get(Config, KEY)
            row.value = {**row.value, 'next_request_at': '2000-01-01T00:00:00+00:00'}
    asyncio.run(before_navigation('search'))
    with Session() as db:
        next_time = timestamp(policy_state(db)['next_request_at'])
        assert (next_time - datetime.now(timezone.utc)).total_seconds() > 25
    monkeypatch.setattr('app.browser_policy.asyncio.sleep', elapsed)
    asyncio.run(before_navigation('repository'))
    assert waits and waits[0] > 0


def test_reader_interprets_retry_after_and_closes_rate_limited_page(client):
    class Page:
        url = 'https://github.com/search?q=tv&type=repositories'
        closed = False
        async def goto(self, *a, **kw):
            return type('Response', (), {'status': 429, 'headers': {'retry-after': '1800'}})()
        async def title(self):
            return 'Too many requests'
        def locator(self, *a):
            return self
        async def inner_text(self, **kw):
            return 'Please wait before trying again.'
        async def close(self):
            self.closed = True
    page = Page()
    class Context:
        async def new_page(self):
            return page
    reader = BrowserReader(Context(), 'limited')
    with pytest.raises(BrowserCooling) as error:
        asyncio.run(reader.read(page.url, 'search'))
    assert error.value.retry_after >= 1800
    assert page.closed and not reader.sources
    with Session() as db:
        assert policy_state(db)['cooling']


def test_completed_search_sources_and_links_can_resume_without_new_requests(client):
    url = 'https://github.com/search?q=tv&type=repositories'
    class NoNavigation:
        async def new_page(self):
            raise AssertionError('A completed search must not be requested again')
    reader = BrowserReader(NoNavigation(), 'resumed')
    source = {'url': url, 'title': 'TV', 'role': 'search', 'content': 'Official TV project.'}
    links = [{'url': 'https://github.com/owner/tv', 'title': 'owner/tv'}]
    reader.sources[url] = source
    reader.source_links[url] = links
    actual_source, actual_links = asyncio.run(reader.read(url, 'search'))
    assert actual_source == source and actual_links == links
