-- Minimal schema for Recent Projects functionality
-- MySQL 5.7+ compatible

CREATE DATABASE IF NOT EXISTS alvis CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE alvis;

-- Projects: Each analysis session
CREATE TABLE projects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_created (created_at DESC)
) ENGINE=InnoDB;

-- Alignments: FASTA files analyzed in a project
CREATE TABLE alignments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    filename VARCHAR(255) NOT NULL,
    num_sequences INT,
    sequence_length INT,
    conservation_threshold DECIMAL(5,2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    INDEX idx_project (project_id)
) ENGINE=InnoDB;

-- Conservation results: Cached analysis data
CREATE TABLE conserved_positions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    alignment_id INT NOT NULL,
    position INT NOT NULL,
    residue CHAR(1) NOT NULL,
    conservation_pct DECIMAL(5,2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (alignment_id) REFERENCES alignments(id) ON DELETE CASCADE,
    INDEX idx_alignment (alignment_id),
    INDEX idx_position (alignment_id, position)
) ENGINE=InnoDB;

-- Visualizations: Store generated SVG
CREATE TABLE visualizations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    svg_content LONGTEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE KEY unique_project (project_id)
) ENGINE=InnoDB;
