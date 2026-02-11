# Phase 2 Implementation - Database Integration

## Summary

Phase 2 has been successfully implemented! The application now supports saving and loading projects from the MySQL database.

## What Was Implemented

### 1. Service Layer (`services/project_service.py`)

Created a complete service layer with the following functions:

- `create_project(name, description)` - Create a new project
- `get_recent_projects(limit)` - Get list of recent projects
- `get_project_by_id(project_id)` - Get complete project data
- `save_project_data(project_id, alignments, svg_content)` - Save analysis results
- `delete_project(project_id)` - Delete a project
- `update_project(project_id, name, description)` - Update project metadata

### 2. Backend Updates ([app.py](app.py))

Added database integration and new routes:

- **GET** `/projects` - List recent projects
- **GET** `/projects/<id>` - Get specific project with all data
- **POST** `/projects/create` - Create new project
- **DELETE** `/projects/<id>` - Delete project
- **Modified** `/generate` - Now accepts optional `project_id` to save results

Database initialization:
```python
from config import Config
from models.database import db
from services import project_service

app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLALCHEMY_DATABASE_URI
db.init_app(app)
```

### 3. Frontend Updates ([templates/index.html](templates/index.html))

Added complete Recent Projects UI:

#### New UI Components:
- **"Recent Projects" button** - In header to view saved projects
- **Recent Projects modal** - Shows list of saved projects with load/delete actions
- **Save Project modal** - Dialog to name and save current analysis
- **Save Project button** - In results section

#### New JavaScript Functions:
- `showRecentProjects()` - Display recent projects modal
- `displayProjects(projects)` - Render projects list
- `loadProject(projectId)` - Load and display saved project
- `deleteProject(projectId)` - Delete project with confirmation
- `showSaveDialog()` - Show save project dialog
- `saveProject()` - Create project and save analysis data

### 4. CSS Updates ([static/style.css](static/style.css))

Added styles for:
- Modal dialogs (overlay, content, header)
- Project list items (hover effects, layout)
- Form inputs (text, textarea)
- Button variants (secondary, delete)
- Header layout with Recent Projects button

## How It Works

### Saving a Project:

1. User uploads ZIP and generates analysis
2. User clicks "Save Project" button
3. Modal appears asking for project name and description
4. System creates project in database
5. System re-runs generation with `project_id` to save all data
6. Temp files are cleaned up
7. Project is saved with:
   - Project metadata (name, description, timestamps)
   - Alignment data (filename, sequences, length, threshold)
   - Conserved positions (position, residue, conservation %)
   - SVG visualization

### Loading a Project:

1. User clicks "Recent Projects" button
2. Modal shows list of saved projects (most recent first)
3. User clicks "Load" on desired project
4. System fetches complete project data from database
5. SVG visualization is displayed
6. User can download SVG or start over

### Deleting a Project:

1. User clicks "Delete" on project in list
2. Confirmation dialog appears
3. If confirmed, project and all related data are deleted (cascade)
4. Projects list automatically refreshes

## Database Schema Used

```
projects (id, name, description, created_at, updated_at)
    ↓ 1:N
alignments (id, project_id, filename, num_sequences, sequence_length, threshold)
    ↓ 1:N
conserved_positions (id, alignment_id, position, residue, conservation_pct)

projects (id)
    ↓ 1:1
visualizations (id, project_id, svg_content)
```

## Testing the Implementation

### Prerequisites:
1. Database setup completed (see [DATABASE_SETUP.md](DATABASE_SETUP.md))
2. Dependencies installed: `pip install -r requirements.txt`
3. `.env` file configured with MySQL credentials

### Test Workflow:

```bash
# 1. Start the application
python app.py

# 2. Open browser
open http://localhost:5000
```

#### Test Case 1: Create and Save Project
1. Upload `test_alignments.zip`
2. Configure thresholds (or use default 95%)
3. Click "Generate SVG"
4. Wait for visualization to appear
5. Click "Save Project"
6. Enter name: "Test Alignment 1"
7. Enter description: "Testing save functionality"
8. Click "Save"
9. Confirm success message appears

#### Test Case 2: View Recent Projects
1. Click "Recent Projects" button
2. Verify project appears in list
3. Check project name, description, and timestamp
4. Close modal

#### Test Case 3: Load Saved Project
1. Click "Recent Projects"
2. Click "Load" on saved project
3. Verify SVG visualization loads correctly
4. Verify "Download SVG" button works

