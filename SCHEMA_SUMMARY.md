# Database Schema Summary

## Files Created

### Configuration & Setup
- **[schema.sql](schema.sql)** - Raw SQL schema (for reference)
- **[setup_user.sql](setup_user.sql)** - Manual user/database creation
- **[setup_db.py](setup_db.py)** - Automated Python setup script
- **[config.py](config.py)** - Application configuration
- **[.env.example](.env.example)** - Environment variables template
- **[DATABASE_SETUP.md](DATABASE_SETUP.md)** - Complete setup guide

### Models
- **[models/__init__.py](models/__init__.py)** - Package initialization
- **[models/database.py](models/database.py)** - Database connection
- **[models/models.py](models/models.py)** - SQLAlchemy models

### Updated
- **[requirements.txt](requirements.txt)** - Added database dependencies

## Database Structure

```
┌─────────────────┐
│    projects     │  ← Analysis sessions
│─────────────────│
│ id (PK)         │
│ name            │
│ description     │
│ created_at      │
│ updated_at      │
└─────────────────┘
        │
        │ 1:N
        ▼
┌─────────────────┐
│   alignments    │  ← FASTA files
│─────────────────│
│ id (PK)         │
│ project_id (FK) │
│ filename        │
│ num_sequences   │
│ sequence_length │
│ threshold       │
└─────────────────┘
        │
        │ 1:N
        ▼
┌──────────────────────┐
│ conserved_positions  │  ← Analysis results
│──────────────────────│
│ id (PK)              │
│ alignment_id (FK)    │
│ position             │
│ residue              │
│ conservation_pct     │
└──────────────────────┘

┌─────────────────┐
│ visualizations  │  ← Generated SVGs
│─────────────────│
│ id (PK)         │
│ project_id (FK) │◄── 1:1 with projects
│ svg_content     │
└─────────────────┘
```

## Quick Start

### Option 1: Automated Setup (Recommended)

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Edit .env with your MySQL credentials
nano .env

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run setup script
python setup_db.py
```

### Option 2: Manual Setup

```bash
# 1. Create user and database
mysql -u root -p < setup_user.sql

# 2. Create tables from schema
mysql -u alvis_user -p alvis < schema.sql

# 3. Install dependencies
pip install -r requirements.txt
```

## Data Flow

### Current Workflow (No DB):
```
Upload ZIP → Process → Generate SVG → Display → Gone
```

### New Workflow (With DB):
```
Upload ZIP → Process → Generate SVG → Display
                ↓
          Save to Database
                ↓
          Available in "Recent Projects"
```

## What's NOT Included Yet

We intentionally kept the schema minimal. Not included:
- ❌ User management
- ❌ PDB structures
- ❌ Secondary structure data
- ❌ Sequence details (beyond what's in alignments)
- ❌ File storage paths (everything in DB for now)

These can be added later when implementing PDB integration!

## Next Implementation Steps

After database setup, you'll need to:

1. **Update app.py**
   - Initialize database connection
   - Add `/projects` route (list recent)
   - Add `/projects/<id>` route (load specific)
   - Modify `/generate` to save results

2. **Update frontend**
   - Add "Recent Projects" button
   - Create projects list modal
   - Add "Save Project" dialog

3. **Add service layer**
   - `services/project_service.py` - CRUD operations
   - Handle database transactions
   - Serialize/deserialize data

Would you like me to implement any of these next steps?
