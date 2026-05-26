# Protein Alignment Conservation Analyzer
[![DOI](https://zenodo.org/badge/1156497058.svg)](https://doi.org/10.5281/zenodo.20375232)

A web platform for visualizing conserved residues in protein sequence alignments. Try it at [alvis.idameitil.dk](https://alvis.idameitil.dk).

![Example conservation visualization](static/example_figure.svg)

## Features

- Upload ZIP files containing multiple FASTA alignment files
- Configure conservation thresholds (global or per-file)
- Generate SVG visualization with:
  - Color-coded conserved residues
  - Smart label positioning to avoid overlap
  - Sequence position markers
  - File names for each alignment
- Download publication-ready SVG figures

## Documentation

- **[Getting started](docs/getting-started.md)** — install, run locally (Docker or Python), and a usage walkthrough
- **[Deployment](docs/deployment.md)** — production deployment guide (nginx + Docker on a VM)

## Color Scheme

Residues are colored using the ClustalX color scheme:
- **Blue** : A, V, I, L, M, F, W, P (hydrophobic)
- **Red** : K, R (basic/positive)
- **Magenta** : D, E (acidic/negative)
- **Green** : N, Q, S, T (polar)
- **Pink** : C (cysteine)
- **Orange** : G (glycine)
- **Cyan** : H, Y (aromatic/histidine)

## Technical Details

- **Maximum sequence length:** 400 residues
- **Conservation calculation:** Based on the most common residue at each position in the alignment
- **Label positioning:** Automatic vertical stacking when residues are clustered
- **File size limit:** 50 MB ZIP upload

## Project Structure

```
alvis/
├── app.py                 # Flask application
├── conservation.py        # Conservation analysis logic
├── structure.py           # Secondary structure extraction (PDB + DSSP)
├── svg_generator.py       # SVG generation with smart positioning
├── requirements.txt       # Python dependencies
├── models/                # Dataclasses + business logic
├── routes/                # Flask blueprints
├── templates/             # HTML templates
├── static/                # CSS, JS
├── docs/                  # Getting-started + deployment docs
└── deployment/            # Production compose file + nginx config
```

## Example FASTA Alignment Format

```
>Sequence1
MVHLTPEEKSAVTALWGKVN--VDEVGGEALG
>Sequence2
MVHLTPEEKTAVTALWGKVN--VDEVGGEALG
>Sequence3
MVHLTPEEKSAVNALWGKVNVGDEVGGEALG
```

## Citation

If you use Alvis in your research, please cite:

```bibtex
@software{meitil2026alvis,
  author       = {Meitil, Ida K. S. and Martinez Pineda, Diego Joshua},
  title        = {Alvis: Protein Alignment Conservation Visualizer},
  year         = {2026},
  version      = {1.0.0},
  doi          = {10.5281/zenodo.20375233},
  url          = {https://github.com/idameitil/alvis}
}
```

## License

Alvis is released under the MIT license. See [LICENSE](LICENSE).
