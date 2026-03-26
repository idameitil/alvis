#!/usr/bin/env python3
"""
Build improved globins example dataset.

Pipeline:
  1. Fetch human HBA, HBB, MB seed sequences from UniProt
  2. BLASTP against Swiss-Prot (E < 1e-5, query coverage > 70%, no result cap)
  3. Cluster hits with CD-HIT at 90% identity
  4. Align each group with MAFFT LINSI
  5. Build all.fasta (combined alignment for cross-conservation)
  6. Download PDB files 1a3n (hemoglobin), 1a6m (myoglobin)
  7. Package everything as globins_example.zip

Usage:
  source venv/bin/activate
  python scripts/build_globins_example.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

import requests
from Bio.Blast import NCBIWWW, NCBIXML

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SEEDS = {
    "HBA": "P69905",   # Human hemoglobin subunit alpha
    "HBB": "P68871",   # Human hemoglobin subunit beta
    "MB":  "P02144",   # Human myoglobin
}

PDBS = {
    "HBA": "1a3n",
    "HBB": "1a3n",
    "MB":  "1a6m",
}

EVALUE_THRESHOLD = 1e-5
COVERAGE_MIN     = 0.70   # query coverage >= 70%
CDHIT_IDENTITY   = 0.95   # 95% — raise to keep more diverse representatives
CDHIT_COVERAGE   = 0.70
LENGTH_TOLERANCE = 0.30   # ±30% of seed length

OUT_DIR  = Path(__file__).parent.parent / "example_data" / "globins_example"
ZIP_OUT  = Path(__file__).parent.parent / "example_data" / "globins_example.zip"
WORK_DIR = Path("/tmp/globins_build")

UNIPROT_BASE = "https://rest.uniprot.org"
RCSB_BASE    = "https://files.rcsb.org/download"

# ---------------------------------------------------------------------------
# FASTA helpers
# ---------------------------------------------------------------------------

def fetch_uniprot_fasta(accession: str) -> str:
    """Fetch FASTA text for a single UniProt accession."""
    url = f"{UNIPROT_BASE}/uniprotkb/{accession}.fasta"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.text


def fetch_fasta_batch(accessions: list[str]) -> str:
    """Fetch FASTAs for multiple UniProt accessions in one request."""
    if not accessions:
        return ""
    url = f"{UNIPROT_BASE}/uniprotkb/accessions"
    r = requests.get(url, params={"accessions": ",".join(accessions), "format": "fasta"},
                     timeout=60)
    r.raise_for_status()
    return r.text


def parse_fasta(text: str) -> list[tuple[str, str]]:
    """Parse FASTA text into list of (header, sequence)."""
    records: list[tuple[str, str]] = []
    header = ""
    parts: list[str] = []
    for line in text.splitlines():
        if line.startswith(">"):
            if header:
                records.append((header, "".join(parts)))
            header = line[1:].strip()
            parts = []
        else:
            parts.append(line.strip())
    if header:
        records.append((header, "".join(parts)))
    return records


def write_fasta(records: list[tuple[str, str]], path: Path) -> None:
    """Write (header, sequence) pairs as FASTA with 60-char line width."""
    with open(path, "w") as f:
        for header, seq in records:
            f.write(f">{header}\n")
            for i in range(0, len(seq), 60):
                f.write(seq[i:i+60] + "\n")


def count_seqs(path: Path) -> int:
    count = 0
    with open(path) as f:
        for line in f:
            if line.startswith(">"):
                count += 1
    return count

# ---------------------------------------------------------------------------
# BLAST search
# ---------------------------------------------------------------------------

def blast_search(seed_seq: str, label: str) -> list[str]:
    """
    Run BLASTP against Swiss-Prot via NCBI, return UniProt accessions that
    pass E-value < 1e-5 and query coverage >= 70%.
    No cap on the number of results (hitlist_size=20000).
    """
    print(f"  Running NCBI BLASTP (this may take a few minutes)...")

    result_handle = NCBIWWW.qblast(
        "blastp",
        "swissprot",
        seed_seq,
        expect=EVALUE_THRESHOLD,
        hitlist_size=20000,
        matrix_name="BLOSUM62",
    )

    blast_record = NCBIXML.read(result_handle)
    query_len = blast_record.query_length
    print(f"  Query length: {query_len} aa, BLAST hits: {len(blast_record.alignments)}")

    # Debug: show the raw title format so we can verify regex
    for i, aln in enumerate(blast_record.alignments[:3]):
        acc_attr = getattr(aln, 'accession', 'N/A')
        print(f"  Sample hit {i+1}: accession={acc_attr!r}  title={aln.title[:100]!r}")

    rows: list[dict] = []           # all hits, for saving to TSV
    accessions: list[str] = []      # passing hits only

    for aln in blast_record.alignments:
        best = aln.hsps[0]
        evalue = best.expect
        # query_start/end are 1-based in BioPython NCBIXML
        query_cov = (best.query_end - best.query_start + 1) / query_len
        identity_pct = best.identities / best.align_length * 100 if best.align_length else 0
        passes = evalue <= EVALUE_THRESHOLD and query_cov >= COVERAGE_MIN

        # Extract all UniProt accessions from title (handles merged hits like
        # "sp|P69905|HBA_HUMAN ... >sp|P68872|HBA_PANTR ...").
        # UniProt accessions: 6-char ([OPQ][0-9][A-Z0-9]{3}[0-9]) or 10-char.
        # Use a relaxed pattern that matches any \w+ between sp| and |.
        accs_in_hit = re.findall(r'(?:sp|tr)\|(\w+)\|', aln.title)

        # Fallback: BioPython's own parsed accession field
        if not accs_in_hit:
            acc_attr = getattr(aln, 'accession', '') or ''
            if acc_attr:
                accs_in_hit = [acc_attr]

        # Always save one row per alignment for inspection
        rows.append({
            "accession": ",".join(accs_in_hit) if accs_in_hit else "(no_match)",
            "evalue": evalue,
            "identity_pct": round(identity_pct, 1),
            "query_coverage": round(query_cov * 100, 1),
            "passes_filter": passes and bool(accs_in_hit),
            "title": aln.title[:120],
        })

        if passes:
            accessions.extend(accs_in_hit)

    # Save all hits to TSV for inspection
    tsv_path = WORK_DIR / f"{label}_blast_hits.tsv"
    with open(tsv_path, "w") as fh:
        fh.write("accession\tevalue\tidentity_pct\tquery_coverage\tpasses_filter\ttitle\n")
        for row in rows:
            fh.write(
                f"{row['accession']}\t{row['evalue']:.2e}\t{row['identity_pct']}\t"
                f"{row['query_coverage']}\t{row['passes_filter']}\t{row['title']}\n"
            )
    print(f"  Saved {len(rows)} BLAST hits to {tsv_path}")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique = []
    for acc in accessions:
        if acc not in seen:
            seen.add(acc)
            unique.append(acc)

    print(f"  Accessions after E-value/coverage filter: {len(unique)}")
    return unique

# ---------------------------------------------------------------------------
# Length filter
# ---------------------------------------------------------------------------

def filter_by_length(
    records: list[tuple[str, str]],
    seed_len: int,
    tolerance: float = LENGTH_TOLERANCE,
) -> list[tuple[str, str]]:
    """Remove sequences whose ungapped length differs from seed_len by > tolerance."""
    lo = int(seed_len * (1 - tolerance))
    hi = int(seed_len * (1 + tolerance))
    kept, removed = [], []
    for header, seq in records:
        n = len(seq.replace("-", ""))
        if lo <= n <= hi:
            kept.append((header, seq))
        else:
            removed.append((header, n))
    if removed:
        print(f"  Length filter ({lo}–{hi} aa) removed {len(removed)} sequences:")
        for h, n in removed:
            print(f"    {h[:70]}: {n} aa")
    return kept

# ---------------------------------------------------------------------------
# CD-HIT and MAFFT
# ---------------------------------------------------------------------------

def run_cdhit(input_fasta: Path, output_stem: Path,
              identity: float, coverage: float) -> Path:
    """Run CD-HIT; return path to the clustered FASTA output."""
    cmd = [
        "cd-hit",
        "-i", str(input_fasta),
        "-o", str(output_stem),
        "-c", str(identity),
        "-aL", str(coverage),
        "-n", "5",
        "-T", "4",
        "-M", "4000",
    ]
    print(f"  Running CD-HIT...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"CD-HIT failed:\n{result.stderr[:500]}")
    # CD-HIT writes to output_stem (no extension); rename to .fasta
    fasta_out = Path(str(output_stem) + ".fasta")
    if output_stem.exists() and not fasta_out.exists():
        output_stem.rename(fasta_out)
    return fasta_out if fasta_out.exists() else output_stem


def run_mafft_linsi(input_fasta: Path, output_fasta: Path) -> None:
    """Run MAFFT L-INS-i alignment."""
    n = count_seqs(input_fasta)
    print(f"  Running MAFFT L-INS-i on {n} sequences...")
    cmd = ["mafft", "--localpair", "--maxiterate", "1000", "--quiet", str(input_fasta)]
    with open(output_fasta, "w") as out_f:
        result = subprocess.run(cmd, stdout=out_f, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"MAFFT failed:\n{result.stderr[:300]}")

# ---------------------------------------------------------------------------
# all.fasta
# ---------------------------------------------------------------------------

def build_cross_alignment(aligned_files: dict[str, Path], out_path: Path) -> None:
    """
    Combine all group alignments into a single unaligned FASTA, re-align with
    MAFFT L-INS-i.  Headers are kept verbatim so the cross-conservation code
    can look up representatives by their sequence ID.
    """
    all_seqs: list[tuple[str, str]] = []
    for aligned_path in aligned_files.values():
        for header, seq in parse_fasta(aligned_path.read_text()):
            all_seqs.append((header, seq.replace("-", "")))

    tmp = out_path.parent / "all_unaligned.fasta"
    write_fasta(all_seqs, tmp)
    print(f"\nBuilding all.fasta ({len(all_seqs)} sequences)...")
    run_mafft_linsi(tmp, out_path)
    tmp.unlink()

# ---------------------------------------------------------------------------
# PDB download
# ---------------------------------------------------------------------------

def download_pdb(pdb_id: str, out_path: Path) -> None:
    url = f"{RCSB_BASE}/{pdb_id.upper()}.pdb"
    print(f"  Downloading {url}...")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    out_path.write_text(r.text)

# ---------------------------------------------------------------------------
# Per-group pipeline
# ---------------------------------------------------------------------------

def build_group(group_label: str, seed_acc: str, work_dir: Path) -> Path | None:
    """
    Full pipeline for one protein group.
    Returns path to the aligned FASTA, or None on failure.
    """
    print(f"\n{'='*60}")
    print(f"Group: {group_label}  (seed: {seed_acc})")
    print('='*60)

    # 1. Seed sequence
    seed_fasta_text = fetch_uniprot_fasta(seed_acc)
    seed_records = parse_fasta(seed_fasta_text)
    if not seed_records:
        print(f"  ERROR: no FASTA for {seed_acc}")
        return None
    seed_header, seed_seq = seed_records[0]
    seed_len = len(seed_seq)
    print(f"  Seed: {seed_header[:80]}")
    print(f"  Seed length: {seed_len} aa")

    # 2. BLAST search
    hit_accs = blast_search(seed_seq, group_label)
    if not hit_accs:
        print("  No BLAST hits — cannot build group.")
        return None

    # 3. Fetch FASTAs for all hits (batch 200 at a time)
    print(f"  Fetching FASTAs for {len(hit_accs)} accessions...")
    all_records: list[tuple[str, str]] = []
    batch_size = 200
    for i in range(0, len(hit_accs), batch_size):
        batch = hit_accs[i:i+batch_size]
        text = fetch_fasta_batch(batch)
        all_records.extend(parse_fasta(text))
        time.sleep(0.3)

    # Ensure seed is first; deduplicate
    seed_id = re.search(r'\|([A-Z][0-9][A-Z0-9]{3}[0-9])\|', seed_header)
    seed_id_str = seed_id.group(1) if seed_id else ""
    deduped: dict[str, tuple[str, str]] = {}
    if seed_id_str:
        deduped[seed_id_str] = (seed_header, seed_seq)
    for header, seq in all_records:
        m = re.search(r'\|([A-Z][0-9][A-Z0-9]{3}[0-9])\|', header)
        if m and m.group(1) not in deduped:
            deduped[m.group(1)] = (header, seq)
    records = list(deduped.values())
    print(f"  Unique sequences after dedup: {len(records)}")

    # 4. Length filter
    records = filter_by_length(records, seed_len)
    if len(records) < 3:
        print(f"  Too few sequences after length filter ({len(records)}), skipping.")
        return None

    # 5. Write unaligned FASTA
    raw_path = work_dir / f"{group_label}_raw.fasta"
    write_fasta(records, raw_path)
    print(f"  Wrote {len(records)} sequences → {raw_path.name}")

    # 6. CD-HIT at 90%
    cdhit_stem = work_dir / f"{group_label}_cdhit90"
    try:
        cdhit_fasta = run_cdhit(raw_path, cdhit_stem, CDHIT_IDENTITY, CDHIT_COVERAGE)
    except Exception as e:
        print(f"  CD-HIT failed ({e}), using unfiltered sequences.")
        cdhit_fasta = raw_path
    print(f"  CD-HIT representatives: {count_seqs(cdhit_fasta)}")

    # 7. MAFFT L-INS-i
    aligned_path = work_dir / f"{group_label}_aligned.fasta"
    run_mafft_linsi(cdhit_fasta, aligned_path)

    # Copy to output dir
    out_fasta = OUT_DIR / f"{group_label}.fasta"
    shutil.copy(aligned_path, out_fasta)
    print(f"  Saved: {out_fasta.name} ({count_seqs(out_fasta)} seqs, "
          f"{len(next(iter(parse_fasta(out_fasta.read_text())), ('',''))[1])} cols)")

    return aligned_path

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Globins Example Data Builder")
    print("=" * 60)

    aligned_files: dict[str, Path] = {}
    for group_label, seed_acc in SEEDS.items():
        result = build_group(group_label, seed_acc, WORK_DIR)
        if result:
            aligned_files[group_label] = result

    # Build cross-alignment
    if len(aligned_files) >= 2:
        all_fasta_path = OUT_DIR / "all.fasta"
        build_cross_alignment(aligned_files, all_fasta_path)
        print(f"  Saved: all.fasta ({count_seqs(all_fasta_path)} seqs)")
    else:
        print("\nNot enough groups for all.fasta.")

    # Download PDB files
    print(f"\n{'='*60}")
    print("Downloading PDB files...")
    downloaded: set[str] = set()
    for pdb_id in PDBS.values():
        if pdb_id in downloaded:
            continue
        pdb_path = OUT_DIR / f"{pdb_id.upper()}.pdb"
        try:
            download_pdb(pdb_id, pdb_path)
            downloaded.add(pdb_id)
            print(f"  Saved {pdb_path.name}")
        except Exception as e:
            print(f"  Failed to download {pdb_id}: {e}")

    # Package ZIP
    print(f"\n{'='*60}")
    print(f"Packaging {ZIP_OUT.name}...")
    with zipfile.ZipFile(ZIP_OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(OUT_DIR.iterdir()):
            if f.suffix in (".fasta", ".pdb"):
                zf.write(f, f.name)
                print(f"  Added: {f.name}")

    print(f"\nDone!  ZIP size: {ZIP_OUT.stat().st_size // 1024} KB")
    print("\nSummary:")
    for label in SEEDS:
        p = OUT_DIR / f"{label}.fasta"
        if p.exists():
            print(f"  {label}: {count_seqs(p)} sequences")


if __name__ == "__main__":
    main()
