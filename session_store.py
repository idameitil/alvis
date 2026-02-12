"""
In-memory session store mapping opaque tokens to temp directories.
Provides thread-safe creation, lookup, removal, and expiry-based cleanup.
"""
import uuid
import time
import os
import shutil
import threading

_sessions = {}  # {token: {'temp_dir': str, 'created_at': float}}
_lock = threading.Lock()
MAX_AGE = 3600  # 1 hour


def create(temp_dir):
    """Register a temp dir and return an opaque token."""
    token = uuid.uuid4().hex
    with _lock:
        _sessions[token] = {
            'temp_dir': temp_dir,
            'created_at': time.time(),
        }
    return token


def get_temp_dir(token):
    """Look up the temp dir for a token. Returns None if invalid/expired."""
    with _lock:
        session = _sessions.get(token)
    if not session:
        return None
    if not os.path.exists(session['temp_dir']):
        remove(token)
        return None
    return session['temp_dir']


def remove(token):
    """Delete session and its temp dir."""
    with _lock:
        session = _sessions.pop(token, None)
    if session and os.path.exists(session['temp_dir']):
        shutil.rmtree(session['temp_dir'], ignore_errors=True)


def cleanup_expired():
    """Remove sessions older than MAX_AGE."""
    now = time.time()
    with _lock:
        expired = [t for t, s in _sessions.items()
                   if now - s['created_at'] > MAX_AGE]
    for token in expired:
        remove(token)
