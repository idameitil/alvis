# Project Structure

## Updated Directory Layout

```
alvis/
├── 📱 Application
│   ├── app.py                      # Flask application (NEEDS UPDATE)
│   ├── conservation.py             # Conservation analysis
│   └── svg_generator.py            # SVG generation
│
├── 🗄️ Database Layer (NEW)
│   ├── config.py                   # Database configuration
│   ├── setup_db.py                 # Database setup script
│   ├── schema.sql                  # SQL schema definition
│   ├── setup_user.sql              # User creation SQL
│   └── models/
│       ├── __init__.py
│       ├── database.py             # DB connection
│       └── models.py               # SQLAlchemy models
│
├── 🎨 Frontend
│   ├── templates/
│   │   └── index.html             # Web interface (NEEDS UPDATE)
│   └── static/
│       └── style.css              # Styling
│
├── 📝 Configuration
│   ├── .env.example               # Environment template
│   ├── requirements.txt           # Python dependencies (UPDATED)
│   └── .gitignore
│
├── 📚 Documentation (NEW)
│   ├── README.md                  # Main readme
│   ├── DATABASE_SETUP.md          # Setup guide
│   ├── SCHEMA_SUMMARY.md          # Schema overview
│   └── PROJECT_STRUCTURE.md       # This file
│
└── 🧪 Test Data
    ├── example_alignment.fasta
    ├── example_alignment2.fasta
    └── test_alignments.zip
```

## Components Status

### ✅ Completed (Phase 1)
- [x] Database schema design
- [x] SQLAlchemy models
- [x] Configuration management
- [x] Setup scripts
- [x] Documentation

### 🔄 Needs Implementation (Phase 2)
- [ ] Update app.py with DB integration
- [ ] Add Recent Projects UI
- [ ] Add Save Project functionality
- [ ] Add Load Project functionality
- [ ] Create service layer

### 🚧 Future Features (Phase 3+)
- [ ] PDB file upload
- [ ] Secondary structure parsing
- [ ] Enhanced visualizations
- [ ] User management
- [ ] API endpoints

## Key Files Reference

| File | Purpose | Status |
|------|---------|--------|
| `schema.sql` | Database schema | ✅ Ready |
| `models/models.py` | ORM models | ✅ Ready |
| `setup_db.py` | Database initialization | ✅ Ready |
| `config.py` | App configuration | ✅ Ready |
| `DATABASE_SETUP.md` | Setup instructions | ✅ Ready |
| `app.py` | Flask app | 🔄 Needs DB integration |
| `templates/index.html` | Frontend | 🔄 Needs UI updates |

## Dependencies Added

```python
# New in requirements.txt
Flask-SQLAlchemy==3.1.1    # ORM
PyMySQL==1.1.0             # MySQL driver  
cryptography==41.0.7       # Security for PyMySQL
```

## Environment Variables

Required in `.env`:
```bash
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=alvis_user
MYSQL_PASSWORD=alvis_password
MYSQL_DATABASE=alvis
SECRET_KEY=your-secret-key
```
