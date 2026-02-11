# Database Setup Guide

This guide explains how to set up the MySQL database for the Recent Projects feature.

## Prerequisites

### 1. Install MySQL

**macOS** (using Homebrew):
```bash
brew install mysql
brew services start mysql
```

**Ubuntu/Debian**:
```bash
sudo apt update
sudo apt install mysql-server
sudo systemctl start mysql
```

**Windows**:
Download MySQL installer from https://dev.mysql.com/downloads/installer/

### 2. Secure MySQL Installation

```bash
mysql_secure_installation
```

Follow the prompts to set a root password and secure your installation.

## Database Setup

### Step 1: Create MySQL User

Log into MySQL as root:
```bash
mysql -u root -p
```

Create the Alvis database user:
```sql
CREATE USER 'alvis_user'@'localhost' IDENTIFIED BY 'alvis_password';
GRANT ALL PRIVILEGES ON alvis.* TO 'alvis_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

**Note**: Change 'alvis_password' to a secure password!

### Step 2: Configure Environment

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` and update your database credentials:
```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=alvis_user
MYSQL_PASSWORD=your_actual_password_here
MYSQL_DATABASE=alvis
```

### Step 3: Install Python Dependencies

```bash
pip install -r requirements.txt
```

New dependencies added:
- `Flask-SQLAlchemy` - ORM for database
- `PyMySQL` - MySQL driver
- `cryptography` - Required by PyMySQL

### Step 4: Run Database Setup Script

This will create the database and tables:
```bash
python setup_db.py
```

You should see:
```
==================================================
Alvis Database Setup
==================================================

Database Configuration:
  Host: localhost:3306
  User: alvis_user
  Database: alvis

Creating database...
✓ Database 'alvis' created/verified

Creating tables...
✓ All tables created successfully

==================================================
✓ Database setup completed successfully!
==================================================
```

## Database Schema

### Tables Created:

1. **projects** - Analysis sessions
   - `id` - Primary key
   - `name` - Project name
   - `description` - Optional description
   - `created_at` - Creation timestamp
   - `updated_at` - Last update timestamp

2. **alignments** - FASTA files analyzed
   - `id` - Primary key
   - `project_id` - Foreign key to projects
   - `filename` - FASTA filename
   - `num_sequences` - Number of sequences in alignment
   - `sequence_length` - Length of aligned sequences
   - `conservation_threshold` - Threshold used (e.g., 95.0)

3. **conserved_positions** - Conservation analysis results
   - `id` - Primary key
   - `alignment_id` - Foreign key to alignments
   - `position` - Position in sequence
   - `residue` - Amino acid at this position
   - `conservation_pct` - Conservation percentage

4. **visualizations** - Generated SVG visualizations
   - `id` - Primary key
   - `project_id` - Foreign key to projects (unique)
   - `svg_content` - SVG content as text

## Verification

Test the database connection:
```bash
mysql -u alvis_user -p alvis
```

List tables:
```sql
SHOW TABLES;
```

You should see:
```
+---------------------------+
| Tables_in_alvis           |
+---------------------------+
| alignments                |
| conserved_positions       |
| projects                  |
| visualizations            |
+---------------------------+
```

Describe a table:
```sql
DESCRIBE projects;
```

## Troubleshooting

### Connection Refused
- Make sure MySQL is running: `brew services list` (macOS) or `sudo systemctl status mysql` (Linux)
- Check firewall settings

### Access Denied
- Verify username/password in `.env`
- Make sure you granted privileges: `GRANT ALL PRIVILEGES ON alvis.* TO 'alvis_user'@'localhost';`

### Module Not Found
- Install dependencies: `pip install -r requirements.txt`
- Make sure you're in the virtual environment

### Table Already Exists
- Safe to ignore if tables were created previously
- To reset database:
  ```sql
  DROP DATABASE alvis;
  ```
  Then rerun `python setup_db.py`

## Next Steps

Once the database is set up, you can:
1. Run the application: `python app.py`
2. Use the web interface to create projects
3. View recent projects
4. Reload previous analyses

The database will automatically save all analyses for future reference!
