import os
import tempfile
import session_store
from models.session import Session


class TestSessionStore:
    def setup_method(self):
        """Clear global session state before each test."""
        with session_store._lock:
            session_store._sessions.clear()

    def test_create_and_retrieve(self, tmp_path):
        temp_dir = str(tmp_path / "sess")
        os.makedirs(temp_dir)
        session = Session(id='', temp_dir=temp_dir)
        token = session_store.create(session)
        retrieved = session_store.get(token)
        assert retrieved is not None
        assert retrieved.temp_dir == temp_dir

    def test_remove_deletes_dir(self, tmp_path):
        temp_dir = str(tmp_path / "sess")
        os.makedirs(temp_dir)
        session = Session(id='', temp_dir=temp_dir)
        token = session_store.create(session)
        session_store.remove(token)
        assert session_store.get(token) is None
        assert not os.path.exists(temp_dir)

    def test_invalid_token_returns_none(self):
        assert session_store.get("nonexistent") is None

    def test_get_temp_dir_compat(self, tmp_path):
        temp_dir = str(tmp_path / "sess")
        os.makedirs(temp_dir)
        session = Session(id='', temp_dir=temp_dir)
        token = session_store.create(session)
        assert session_store.get_temp_dir(token) == temp_dir
