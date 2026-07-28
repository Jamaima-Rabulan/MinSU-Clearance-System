-- MinSU Clearance System - MySQL Schema (Hostinger MariaDB compatible)
-- Run this once in phpMyAdmin (or `mysql < schema.sql`) after creating your database.

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- ============ users ============
CREATE TABLE IF NOT EXISTS users (
    id             CHAR(36)     NOT NULL PRIMARY KEY,
    email          VARCHAR(190) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    full_name      VARCHAR(190) NOT NULL,
    role           ENUM('student','faculty','admin') NOT NULL DEFAULT 'student',
    student_id     VARCHAR(60)  NULL,
    office         VARCHAR(120) NULL,
    course         VARCHAR(120) NULL,
    year_level     VARCHAR(30)  NULL,
    section        VARCHAR(30)  NULL,
    campus         VARCHAR(30)  NULL,
    college        VARCHAR(30)  NULL,
    email_verified TINYINT(1)   NOT NULL DEFAULT 1,
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_users_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============ clearances ============
CREATE TABLE IF NOT EXISTS clearances (
    id             CHAR(36)     NOT NULL PRIMARY KEY,
    student_id     CHAR(36)     NOT NULL,
    student_name   VARCHAR(190) NOT NULL,
    student_email  VARCHAR(190) NOT NULL,
    student_number VARCHAR(60)  NOT NULL,
    course         VARCHAR(120) NOT NULL,
    year_level     VARCHAR(30)  NOT NULL,
    section        VARCHAR(30)  NOT NULL,
    campus         VARCHAR(30)  NULL,
    college        VARCHAR(30)  NULL,
    semester       VARCHAR(30)  NOT NULL,
    academic_year  VARCHAR(20)  NOT NULL,
    overall_status ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    completed_at   DATETIME     NULL,
    INDEX idx_clr_student (student_id),
    INDEX idx_clr_status  (overall_status),
    CONSTRAINT fk_clr_student FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============ clearance_approvals (one row per office per clearance) ============
CREATE TABLE IF NOT EXISTS clearance_approvals (
    id              INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    clearance_id    CHAR(36)     NOT NULL,
    office          VARCHAR(120) NOT NULL,
    status          ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending',
    approved_by     CHAR(36)     NULL,
    approved_by_name VARCHAR(190) NULL,
    approved_at     DATETIME     NULL,
    comments        TEXT         NULL,
    approval_code   VARCHAR(40)  NULL,
    signature_data  LONGTEXT     NULL,
    display_order   TINYINT UNSIGNED NOT NULL DEFAULT 0,
    INDEX idx_appr_clr    (clearance_id),
    INDEX idx_appr_office (office),
    CONSTRAINT fk_appr_clr FOREIGN KEY (clearance_id) REFERENCES clearances(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============ audit_logs ============
CREATE TABLE IF NOT EXISTS audit_logs (
    id            CHAR(36)     NOT NULL PRIMARY KEY,
    ts            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor_id      CHAR(36)     NULL,
    actor_email   VARCHAR(190) NULL,
    actor_role    VARCHAR(30)  NULL,
    action        VARCHAR(80)  NOT NULL,
    resource_type VARCHAR(40)  NOT NULL,
    resource_id   VARCHAR(80)  NULL,
    status        ENUM('success','failure') NOT NULL DEFAULT 'success',
    details       JSON         NULL,
    ip_address    VARCHAR(64)  NULL,
    user_agent    VARCHAR(255) NULL,
    INDEX idx_audit_ts       (ts),
    INDEX idx_audit_action   (action),
    INDEX idx_audit_resource (resource_type, resource_id),
    INDEX idx_audit_actor    (actor_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============ login_attempts (brute force lockout) ============
CREATE TABLE IF NOT EXISTS login_attempts (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    identifier  VARCHAR(255) NOT NULL,   -- format: ip:email
    attempted_at DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_attempts_id (identifier),
    INDEX idx_attempts_ts (attempted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
