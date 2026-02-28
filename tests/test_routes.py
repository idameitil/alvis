import io
import json
import zipfile
import session_store


class TestUploadRoute:
    def test_upload_valid_zip(self, client, sample_zip):
        with open(sample_zip, 'rb') as f:
            resp = client.post('/upload', data={
                'file': (f, 'test.zip')
            }, content_type='multipart/form-data')

        assert resp.status_code == 200
        data = resp.get_json()
        assert 'session_token' in data
        assert 'fasta_files' in data
        assert len(data['fasta_files']) == 2
        assert data.get('all_fasta') is not None

        # Cleanup
        session_store.remove(data['session_token'])

    def test_upload_single_fasta(self, client, sample_fasta):
        with open(sample_fasta, 'rb') as f:
            resp = client.post('/upload', data={
                'file': (f, 'single.fasta')
            }, content_type='multipart/form-data')

        assert resp.status_code == 200
        data = resp.get_json()
        assert 'session_token' in data
        assert data['fasta_files'] == ['single.fasta']
        assert 'all_fasta' not in data

        # Cleanup
        session_store.remove(data['session_token'])

    def test_upload_single_fasta_alt_extensions(self, client, tmp_path):
        """FASTA files with .fa, .faa, .fas extensions should be accepted."""
        content = ">s1\nACDE\n>s2\nACDE\n"
        for ext in ('.fa', '.faa', '.fas'):
            fasta_path = str(tmp_path / f"test{ext}")
            with open(fasta_path, 'w') as f:
                f.write(content)
            with open(fasta_path, 'rb') as f:
                resp = client.post('/upload', data={
                    'file': (f, f'test{ext}')
                }, content_type='multipart/form-data')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['fasta_files'] == [f'test{ext}']
            session_store.remove(data['session_token'])

    def test_upload_bad_file(self, client):
        resp = client.post('/upload', data={
            'file': (io.BytesIO(b"not a zip"), 'test.txt')
        }, content_type='multipart/form-data')
        assert resp.status_code == 400

    def test_upload_no_file(self, client):
        resp = client.post('/upload', data={})
        assert resp.status_code == 400


class TestGenerateRoute:
    def test_end_to_end(self, client, sample_zip):
        # Upload
        with open(sample_zip, 'rb') as f:
            upload_resp = client.post('/upload', data={
                'file': (f, 'test.zip')
            }, content_type='multipart/form-data')
        upload_data = upload_resp.get_json()
        token = upload_data['session_token']

        # Generate
        thresholds = {f: 100 for f in upload_data['fasta_files']}
        gen_resp = client.post('/generate', json={
            'session_token': token,
            'thresholds': thresholds,
            'all_fasta': upload_data.get('all_fasta'),
            'cross_threshold': 100,
        })
        assert gen_resp.status_code == 200
        gen_data = gen_resp.get_json()
        assert gen_data['success'] is True
        assert '<svg' in gen_data['svg']

        # Cleanup
        session_store.remove(token)


class TestCleanupRoute:
    def test_cleanup_removes_session(self, client, sample_zip):
        with open(sample_zip, 'rb') as f:
            upload_resp = client.post('/upload', data={
                'file': (f, 'test.zip')
            }, content_type='multipart/form-data')
        token = upload_resp.get_json()['session_token']

        # Verify session exists
        assert session_store.get_temp_dir(token) is not None

        # Cleanup
        resp = client.post('/cleanup', json={'session_token': token})
        assert resp.status_code == 200

        # Session should be gone
        assert session_store.get_temp_dir(token) is None
