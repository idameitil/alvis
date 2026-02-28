import os
import zipfile
import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import app as flask_app


@pytest.fixture
def tmp_fasta(tmp_path):
    """Return a helper that writes a FASTA string to a temp file."""
    def _write(content, filename="test.fasta"):
        path = tmp_path / filename
        path.write_text(content)
        return str(path)
    return _write


@pytest.fixture
def client():
    """Flask test client."""
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def sample_zip(tmp_path):
    """Create a small ZIP with 2 group FASTA files + an all.fasta."""
    group1 = (
        ">seq1\nACDEFGHIKL\n"
        ">seq2\nACDEFGHIKL\n"
        ">seq3\nACDEFGHIKL\n"
    )
    group2 = (
        ">seq4\nMNPQRSTWYV\n"
        ">seq5\nMNPQRSTWYV\n"
        ">seq6\nMNPQRSTWYV\n"
    )
    all_fasta = (
        ">seq1\nACDEFGHIKL\n"
        ">seq2\nACDEFGHIKL\n"
        ">seq3\nACDEFGHIKL\n"
        ">seq4\nMNPQRSTWYV\n"
        ">seq5\nMNPQRSTWYV\n"
        ">seq6\nMNPQRSTWYV\n"
    )

    zip_path = str(tmp_path / "test_alignments.zip")
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("group1.fasta", group1)
        zf.writestr("group2.fasta", group2)
        zf.writestr("all.fasta", all_fasta)

    return zip_path


@pytest.fixture
def sample_fasta(tmp_path):
    """Create a single FASTA alignment file."""
    content = (
        ">seq1\nACDEFGHIKL\n"
        ">seq2\nACDEFGHIKL\n"
        ">seq3\nACDEFGHIKL\n"
    )
    fasta_path = str(tmp_path / "single.fasta")
    with open(fasta_path, 'w') as f:
        f.write(content)
    return fasta_path
