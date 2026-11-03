import hashlib
import hmac
import secrets
import time
from collections import OrderedDict
from threading import Lock
from datetime import datetime, timezone
from fastapi import HTTPException, Request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from .config import settings
from .db import Session
from .models import Config, UploadSession


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password):
    salt = secrets.token_hex(16)
    return salt + ':' + hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600_000).hex()


def check_password(password, stored):
    try:
        salt, expected = stored.split(':', 1)
        return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600_000).hex(), expected)
    except (ValueError, TypeError, AttributeError):
        return False


class LoginLimiter:
    """Reserve attempts before password hashing; concurrent failures also count."""
    def __init__(self, limit=10, window=300, capacity=2048):
        self.limit, self.window, self.capacity = limit, window, capacity
        self.entries, self.lock = OrderedDict(), Lock()

    def reserve(self, key):
        now = time.monotonic()
        with self.lock:
            values = [t for t in self.entries.pop(key, []) if now - t < self.window]
            if len(values) >= self.limit:
                self.entries[key] = values
                raise HTTPException(429, '尝试次数过多，请 5 分钟后重试', headers={'Retry-After': str(self.window)})
            self.entries[key] = values + [now]
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)

    def clear(self, key):
        with self.lock:
            self.entries.pop(key, None)


login_limiter = LoginLimiter()


def init_security():
    with Session.begin() as db:
        if not db.get(Config, 'session_secret'):
            db.add(Config(key='session_secret', value={'secret': secrets.token_hex(32)}))
        if settings.admin_password and not db.get(Config, 'admin'):
            db.add(Config(key='admin', value={'hash': hash_password(settings.admin_password)}))


def serializer():
    with Session() as db:
        return URLSafeTimedSerializer(db.get(Config, 'session_secret').value['secret'], salt='github-lens')


def is_admin(request: Request):
    try:
        return serializer().loads(request.cookies.get('lens_auth', ''), max_age=7 * 86400) == 'admin'
    except (BadSignature, SignatureExpired):
        return False


def require_admin(request: Request):
    if not is_admin(request):
        raise HTTPException(401, '请先登录')


def phone_session(request: Request):
    credential = request.headers.get('X-Upload-Credential', '')
    with Session() as db:
        row = db.query(UploadSession).filter_by(credential_hash=digest(credential)).first() if credential else None
        if not row or row.revoked or datetime.fromisoformat(row.expires_at) <= datetime.now(timezone.utc):
            raise HTTPException(401, '上传会话已过期或撤销，请重新扫码')
        return row
