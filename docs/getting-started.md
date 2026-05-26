# Getting Started

This guide covers running Alvis locally. If you want to use alvis, you can use it in [alvis.idameitil.dk](https://alvis.idameitil.dk). Two paths are supported:

- **Option A — Docker** (recommended): one command, no system dependencies to install
- **Option B — Local Python venv**: faster reload cycle if you're developing the app itself, but you must install DSSP yourself

Both paths serve the app on **`http://localhost:5001`**.

## Prerequisites

- Git
- One of:
  - **Docker** with Compose v2 (for Option A)
  - **Python 3.9+** and **DSSP** (for Option B)

## Option A — Docker

From the repo root:

```bash
docker compose up
```

Then open `http://localhost:5001`.

The dev compose file mounts your local code into the container and runs Flask's built-in dev server (`python app.py` with `debug=True`), so edits to `.py` files are picked up automatically by Werkzeug's reloader, and unhandled exceptions show the interactive in-browser debugger. The PIN for the debugger appears in `docker compose logs web`.

> Production runs Gunicorn (see [deployment.md](deployment.md)). Dev runs Flask's dev server so you get the Werkzeug debugger and a step-through debugger via debugpy (below).

To stop:

```bash
docker compose down
```

When `Dockerfile` or `requirements.txt` changes, rebuild:

```bash
docker compose up --build
```

### Attaching a debugger from VS Code

The dev container starts a `debugpy` listener on port `5678` (enabled by the `DEBUGPY=1` env var in `docker-compose.yml`). To step through code:

1. Start the container: `docker compose up` (rebuild once after pulling these changes so `debugpy` is installed: `docker compose up --build`)
2. In VS Code, open **Run & Debug** (Ctrl+Shift+D), select **"Attach to Docker (debugpy)"**, press F5
3. Set breakpoints — they'll hit when matching requests come in

Notes:
- On every Flask reload (auto-triggered by saving a `.py` file), the debugpy session disconnects. Press F5 again to re-attach.
- To disable debugpy entirely, remove or unset `DEBUGPY=1` in `docker-compose.yml`. The app still runs normally; the listener just isn't started.
- The VS Code config lives in `.vscode/launch.json` and maps `${workspaceFolder}` ↔ `/app` for breakpoints.

## Option B — Local Python venv

### 1. Install Python dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Install DSSP

DSSP is an external binary — BioPython calls it as a subprocess.

```bash
# macOS (Homebrew)
brew install dssp

# Conda (any platform)
conda install -c salilab dssp

# Ubuntu / Debian
sudo apt install dssp
```

Verify it works:

```bash
mkdssp --version
```

### 3. Run the app

```bash
python app.py
```

Then open `http://localhost:5001`.

## Usage

1. **Prepare your data:**
   - Create a ZIP file containing your FASTA alignment files
   - Files should have extensions: `.fasta`, `.fa`, `.faa`, or `.fas`
   - Each FASTA file should contain a protein sequence alignment (all sequences same length)
   - The first sequence in each file will be used as the representative

2. **Upload and configure:**
   - Upload your ZIP file
   - Choose to use the default 95% conservation threshold for all files, or customize per file
   - Click "Generate SVG"

3. **Download:**
   - The SVG will be automatically downloaded
   - Open with any SVG viewer or import into Illustrator / Inkscape for further editing

## Running tests

Tests run inside the Docker container:

```bash
docker compose run --rm web python -m pytest tests/ -v
```