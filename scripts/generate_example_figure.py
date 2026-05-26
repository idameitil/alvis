#!/usr/bin/env python3
"""
Generate static/example_figure.svg from the bundled example data.

Run once after changing example data or SVG styling:
    docker compose run --rm web python scripts/generate_example_figure.py
"""
from __future__ import annotations
import os
import sys

# Make project root importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models.session import Session
from models.analysis import build_result

EXAMPLE_DIR = os.path.join(os.path.dirname(__file__), '..', 'example_data', 'globins_example')
OUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'static', 'example_figure.svg')


def main():
    session = Session.create_new('example-figure-gen')
    try:
        for name in ['HBA.fasta', 'HBB.fasta', 'MB.fasta']:
            with open(os.path.join(EXAMPLE_DIR, name), 'r') as f:
                session.add_fasta_content(name, f.read())

        with open(os.path.join(EXAMPLE_DIR, 'all.fasta'), 'r') as f:
            session.add_cross_fasta_content('all.fasta', f.read())

        for pdb_name in ['1A3N.pdb', '3RGK.pdb']:
            with open(os.path.join(EXAMPLE_DIR, pdb_name), 'rb') as f:
                session.add_pdb_from_bytes(pdb_name, f.read())

        session.update_config(
            display_names={
                'HBA.fasta': 'Hemoglobin \u03b1',
                'HBB.fasta': 'Hemoglobin \u03b2',
                'MB.fasta':  'Myoglobin',
            },
            chain_assignments={
                'HBA.fasta': {'pdb_filename': '1A3N.pdb', 'chain_id': 'A'},
                'HBB.fasta': {'pdb_filename': '1A3N.pdb', 'chain_id': 'B'},
                'MB.fasta':  {'pdb_filename': '3RGK.pdb',  'chain_id': 'A'},
            },
            cross_threshold=95.0,
        )

        result = build_result(session)
    finally:
        session.cleanup()

    with open(OUT_PATH, 'w') as f:
        f.write(result.svg)

    print(f'Saved {os.path.relpath(OUT_PATH)} ({len(result.svg) // 1024} KB)')


if __name__ == '__main__':
    main()
