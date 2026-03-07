"""
In-memory session store mapping opaque tokens to Session objects.
Provides thread-safe creation, lookup, removal, and expiry-based cleanup.
"""
import uuid
import time
import os
import shutil
import threading

_sessions = {}  # {token: Session}
_lock = threading.Lock()
MAX_AGE = 3600  # 1 hour


def create(session):
    """Register a Session and return its token (also sets session.id)."""
    token = uuid.uuid4().hex
    session.id = token
    with _lock:
        _sessions[token] = session
    return token


def get(token):
    """Look up the Session for a token. Returns None if invalid/expired."""
    with _lock:
        session = _sessions.get(token)
    if not session:
        return None
    if not os.path.exists(session.temp_dir):
        remove(token)
        return None
    return session


def get_temp_dir(token):
    """Backward-compat shim: return temp_dir string or None."""
    session = get(token)
    return session.temp_dir if session else None


def remove(token):
    """Delete session and its temp dir."""
    with _lock:
        session = _sessions.pop(token, None)
    if session:
        session.cleanup()


def cleanup_expired():
    """Remove sessions older than MAX_AGE."""
    now = time.time()
    with _lock:
        expired = [t for t, s in _sessions.items()
                   if now - s.created_at > MAX_AGE]
    for token in expired:
        remove(token)
