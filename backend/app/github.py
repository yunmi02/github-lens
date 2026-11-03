import base64
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import httpx
from .config import settings


class ServiceError(Exception):
    def __init__(self, message, retryable=False, retry_after=30):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


REPO_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9_.-]{1,100}$')


def normalize_repo(value):
    value = value.strip()
    if value.startswith(('https://', 'http://')):
        parsed = urlparse(value)
        if parsed.hostname not in ('github.com', 'www.github.com') or parsed.username or parsed.password:
            raise ValueError('请输入 github.com 的公开仓库地址')
        value = '/'.join(parsed.path.strip('/').split('/')[:2])
    value = value.removesuffix('.git').strip('/')
    if not REPO_PATTERN.fullmatch(value) or '..' in value:
        raise ValueError('仓库格式应为 owner/repo 或 GitHub 仓库链接')
    return value


def safe_url(value):
    if not isinstance(value, str):
        return ''
    try:
        p = urlparse(value)
        return value if p.scheme in ('http', 'https') and p.hostname and not p.username and not p.password else ''
    except ValueError:
        return ''


def extract_repos(text):
    # URL evidence alone is eligible for automatic confirmation, after API validation.
    normalized = re.sub(r'github\s*[.。]\s*com\s*[/／]\s*', 'github.com/', text, flags=re.I)
    result = []
    for match in re.finditer(r'(?:https?://)?(?:www\.)?github\.com/([\w.-]+)\s*/\s*([\w.-]+)', normalized, re.I):
        try:
            name = normalize_repo(f'{match[1]}/{match[2].rstrip(".,;:")}')
            if name.lower() not in {x['full_name'].lower() for x in result}:
                result.append({'full_name': name, 'evidence': '完整 GitHub 链接', 'auto': True})
        except ValueError:
            pass
    for match in re.finditer(r'(?<![\w./])([A-Za-z0-9][\w.-]{1,60})/([A-Za-z0-9][\w.-]{1,80})(?![\w/])', text):
        try:
            name = normalize_repo(match.group())
            if name.lower() not in {x['full_name'].lower() for x in result}:
                result.append({'full_name': name, 'evidence': '识别到 owner/repo，需要确认', 'auto': False})
        except ValueError:
            pass
    return result


class GitHub:
    def __init__(self):
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'GitHub-Lens/0.1'}
        if settings.github_token:
            headers['Authorization'] = f'Bearer {settings.github_token}'
        self.client = httpx.Client(base_url='https://api.github.com', headers=headers, timeout=30, follow_redirects=False, trust_env=False)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.client.close()

    def get(self, path, params=None, missing_ok=False):
        try:
            response = self.client.get(path, params=params)
            # Repository moves may redirect within api.github.com only.
            for _ in range(3):
                if response.status_code not in (301, 302, 307, 308):
                    break
                location = response.headers.get('location', '')
                if urlparse(location).hostname != 'api.github.com':
                    raise ServiceError('GitHub 返回了不受支持的重定向')
                response = self.client.get(location, params=params)
        except httpx.HTTPError as exc:
            raise ServiceError('无法连接 GitHub，请检查网络后重试', True) from exc
        if response.status_code == 404:
            if missing_ok:
                return None, response.headers
            raise ServiceError('未找到公开仓库，可能已删除、转为私有或名称识别有误')
        if response.status_code in (403, 429):
            delay = 60
            try:
                if response.headers.get('x-ratelimit-remaining') == '0':
                    delay = max(60, int(response.headers.get('x-ratelimit-reset', '0')) - int(datetime.now(timezone.utc).timestamp()))
                delay = int(response.headers.get('retry-after', delay))
            except ValueError:
                pass
            raise ServiceError('GitHub 请求受限，任务将在额度恢复后重试；可配置 GITHUB_TOKEN', True, min(delay, 86400))
        if response.status_code >= 500:
            raise ServiceError('GitHub 暂时不可用', True)
        if response.status_code >= 400:
            raise ServiceError(f'GitHub 请求失败（HTTP {response.status_code}）')
        return response.json(), response.headers

    def search(self, query, limit=5):
        data, _ = self.get('/search/repositories', {'q': query[:240], 'per_page': min(limit, 100), 'sort': 'stars', 'order': 'desc'})
        return data

    def bundle(self, full_name):
        full_name = normalize_repo(full_name)
        repo, _ = self.get(f'/repos/{full_name}')
        if repo.get('private'):
            raise ServiceError('当前版本仅处理公开仓库')
        full_name = repo['full_name']
        readme_data, _ = self.get(f'/repos/{full_name}/readme', missing_ok=True)
        readme = ''
        if readme_data and readme_data.get('content'):
            try:
                readme = base64.b64decode(readme_data['content']).decode('utf-8', errors='replace')[:150_000]
            except (ValueError, TypeError):
                pass
        releases, complete = [], False
        for page in range(1, 11):
            items, headers = self.get(f'/repos/{full_name}/releases', {'per_page': 100, 'page': page})
            releases.extend(x for x in items if not x.get('draft') and not x.get('prerelease') and x.get('published_at'))
            if 'rel="next"' not in headers.get('link', ''):
                complete = True
                break
        releases.sort(key=lambda x: x['published_at'])
        return repo, readme, {
            'readme_url': (readme_data or {}).get('html_url', f'https://github.com/{full_name}#readme'),
            'readme_blob_sha': (readme_data or {}).get('sha'),
            'releases_complete': complete,
            'first_release': self.release_info(releases[0]) if releases and complete else None,
            'latest_release': self.release_info(releases[-1]) if releases else None,
        }

    @staticmethod
    def release_info(release):
        return {k: release.get(k) for k in ('tag_name', 'published_at', 'html_url', 'name')}


def discovery_query(rule):
    since = (datetime.now(timezone.utc) - timedelta(days=rule['days'])).date().isoformat()
    terms = [f'created:>={since}', f'stars:>={rule["min_stars"]}', 'archived:false', 'fork:false']
    if rule.get('language'):
        terms.append('language:' + rule['language'])
    if rule.get('topic'):
        terms.append('topic:' + rule['topic'])
    return ' '.join(terms)
