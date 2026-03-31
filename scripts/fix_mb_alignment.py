#!/usr/bin/env python3
"""
Quick fix: add 3RGK chain A to the existing MB alignment and rebuild.

Does NOT re-run BLAST. Just:
  1. Degap existing MB.fasta sequences
  2. Download 3RGK.pdb if needed, extract chain A sequence
  3. Add chain A to the pool if not already present
  4. Re-run MAFFT L-INS-i
  5. Rebuild all.fasta and globins_example.zip
"""
from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import requests
from Bio.PDB import PDBParser
from Bio import SeqUtils, SeqIO

OUT_DIR = Path(__file__).parent.parent / "example_data" / "globins_example"
ZIP_OUT = Path(__file__).parent.parent / "example_data" / "globins_example.zip"
RCSB_BASE = "https://files.rcsb.org/download"


def parse_fasta(text: str) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    header, parts = "", []
    for line in text.splitlines():
        if line.startswith(">"):
            if header:
                records.append((header, "".join(parts)))
            header, parts = line[1:].strip(), []
        else:
            parts.append(line.strip())
    if header:
        records.append((header, "".join(parts)))
    return records


def write_fasta(records: list[tuple[str, str]], path: Path) -> None:
    with open(path, "w") as f:
        for header, seq in records:
            f.write(f">{header}\n")
            for i in range(0, len(seq), 60):
                f.write(seq[i:i+60] + "\n")


def run_mafft(input_fasta: Path, output_fasta: Path) -> None:
    n = sum(1 for line in open(input_fasta) if line.startswith(">"))
    print(f"  Running MAFFT L-INS-i on {n} sequences...")
    cmd = ["mafft", "--localpair", "--maxiterate", "1000", "--quiet", str(input_fasta)]
    with open(output_fasta, "w") as out_f:
        result = subprocess.run(cmd, stdout=out_f, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"MAFFT failed:\n{result.stderr[:300]}")


def extract_chain_seq(pdb_path: Path, chain_id: str) -> tuple[str, str] | None:
    parser = PDBParser(QUIET=True)
    structure = parser.get_structure("pdb", str(pdb_path))[0]
    available = [c.id for c in structure.get_chains()]
    if chain_id not in available:
        print(f"  Chain {chain_id} not found; available: {available}")
        return None
    chain = structure[chain_id]
    residues = [r for r in chain.get_residues() if r.id[0] == " "]
    seq = "".join(SeqUtils.seq1(r.get_resname()) for r in residues)
    if not seq:
        return None
    print(f"  Extracted chain {chain_id}: {len(seq)} aa")
    return f"PDB_{pdb_path.stem.upper()}_Chain_{chain_id}", seq


def build_all_fasta(group_fastas: list[Path], out_path: Path) -> None:
    all_seqs: list[tuple[str, str]] = []
    for fasta_path in group_fastas:
        for header, seq in parse_fasta(fasta_path.read_text()):
            all_seqs.append((header, seq.replace("-", "")))
    tmp = out_path.parent / "all_unaligned.fasta"
    write_fasta(all_seqs, tmp)
    print(f"\nRebuilding all.fasta ({len(all_seqs)} sequences)...")
    run_mafft(tmp, out_path)
    tmp.unlink()
    print(f"  Saved all.fasta")


def main() -> None:
    # 1. Load existing MB sequences (degapped)
    mb_fasta = OUT_DIR / "MB.fasta"
    existing = parse_fasta(mb_fasta.read_text())
    records = [(h, s.replace("-", "")) for h, s in existing]
    print(f"Existing MB sequences: {len(records)}")

    # 2. Download 3RGK if needed
    pdb_path = OUT_DIR / "3RGK.pdb"
    if not pdb_path.exists():
        url = f"{RCSB_BASE}/3RGK.pdb"
        print(f"Downloading {url}...")
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        pdb_path.write_text(r.text)
        print(f"  Saved 3RGK.pdb")
    else:
        print("3RGK.pdb already present.")

    # 3. Extract chain A and add if not already covered
    entry = extract_chain_seq(pdb_path, "A")
    if not entry:
        raise RuntimeError("Could not extract chain A from 3RGK.pdb")
    pdb_header, pdb_seq = entry
    already_in = any(
        pdb_seq.upper() in s.upper() or s.upper() in pdb_seq.upper()
        for _, s in records
    )
    if already_in:
        print("3RGK chain A already covered by an existing sequence — no injection needed.")
    else:
        print(f"Injecting 3RGK chain A ({len(pdb_seq)} aa) as first sequence.")
        records.insert(0, (pdb_header, pdb_seq))

    # 4. Re-align with MAFFT
    tmp_unaligned = OUT_DIR / "MB_unaligned_tmp.fasta"
    write_fasta(records, tmp_unaligned)
    run_mafft(tmp_unaligned, mb_fasta)
    tmp_unaligned.unlink()
    n_seqs = sum(1 for line in open(mb_fasta) if line.startswith(">"))
    aln_len = len(next(r for r in SeqIO.parse(str(mb_fasta), "fasta")).seq)
    print(f"  Saved MB.fasta ({n_seqs} seqs, {aln_len} cols)")

    # 5. Rebuild all.fasta
    group_fastas = [OUT_DIR / "HBA.fasta", OUT_DIR / "HBB.fasta", OUT_DIR / "MB.fasta"]
    build_all_fasta(group_fastas, OUT_DIR / "all.fasta")

    # 6. Repackage ZIP
    print(f"\nPackaging {ZIP_OUT.name}...")
    with zipfile.ZipFile(ZIP_OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(OUT_DIR.iterdir()):
            if f.suffix in (".fasta", ".pdb"):
                zf.write(f, f.name)
                print(f"  Added: {f.name}")
    print(f"Done! ZIP size: {ZIP_OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
