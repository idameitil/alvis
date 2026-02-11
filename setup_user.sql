-- Manual MySQL user and database setup
-- Run this as MySQL root user: mysql -u root -p < setup_user.sql

-- Create database
CREATE DATABASE IF NOT EXISTS alvis CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Create user (change password!)
CREATE USER IF NOT EXISTS 'alvis_user'@'localhost' IDENTIFIED BY 'alvis_password';

-- Grant privileges
GRANT ALL PRIVILEGES ON alvis.* TO 'alvis_user'@'localhost';

-- Apply changes
FLUSH PRIVILEGES;

-- Show result
SELECT User, Host FROM mysql.user WHERE User = 'alvis_user';
SHOW DATABASES LIKE 'alvis';