#### Test Case 4: Delete Project
1. Click "Recent Projects"
2. Click "Delete" on a project
3. Confirm deletion in dialog
4. Verify project disappears from list

#### Test Case 5: Multiple Projects
1. Create several projects with different FASTA files
2. Verify all appear in Recent Projects list
3. Verify they are ordered by most recent first
4. Load different projects and verify correct data

### Verify Database:

```bash
# Connect to MySQL
mysql -u alvis_user -p alvis

# Check data
SELECT * FROM projects;
SELECT * FROM alignments;
SELECT * FROM conserved_positions LIMIT 10;
SELECT id, project_id, LENGTH(svg_content) as svg_size FROM visualizations;

# Check relationships
SELECT p.name, COUNT(a.id) as num_alignments
FROM projects p
LEFT JOIN alignments a ON p.id = a.project_id
GROUP BY p.id;
```

## API Endpoints Reference

### GET `/projects`
Returns list of recent projects.

**Query Parameters:**
- `limit` (optional): Number of projects to return (default: 10)

**Response:**
```json
{
  "projects": [
    {
      "id": 1,
      "name": "Test Alignment 1",
      "description": "Testing save functionality",
      "created_at": "2024-01-15T10:30:00",
      "updated_at": "2024-01-15T10:30:00"
    }
  ]
}
```

### GET `/projects/<id>`
Returns complete project data including alignments and visualization.

**Response:**
```json
{
  "id": 1,
  "name": "Test Alignment 1",
  "description": "Testing save functionality",
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00",
  "alignments": [
    {
      "id": 1,
      "filename": "alignment1.fasta",
      "num_sequences": 4,
      "sequence_length": 142,
      "conservation_threshold": 95.0,
      "conserved": [
        {"position": 10, "residue": "G", "conservation_pct": 100.0}
      ]
    }
  ],
  "svg_content": "<svg>...</svg>"
}
```

### POST `/projects/create`
Creates a new project.

**Request Body:**
```json
{
  "name": "Project Name",
  "description": "Optional description"
}
```

**Response:**
```json
{
  "id": 1,
  "name": "Project Name",
  "description": "Optional description",
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00"
}
```

### DELETE `/projects/<id>`
Deletes a project and all related data.

**Response:**
```json
{
  "success": true
}
```

### POST `/generate` (Modified)
Generate SVG with optional project saving.

**Request Body:**
```json
{
  "temp_dir": "/tmp/...",
  "thresholds": {
    "file1.fasta": 95.0,
    "file2.fasta": 90.0
  },
  "project_id": 1  // Optional: saves to this project
}
```

## Files Created/Modified

### New Files:
- `services/__init__.py` - Services package init
- `services/project_service.py` - Database operations service
- `PHASE2_IMPLEMENTATION.md` - This file

### Modified Files:
- `app.py` - Added database integration and new routes
- `templates/index.html` - Added Recent Projects UI and modals
- `static/style.css` - Added styles for new UI components

## Next Steps (Phase 3+)

Future enhancements to consider:

1. **PDB Integration**
   - Upload PDB files for protein structures
   - Parse secondary structure information
   - Visualize secondary structure alongside conservation

2. **Enhanced Visualizations**
   - Interactive SVG with tooltips
   - Zoom and pan functionality
   - Export to different formats (PNG, PDF)

3. **User Management**
   - User authentication
   - User-specific projects
   - Sharing projects between users

4. **Search and Filters**
   - Search projects by name/description
   - Filter by date range
   - Tag system for organization

5. **Batch Processing**
   - Process multiple ZIP files at once
   - Compare multiple alignments
   - Bulk export functionality

## Troubleshooting

### "No saved projects yet"
- Ensure database is set up correctly
- Check database connection in `.env`
- Verify tables exist: `SHOW TABLES;`

### "Error loading project"
- Check project exists in database
- Verify foreign key relationships
- Check server logs for details

### "Error saving project data"
- Ensure temp directory still exists
- Check database write permissions
- Verify alignment data is valid

### Modal doesn't appear
- Check browser console for JavaScript errors
- Verify CSS is loading correctly
- Clear browser cache

## Support

For issues or questions:
1. Check database connection: `python -c "from models.database import db; from flask import Flask; app = Flask(__name__); app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://alvis_user:alvis_password@localhost:3306/alvis'; db.init_app(app); print('OK')"`
2. Check server logs for errors
3. Verify all dependencies are installed
4. Review [DATABASE_SETUP.md](DATABASE_SETUP.md) for setup issues
