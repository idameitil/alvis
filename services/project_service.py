"""
Project service for database operations
Handles CRUD operations for projects, alignments, and visualizations
"""
from datetime import datetime
from models.database import db
from models.models import Project, Alignment, ConservedPosition, Visualization


def create_project(name, description=None):
    """
    Create a new project

    Args:
        name: Project name
        description: Optional project description

    Returns:
        Project: Created project object
    """
    project = Project(
        name=name,
        description=description
    )
    db.session.add(project)
    db.session.commit()
    return project


def get_recent_projects(limit=10):
    """
    Get most recent projects

    Args:
        limit: Maximum number of projects to return

    Returns:
        list: List of project dictionaries
    """
    projects = Project.query.order_by(
        Project.updated_at.desc()
    ).limit(limit).all()

    return [p.to_dict() for p in projects]


def get_project_by_id(project_id):
    """
    Get a project by ID with all related data

    Args:
        project_id: Project ID

    Returns:
        dict: Complete project data including alignments and visualization
    """
    project = Project.query.get(project_id)
    if not project:
        return None

    # Get project data
    project_data = project.to_dict()

    # Get alignments with conserved positions
    alignments_data = []
    for alignment in project.alignments:
        alignment_dict = alignment.to_dict()

        # Get conserved positions for this alignment
        conserved = [
            {
                'position': cp.position,
                'residue': cp.residue,
                'conservation_pct': cp.conservation_pct
            }
            for cp in alignment.conserved_positions
        ]
        alignment_dict['conserved'] = conserved
        alignments_data.append(alignment_dict)

    project_data['alignments'] = alignments_data

    # Get visualization if exists
    if project.visualization:
        project_data['svg_content'] = project.visualization.svg_content
        print(f"Loaded project {project_id} with visualization (length: {len(project.visualization.svg_content)})")
    else:
        print(f"Warning: Project {project_id} has no visualization data")

    return project_data


def save_project_data(project_id, alignments, svg_content):
    """
    Save alignment analysis results and visualization to database

    Args:
        project_id: Project ID
        alignments: List of alignment dictionaries with conserved positions
        svg_content: SVG content string

    Returns:
        bool: True if successful
    """
    project = Project.query.get(project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")

    try:
        # Save alignments and conserved positions
        for alignment_data in alignments:
            # Create alignment record
            alignment = Alignment(
                project_id=project_id,
                filename=alignment_data['name'],
                num_sequences=alignment_data.get('num_sequences', 0),
                sequence_length=alignment_data['length'],
                conservation_threshold=alignment_data.get('threshold', 95.0)
            )
            db.session.add(alignment)
            db.session.flush()  # Get alignment ID

            # Save conserved positions
            for conserved in alignment_data['conserved']:
                position = ConservedPosition(
                    alignment_id=alignment.id,
                    position=conserved['position'],
                    residue=conserved['residue'],
                    conservation_pct=conserved['conservation']  # Key is 'conservation' not 'conservation_pct'
                )
                db.session.add(position)

        # Check if visualization already exists (shouldn't happen, but handle it)
        existing_viz = Visualization.query.filter_by(project_id=project_id).first()
        if existing_viz:
            # Update existing visualization
            existing_viz.svg_content = svg_content
        else:
            # Create new visualization
            visualization = Visualization(
                project_id=project_id,
                svg_content=svg_content
            )
            db.session.add(visualization)

        # Update project timestamp
        project.updated_at = datetime.utcnow()

        db.session.commit()
        print(f"Successfully saved project {project_id} with {len(alignments)} alignments")
        return True

    except Exception as e:
        db.session.rollback()
        print(f"Error saving project data: {str(e)}")
        raise e


def delete_project(project_id):
    """
    Delete a project and all related data

    Args:
        project_id: Project ID

    Returns:
        bool: True if successful, False if project not found
    """
    project = Project.query.get(project_id)
    if not project:
        return False

    db.session.delete(project)
    db.session.commit()
    return True


def update_project(project_id, name=None, description=None):
    """
    Update project metadata

    Args:
        project_id: Project ID
        name: New name (optional)
        description: New description (optional)

    Returns:
        Project: Updated project object or None if not found
    """
    project = Project.query.get(project_id)
    if not project:
        return None

    if name is not None:
        project.name = name
    if description is not None:
        project.description = description

    project.updated_at = datetime.utcnow()
    db.session.commit()

    return project
