import io
import json
import session_store


def _create_session(client):
    """Helper: create a session and return its id."""
    resp = client.post('/session')
    assert resp.status_code == 200
    return resp.get_json()['id']


def _upload_zip(client, session_id, zip_path):
    """Helper: upload a ZIP to a session, return session data."""
    with open(zip_path, 'rb') as f:
        resp = client.post(f'/session/{session_id}/fasta', data={
            'file': (f, 'test.zip')
        }, content_type='multipart/form-data')
    assert resp.status_code == 200
    return resp.get_json()


def _upload_fasta(client, session_id, fasta_path, filename='single.fasta'):
    """Helper: upload a single FASTA to a session, return session data."""
    with open(fasta_path, 'rb') as f:
        resp = client.post(f'/session/{session_id}/fasta', data={
            'file': (f, filename)
        }, content_type='multipart/form-data')
    assert resp.status_code == 200
    return resp.get_json()


class TestSessionCreate:
    def test_create_session(self, client):
        resp = client.post('/session')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'id' in data
        assert 'groups' in data
        assert data['groups'] == {}

        # Cleanup
        session_store.remove(data['id'])


class TestFastaUpload:
    def test_upload_valid_zip(self, client, sample_zip):
        session_id = _create_session(client)
        data = _upload_zip(client, session_id, sample_zip)

        assert len(data['groups']) == 2
        assert data['all_fasta'] is not None

        session_store.remove(session_id)

    def test_upload_single_fasta(self, client, sample_fasta):
        session_id = _create_session(client)
        data = _upload_fasta(client, session_id, sample_fasta)

        assert 'single.fasta' in data['groups']
        assert data['all_fasta'] is None

        session_store.remove(session_id)

    def test_upload_single_fasta_alt_extensions(self, client, tmp_path):
        content = ">s1\nACDE\n>s2\nACDE\n"
        for ext in ('.fa', '.faa', '.fas'):
            session_id = _create_session(client)
            fasta_path = str(tmp_path / f"test{ext}")
            with open(fasta_path, 'w') as f:
                f.write(content)
            data = _upload_fasta(client, session_id, fasta_path, f'test{ext}')
            assert f'test{ext}' in data['groups']
            session_store.remove(session_id)

    def test_upload_bad_file(self, client):
        session_id = _create_session(client)
        resp = client.post(f'/session/{session_id}/fasta', data={
            'file': (io.BytesIO(b"not a zip"), 'test.txt')
        }, content_type='multipart/form-data')
        assert resp.status_code == 400

        session_store.remove(session_id)

    def test_upload_no_file(self, client):
        session_id = _create_session(client)
        resp = client.post(f'/session/{session_id}/fasta', data={})
        assert resp.status_code == 400

        session_store.remove(session_id)

    def test_upload_fasta_content_json(self, client):
        session_id = _create_session(client)
        resp = client.post(f'/session/{session_id}/fasta', json={
            'name': 'pasted.fasta',
            'content': '>seq1\nACDE\n>seq2\nACDE\n'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'pasted.fasta' in data['groups']

        session_store.remove(session_id)

    def test_invalid_session(self, client):
        resp = client.post('/session/nonexistent/fasta', data={
            'file': (io.BytesIO(b">s\nACDE\n"), 'test.fasta')
        }, content_type='multipart/form-data')
        assert resp.status_code == 404


class TestSessionConfig:
    def test_patch_thresholds(self, client, sample_fasta):
        session_id = _create_session(client)
        _upload_fasta(client, session_id, sample_fasta)

        resp = client.patch(f'/session/{session_id}', json={
            'thresholds': {'single.fasta': 80}
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['groups']['single.fasta']['threshold'] == 80

        session_store.remove(session_id)

    def test_patch_cross_threshold(self, client, sample_zip):
        session_id = _create_session(client)
        _upload_zip(client, session_id, sample_zip)

        resp = client.patch(f'/session/{session_id}', json={
            'cross_threshold': 90
        })
        assert resp.status_code == 200
        assert resp.get_json()['cross_threshold'] == 90

        session_store.remove(session_id)


class TestDeleteFasta:
    def test_remove_fasta(self, client, sample_zip):
        session_id = _create_session(client)
        data = _upload_zip(client, session_id, sample_zip)

        files = list(data['groups'].keys())
        resp = client.delete(f'/session/{session_id}/fasta/{files[0]}')
        assert resp.status_code == 200
        result = resp.get_json()
        assert files[0] not in result['groups']

        session_store.remove(session_id)


class TestAnalysisResult:
    def test_end_to_end(self, client, sample_zip):
        session_id = _create_session(client)
        data = _upload_zip(client, session_id, sample_zip)

        # Set thresholds
        thresholds = {f: 100 for f in data['groups'].keys()}
        client.patch(f'/session/{session_id}', json={
            'thresholds': thresholds,
            'cross_threshold': 100,
        })

        # Get result
        resp = client.get(f'/session/{session_id}/result')
        assert resp.status_code == 200
        result = resp.get_json()
        assert result['success'] is True
        assert '<svg' in result['svg']

        session_store.remove(session_id)

    def test_end_to_end_single_fasta(self, client, sample_fasta):
        session_id = _create_session(client)
        _upload_fasta(client, session_id, sample_fasta)

        client.patch(f'/session/{session_id}', json={
            'thresholds': {'single.fasta': 100}
        })

        resp = client.get(f'/session/{session_id}/result')
        assert resp.status_code == 200
        result = resp.get_json()
        assert result['success'] is True
        assert '<svg' in result['svg']

        session_store.remove(session_id)

    def test_no_fasta_returns_error(self, client):
        session_id = _create_session(client)
        resp = client.get(f'/session/{session_id}/result')
        assert resp.status_code == 400

        session_store.remove(session_id)


class TestDeleteSession:
    def test_delete_removes_session(self, client, sample_zip):
        session_id = _create_session(client)
        _upload_zip(client, session_id, sample_zip)

        assert session_store.get(session_id) is not None

        resp = client.delete(f'/session/{session_id}')
        assert resp.status_code == 200

        assert session_store.get(session_id) is None
