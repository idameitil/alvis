# Plan: Remove database/projects, add session tokens

## Goal

Strip out the projects/database layer entirely and replace the exposed
`temp_dir` filesystem paths with opaque session tokens. After this change
the app is a stateless tool: upload → configure → generate → download.

---

## What gets removed

| File / code | Action |
|-------------|--------|
| `models/models.py` | Delete file |
| `models/database.py` | Delete file |
| `models/__init__.py` | Delete file |
| `models/` directory | Delete directory |
| `services/project_service.py` | Delete file |
| `services/` directory | Delete directory |
| `schema.sql` | Delete file |
| `setup_db.py` | Delete file |
| `setup_user.sql` | Delete file |
| `DATABASE_SETUP.md` | Delete file |
| `.env` | Delete file (only held DB credentials) |
| `.env.example` | Delete file |
| `config.py` | Delete file (only held DB config + SECRET_KEY; SECRET_KEY moves inline) |

### Endpoints removed from `app.py`

| Route | Method | Purpose |
|-------|--------|---------|
| `/debug/db-test` | GET | DB connection test |
| `/projects` | GET | List recent projects |
| `/projects/<id>` | GET | Load a project |
| `/projects/create` | POST | Create a project |
| `/projects/<id>` | DELETE | Delete a project |

### Frontend code removed from `index.html`

- `currentProjectId` variable
- "Recent Projects" button + modal + all related functions
  (`showRecentProjects`, `displayProjects`, `loadProject`,
  `deleteProject`, `closeProjectsModal`)
- "Save Project" button + modal + all related functions
  (`showSaveDialog`, `saveProject`, `closeSaveModal`)
- `project_id` from all `/generate` request bodies
- The entire save flow (projects/create → /generate with project_id)

### Dependencies removed from `requirements.txt`

- `Flask-SQLAlchemy`
- `PyMySQL`
- `cryptography` (only needed for PyMySQL)
- `python-dotenv` (only loaded .env for DB creds)

---

## What gets added: session token store

### New module: `session_store.py`

A small in-memory dict mapping tokens to temp dir paths, with timestamps
for garbage collection.

```python
import uuid
import time
import os
import shutil
import threading

_sessions = {}       # {token: {'temp_dir': str, 'created_at': float}}
_lock = threading.Lock()
MAX_AGE = 3600       # 1 hour

def create(temp_dir):
    """Register a temp dir and return an opaque token."""
    token = uuid.uuid4().hex
    with _lock:
        _sessions[token] = {
            'temp_dir': temp_dir,
            'created_at': time.time()
        }
    return token

def get_temp_dir(token):
    """Look up the temp dir for a token. Returns None if invalid/expired."""
    with _lock:
        session = _sessions.get(token)
    if not session:
        return None
    if not os.path.exists(session['temp_dir']):
        remove(token)
        return None
    return session['temp_dir']

def remove(token):
    """Delete session + its temp dir."""
    with _lock:
        session = _sessions.pop(token, None)
    if session and os.path.exists(session['temp_dir']):
        shutil.rmtree(session['temp_dir'], ignore_errors=True)

def cleanup_expired():
    """Remove sessions older than MAX_AGE."""
    now = time.time()
    with _lock:
        expired = [t for t, s in _sessions.items()
                   if now - s['created_at'] > MAX_AGE]
    for token in expired:
        remove(token)
```

Thread-safe, no dependencies. `cleanup_expired()` is called
opportunistically (e.g. on each `/upload` call) rather than via a
background thread — keeps it simple.

---

## Changes per file

### 1. `app.py`

**Imports — remove:**
```python
from config import Config
from models.database import db
from services import project_service
```

**Imports — add:**
```python
import session_store
```

**App setup — remove:**
```python
app.config['SQLALCHEMY_DATABASE_URI'] = ...
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = ...
app.config['SECRET_KEY'] = ...
db.init_app(app)
```

**App setup — keep/simplify:**
```python
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
```

**`/upload` route:**
- After extracting files and building the response, replace:
  ```python
  response['temp_dir'] = temp_dir
  ```
  with:
  ```python
  token = session_store.create(temp_dir)
  response['session_token'] = token
  ```
- Call `session_store.cleanup_expired()` at the top of the function
  (opportunistic GC)
- Remove `temp_dir` from the response entirely

**`/upload-pdb` route:**
- Read `session_token` from the form data instead of `temp_dir`
- Resolve via `session_store.get_temp_dir(token)`
- Return 400 if token is invalid

