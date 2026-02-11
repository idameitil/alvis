"""
SQLAlchemy models for Alvis
"""
from datetime import datetime
from models.database import db


class Project(db.Model):
    """Analysis project/session"""
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    alignments = db.relationship('Alignment', back_populates='project', cascade='all, delete-orphan')
    visualization = db.relationship('Visualization', back_populates='project', uselist=False, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Project {self.id}: {self.name}>'

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'num_alignments': len(self.alignments) if self.alignments else 0
        }


class Alignment(db.Model):
    """FASTA alignment file"""
    __tablename__ = 'alignments'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    num_sequences = db.Column(db.Integer)
    sequence_length = db.Column(db.Integer)
    conservation_threshold = db.Column(db.Numeric(5, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    project = db.relationship('Project', back_populates='alignments')
    conserved_positions = db.relationship('ConservedPosition', back_populates='alignment', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Alignment {self.id}: {self.filename}>'

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'filename': self.filename,
            'num_sequences': self.num_sequences,
            'sequence_length': self.sequence_length,
            'conservation_threshold': float(self.conservation_threshold) if self.conservation_threshold else None,
            'num_conserved': len(self.conserved_positions) if self.conserved_positions else 0
        }


class ConservedPosition(db.Model):
    """Conserved residue position in alignment"""
    __tablename__ = 'conserved_positions'

    id = db.Column(db.Integer, primary_key=True)
    alignment_id = db.Column(db.Integer, db.ForeignKey('alignments.id'), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False)
    residue = db.Column(db.String(1), nullable=False)
    conservation_pct = db.Column(db.Numeric(5, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    alignment = db.relationship('Alignment', back_populates='conserved_positions')

    # Indexes
    __table_args__ = (
        db.Index('idx_alignment_position', 'alignment_id', 'position'),
    )

    def __repr__(self):
        return f'<ConservedPosition {self.id}: {self.residue}{self.position}>'

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'position': self.position,
            'residue': self.residue,
            'conservation': float(self.conservation_pct) if self.conservation_pct else None
        }


class Visualization(db.Model):
    """Generated SVG visualization"""
    __tablename__ = 'visualizations'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, unique=True)
    svg_content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    project = db.relationship('Project', back_populates='visualization')

    def __repr__(self):
        return f'<Visualization {self.id} for Project {self.project_id}>'
