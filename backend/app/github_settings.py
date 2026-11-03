"""Validate a GitHub credential before storing it; never return the credential."""
import re
from threading import Lock
import httpx
from dotenv import set_key
from fastapi import HTTPException
from .config import ROOT, settings
from .db import Session, utcnow
from .models import Job, ImageResearch

CONFIG_PATH = ROOT / '.env'
_write_lock = Lock()


def configure_github_token(token):
    token = token.strip()
    if not 20 <= len(token) <= 512 or not re.fullmatch(r'[A-Za-z0-9_]+', token):
        raise HTTPException(422, '请输入完整的 GitHub Token')
    try:
        with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
            response = client.get('https://api.github.com/rate_limit', headers={
                'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json', 'User-Agent': 'GitHub-Lens/0.1'})
    except httpx.HTTPError as exc:
        raise HTTPException(502, '无法连接 GitHub，尚未保存，请检查网络后重试') from exc
    if response.status_code == 401:
        raise HTTPException(422, 'GitHub Token 无效或已过期，原配置未改变')
    if response.status_code in (403, 429):
        raise HTTPException(429, 'GitHub 暂时限制请求，请稍后重新验证')
    if not response.is_success:
        raise HTTPException(502, 'GitHub 验证暂时失败，原配置未改变')
    try:
        resources = response.json()['resources']
        rates = {key: {field: int(resources[key][field]) for field in ('limit', 'remaining', 'reset')} for key in ('core', 'search')}
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(502, 'GitHub 返回的验证结果无效，原配置未改变') from exc
    with _write_lock:
        try:
            set_key(str(CONFIG_PATH), 'GITHUB_TOKEN', token, quote_mode='always')
        except OSError as exc:
            raise HTTPException(500, '令牌验证通过，但配置保存失败，请检查项目目录权限') from exc
        settings.github_token = token
    resumed = 0
    with Session.begin() as db:
        for job in db.query(Job).filter_by(status='queued'):
            if 'GitHub' in job.error and '受限' in job.error:
                job.available_at, job.error, job.stage = utcnow(), '', 'GitHub Token 已更新，等待继续'
                row = db.get(ImageResearch, job.payload.get('image_id')) if job.payload.get('image_id') else None
                if row and row.job_id == job.id:
                    row.error, row.stage = '', job.stage
                resumed += 1
    return {'github_authenticated': True, 'rate_limit': rates, 'resumed_jobs': resumed, 'message': 'GitHub Token 已验证并保存，立即生效'}