**`/generate` route:**
- Read `session_token` instead of `temp_dir` from JSON body
- Resolve via `session_store.get_temp_dir(token)`
- **Remove** `project_id` parameter and all DB-save logic
  (the `if project_id:` block that calls `project_service.save_project_data`
  and does `shutil.rmtree`)
- The route never deletes the temp dir — that's `/cleanup`'s job
- Return `session_token` (not `temp_dir`) in the response so the
  frontend can still call `/cleanup` later

**`/cleanup` route:**
- Read `session_token` instead of `temp_dir`
- Call `session_store.remove(token)`

**Delete these route functions entirely:**
- `db_test`
- `get_projects`
- `get_project`
- `create_project`
- `delete_project`

### 2. `templates/index.html`

**Variables — remove:**
- `currentProjectId`

**`sessionData` shape changes:**
- `sessionData.temp_dir` → `sessionData.session_token`
  (every reference: uploadPdb, generateSVG, cancelSession, resetApp,
  saveProject)

**Remove UI elements:**
- "Recent Projects" button from header
- `#projects-modal` (entire modal)
- `#save-modal` (entire modal)
- "Save Project" button from result section button group

**Remove functions:**
- `showRecentProjects`, `displayProjects`, `loadProject`,
  `deleteProject`, `closeProjectsModal`
- `showSaveDialog`, `saveProject`, `closeSaveModal`
- The `window.onclick` handler for closing modals

**`uploadFile()`:**
- No change to logic (sessionData stores whatever the server returns)

**`uploadPdb()`:**
- Change `formData.append('temp_dir', sessionData.temp_dir)` →
  `formData.append('session_token', sessionData.session_token)`

**`generateSVG()`:**
- Change `temp_dir: sessionData.temp_dir` →
  `session_token: sessionData.session_token`
- Remove `project_id: currentProjectId` from the request body
- Simplify `window.currentResults` — drop `fasta_files` and
  project-related fields (only `svg` and `thresholds` are still used
  for potential re-generate)

**`cancelSession()` and `resetApp()`:**
- Change `temp_dir: sessionData.temp_dir` →
  `session_token: sessionData.session_token`
- Remove `currentProjectId = null`

### 3. `static/style.css`

Remove styles that only served the project modals and save flow:
- `.modal`, `.modal-content`, `.modal-header`, `.modal-body` — **keep**
  only if another modal still exists; otherwise delete all modal styles
- `.close` — same
- `.project-item`, `.project-info`, `.project-meta`, `.project-desc`,
  `.project-actions`, `.no-projects` — delete
- `.delete-btn` — delete

Since removing all modals leaves no modal users, delete all modal-related
CSS.

### 4. `requirements.txt`

Remove:
```
Flask-SQLAlchemy==3.1.1
PyMySQL==1.1.0
cryptography==41.0.7
python-dotenv==1.0.0
```

Keep:
```
Flask==3.0.0
biopython==1.83
svgwrite==1.4.3
```

### 5. New file: `session_store.py`

As described above.

### 6. Delete files

```
rm -r models/
rm -r services/
rm config.py
rm schema.sql
rm setup_db.py
rm setup_user.sql
rm DATABASE_SETUP.md
rm .env
rm .env.example
```

---

## Implementation order

1. **Create `session_store.py`** — no dependencies on anything else
2. **Update `app.py`** — gut DB code, wire in session_store, remove
   project endpoints
3. **Update `templates/index.html`** — remove project UI, switch
   `temp_dir` → `session_token`
4. **Update `static/style.css`** — remove dead modal/project styles
5. **Update `requirements.txt`** — remove DB dependencies
6. **Delete dead files** — models/, services/, config.py, schema.sql,
   setup_db.py, setup_user.sql, DATABASE_SETUP.md, .env, .env.example
7. **Smoke test** — upload ZIP, set thresholds, generate, download

---

## Verification

1. Upload a ZIP → response contains `session_token` (not a filesystem
   path)
2. Upload PDB → works using `session_token`
3. Generate → works using `session_token`, no `project_id` in payload
4. Download SVG → works as before
5. Cancel/Start Over → calls `/cleanup` with `session_token`, temp dir
   is deleted
6. No `/projects` endpoints respond (404)
7. No database connection attempted on startup
8. Inspect network tab: no filesystem paths visible in any request or
   response
