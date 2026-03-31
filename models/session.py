from __future__ import annotations
import os
import zipfile
import shutil
import tempfile
import time
from dataclasses import dataclass, field

from Bio import SeqIO
from Bio.PDB import PDBParser, MMCIFParser
from Bio import SeqUtils

from models.types import ChainInfo, PdbInfo, GroupConfig
from models.analysis import find_representative_index
from models.analysis import find_representative_index

FASTA_EXTENSIONS = ('.fasta', '.fa', '.faa', '.fas')
FASTA_ENCODINGS = ('utf-8', 'latin-1', 'cp1252', 'iso-8859-1')


def _safe_path(base_dir: str, filename: str) -> str:
    """Join base_dir and filename, raising ValueError on path traversal."""
    joined = os.path.normpath(os.path.join(base_dir, filename))
    base = os.path.normpath(base_dir) + os.sep
    if not joined.startswith(base):
        raise ValueError(f'Invalid path: {filename}')
    return joined


def _structure_parser(pdb_path):
    """Return the appropriate BioPython parser for PDB or mmCIF files."""
    if pdb_path.lower().endswith('.cif'):
        return MMCIFParser(QUIET=True)
    return PDBParser(QUIET=True)


def parse_pdb_chains(pdb_path):
    """Parse a PDB/mmCIF file and return list of ChainInfo."""
    parser = _structure_parser(pdb_path)
    structure = parser.get_structure("protein", pdb_path)
    model = structure[0]
    chains = []
    for chain in model.get_chains():
        residues = [r for r in chain.get_residues() if r.id[0] == ' ']
        seq = ''.join(SeqUtils.seq1(r.get_resname()) for r in residues)
        chains.append(ChainInfo(
            id=chain.id,
            num_residues=len(residues),
            sequence=seq,
        ))
    return chains


def _read_fasta(path):
    """Read a FASTA file trying multiple encodings. Returns list of SeqRecords."""
    for encoding in FASTA_ENCODINGS:
        try:
            with open(path, 'r', encoding=encoding) as f:
                return list(SeqIO.parse(f, 'fasta'))
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"Could not read {path} with any supported encoding")


def _scan_fasta(path):
    """Quick scan of a FASTA file. Returns (num_sequences, alignment_length)."""
    seqs = _read_fasta(path)
    if not seqs:
        return 0, 0
    return len(seqs), len(seqs[0].seq)


