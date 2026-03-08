from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ChainInfo:
    id: str
    num_residues: int
    sequence: str

    def to_dict(self):
        return {
            'id': self.id,
            'num_residues': self.num_residues,
            'sequence': self.sequence,
        }


@dataclass
class PdbInfo:
    filename: str
    chain_id: str | None = None
    chain_sequence: str | None = None
    available_chains: list[ChainInfo] = field(default_factory=list)

    def to_dict(self):
        return {
            'filename': self.filename,
            'chain_id': self.chain_id,
            'chain_sequence': self.chain_sequence,
            'available_chains': [c.to_dict() for c in self.available_chains],
        }


@dataclass
class GroupConfig:
    filename: str
    threshold: float = 95.0
    pdb: PdbInfo | None = None
    representative_index: int | None = None
    num_sequences: int = 0
    alignment_length: int = 0

    def to_dict(self):
        return {
            'filename': self.filename,
            'threshold': self.threshold,
            'pdb': self.pdb.to_dict() if self.pdb else None,
            'representative_index': self.representative_index,
            'num_sequences': self.num_sequences,
            'alignment_length': self.alignment_length,
        }
