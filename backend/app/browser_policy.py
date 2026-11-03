"""Persisted pacing and queue-wide backoff for the application's browser."""
import asyncio
import math
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from .config import settings
from .db import Session
from .models import Config
from .github import ServiceError

KEY = 'browser_request_policy'


class BrowserCooling(ServiceError):
    """A site-wide limit is not a failed project or an AI quota failure."""
    pass


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def policy_state(db):
    row = db.get(Config, KEY)
    state = dict(row.value or {}) if row else {}
    state['cooling'] = timestamp(state.get('cooldown_until')) > datetime.now(timezone.utc)
    return state


def save(db, state):
    row = db.get(Config, KEY)
    if row:
        row.value = state
    else:
        db.add(Config(key=KEY, value=state))


def retry_seconds(headers, now):
    value = headers.get('retry-after', '')
    try:
        seconds = float(value)
        if math.isfinite(seconds):
            return max(0, min(seconds, 365 * 86400))
    except (TypeError, ValueError):
        pass
    try:
        target = parsedate_to_datetime(value)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        return max(0, (target - now).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return 0


def limited(status, headers, host):
    now = datetime.now(timezone.utc)
    with Session.begin() as db:
        state = policy_state(db)
        previous = state.get('limit_count', 0) if (now - timestamp(state.get('last_limited_at'))).total_seconds() < 86400 else 0
        count = previous + 1
        delay = max(settings.browser_cooldown_seconds,
                    min(settings.browser_max_cooldown_seconds, settings.browser_cooldown_seconds * 2 ** min(count - 1, 10)),
                    retry_seconds(headers, now))
        until = max(timestamp(state.get('cooldown_until')), now + timedelta(seconds=delay))
        reason = f'{host} 网页限流（HTTP {status}），整个浏览器队列冷却后自动继续'
        save(db, {**state, 'limit_count': count, 'last_limited_at': now.isoformat(),
                  'cooldown_until': until.isoformat(), 'reason': reason})
    return BrowserCooling(reason, True, math.ceil((until - now).total_seconds()))


async def before_navigation(role):
    # Single-worker application: all jobs and browser contexts share this gate.
    # Persisting it prevents service restarts from bypassing a website cooldown.
    while True:
        now = datetime.now(timezone.utc)
        with Session.begin() as db:
            state = policy_state(db)
            if state['cooling']:
                raise BrowserCooling(state.get('reason', '浏览器队列正在冷却'), True,
                                     math.ceil((timestamp(state['cooldown_until']) - now).total_seconds()))
            wait = (timestamp(state.get('next_request_at')) - now).total_seconds()
            if wait <= 0:
                interval = max(settings.browser_request_interval_seconds,
                               settings.browser_search_interval_seconds if role == 'search' else 0)
                save(db, {**state, 'next_request_at': (now + timedelta(seconds=interval)).isoformat()})
                return
        await asyncio.sleep(min(wait, 20))