@dataclass
class Session:
    id: str
    temp_dir: str
    groups: dict[str, GroupConfig] = field(default_factory=dict)
    all_fasta: str | None = None
    cross_threshold: float = 95.0
    created_at: float = field(default_factory=time.time)

    @classmethod
    def create_new(cls, session_id: str) -> 'Session':
        """Create a new session with a fresh temp directory."""
        temp_dir = tempfile.mkdtemp()
        return cls(id=session_id, temp_dir=temp_dir)

    def _save_file(self, filename, file_storage):
        """Save an uploaded file to the temp directory."""
        dest = os.path.join(self.temp_dir, filename)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        file_storage.save(dest)
        return dest

    def _save_content(self, filename, content):
        """Save text content as a file in the temp directory."""
        dest = os.path.join(self.temp_dir, filename)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, 'w') as f:
            f.write(content)
        return dest

    def _add_group(self, filename, path):
        """Register a FASTA file as a group, scanning for metadata."""
        num_seq, aln_len = _scan_fasta(path)
        self.groups[filename] = GroupConfig(
            filename=filename,
            num_sequences=num_seq,
            alignment_length=aln_len,
        )

    def add_fasta_file(self, filename, file_storage) -> 'Session':
        """Add a single FASTA file from an upload."""
        path = self._save_file(filename, file_storage)
        self._add_group(filename, path)
        return self

    def add_fasta_content(self, filename, content) -> 'Session':
        """Add a FASTA file from text content."""
        path = self._save_content(filename, content)
        self._add_group(filename, path)
        return self

    def add_cross_fasta_file(self, filename, file_storage) -> 'Session':
        """Add a FASTA file as the cross-alignment (all.fasta)."""
        self._save_file(filename, file_storage)
        self.all_fasta = filename
        return self

    def add_cross_fasta_content(self, filename, content) -> 'Session':
        """Add text content as the cross-alignment."""
        self._save_content(filename, content)
        self.all_fasta = filename
        return self

    def add_fasta_zip(self, file_storage) -> 'Session':
        """Extract a ZIP of FASTA files, detect all.fasta, populate groups."""
        zip_path = os.path.join(self.temp_dir, 'upload.zip')
        file_storage.save(zip_path)

        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Validate all paths before extracting (prevent ZipSlip)
                for member in zip_ref.namelist():
                    member_path = os.path.normpath(
                        os.path.join(self.temp_dir, member)
                    )
                    if not member_path.startswith(
                        os.path.normpath(self.temp_dir) + os.sep
                    ) and member_path != os.path.normpath(self.temp_dir):
                        raise ValueError(
                            f'ZIP contains path traversal entry: {member}'
                        )
                zip_ref.extractall(self.temp_dir)
        except zipfile.BadZipFile:
            os.remove(zip_path)
            raise ValueError('Invalid ZIP file')

        # Find all FASTA files
        fasta_files = []
        for root, dirs, files in os.walk(self.temp_dir):
            dirs[:] = [d for d in dirs if d not in ['__MACOSX', '.DS_Store']]
            for fname in files:
                if fname.startswith('.') or fname.startswith('._'):
                    continue
                if fname.endswith(FASTA_EXTENSIONS):
                    rel_path = os.path.relpath(os.path.join(root, fname), self.temp_dir)
                    fasta_files.append(rel_path)

        # Separate all.fasta from group files
        for f in fasta_files:
            basename_no_ext = os.path.splitext(os.path.basename(f))[0]
            if basename_no_ext.lower() == 'all':
                self.all_fasta = f
            else:
                abs_path = os.path.join(self.temp_dir, f)
                self._add_group(f, abs_path)

        if not self.groups:
            raise ValueError('No FASTA files found in ZIP')

        return self

    def remove_fasta(self, filename) -> 'Session':
        """Remove a FASTA file from the session."""
        if filename not in self.groups and filename != self.all_fasta:
            raise FileNotFoundError(f'FASTA file not found: {filename}')

        file_path = _safe_path(self.temp_dir, filename)
        if os.path.exists(file_path):
            os.remove(file_path)

        if filename == self.all_fasta:
            self.all_fasta = None
        else:
            self.groups.pop(filename, None)

        return self

    def get_fasta_content(self, filename) -> str:
        """Return the raw text of a FASTA file."""
        path = _safe_path(self.temp_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f'FASTA file not found: {filename}')
        for encoding in FASTA_ENCODINGS:
            try:
                with open(path, 'r', encoding=encoding) as f:
                    return f.read()
            except (UnicodeDecodeError, UnicodeError):
                continue
        raise ValueError(f'Could not read {filename} with any supported encoding')

    def list_sequences(self, filename):
        """List sequence IDs and lengths in a FASTA file.

        Returns list of {index, id, length} dicts.
        """
        path = _safe_path(self.temp_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f'FASTA file not found: {filename}')

        seqs = _read_fasta(path)
        return [
            {
                'index': i,
                'id': seq.id,
                'length': len(str(seq.seq).replace('-', '')),
            }
            for i, seq in enumerate(seqs)
        ]

    def suggest_representative(self, fasta_filename, chain_sequence):
        """Find the FASTA sequence that best matches a PDB chain sequence.

        Returns the full match dict from find_representative_index.
        """
        path = _safe_path(self.temp_dir, fasta_filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f'FASTA file not found: {fasta_filename}')
        return find_representative_index(path, chain_sequence)

    def add_pdb(self, filename, file_storage) -> list[ChainInfo]:
        """Save a PDB file and return its parsed chains."""
        pdb_dir = os.path.join(self.temp_dir, 'pdb')
        os.makedirs(pdb_dir, exist_ok=True)

        pdb_path = os.path.join(pdb_dir, filename)
        file_storage.save(pdb_path)

        try:
            chains = parse_pdb_chains(pdb_path)
        except Exception as e:
            os.remove(pdb_path)
            raise ValueError(f'Failed to parse PDB file: {e}')

        if not chains:
            os.remove(pdb_path)
            raise ValueError('No protein chains found in PDB file')

        return chains

    def add_pdb_from_bytes(self, filename, data) -> list[ChainInfo]:
        """Save PDB data (bytes) and return its parsed chains."""
        pdb_dir = os.path.join(self.temp_dir, 'pdb')
        os.makedirs(pdb_dir, exist_ok=True)

        pdb_path = os.path.join(pdb_dir, filename)
        with open(pdb_path, 'wb') as f:
            f.write(data)

        try:
            chains = parse_pdb_chains(pdb_path)
        except Exception as e:
            os.remove(pdb_path)
            raise ValueError(f'Failed to parse PDB file: {e}')

        if not chains:
            os.remove(pdb_path)
            raise ValueError('No protein chains found in PDB file')

        return chains

    def remove_pdb(self, filename) -> 'Session':
        """Remove a PDB file and clear any group references to it."""
        pdb_dir = os.path.join(self.temp_dir, 'pdb')
        pdb_path = _safe_path(pdb_dir, filename)
        if os.path.exists(pdb_path):
            os.remove(pdb_path)

        for group in self.groups.values():
            if group.pdb and group.pdb.filename == filename:
                group.pdb = None

        return self

    def update_config(self, thresholds=None, chain_assignments=None,
                      cross_threshold=None, representative_indices=None,
                      display_names=None) -> 'Session':
        """Update session configuration."""
        if display_names:
            for filename, name in display_names.items():
                if filename in self.groups:
                    self.groups[filename].display_name = name

        if thresholds:
            for filename, threshold in thresholds.items():
                if filename in self.groups:
                    self.groups[filename].threshold = threshold

        if representative_indices:
            for filename, index in representative_indices.items():
                if filename in self.groups:
                    self.groups[filename].representative_index = index

        if chain_assignments:
            for filename, assignment in chain_assignments.items():
                if filename not in self.groups:
                    continue
                pdb_filename = assignment.get('pdb_filename')
                chain_id = assignment.get('chain_id')
                if not pdb_filename:
                    self.groups[filename].pdb = None
                    continue

                pdb_path = os.path.join(self.temp_dir, 'pdb', pdb_filename)
                if not os.path.exists(pdb_path):
                    continue

                chains = parse_pdb_chains(pdb_path)
                chain_sequence = None
                for chain in chains:
                    if chain.id == chain_id:
                        chain_sequence = chain.sequence
                        break

                self.groups[filename].pdb = PdbInfo(
                    filename=pdb_filename,
                    chain_id=chain_id,
                    chain_sequence=chain_sequence,
                    available_chains=chains,
                )

        if cross_threshold is not None:
            self.cross_threshold = cross_threshold

        return self

    def to_dict(self):
        return {
            'id': self.id,
            'groups': {k: v.to_dict() for k, v in sorted(self.groups.items())},
            'all_fasta': self.all_fasta,
            'cross_threshold': self.cross_threshold,
        }

    def cleanup(self):
        """Delete the temp directory."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
