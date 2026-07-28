<?php
// Local development config example.
// On Hostinger, copy this to `config.php` and edit with your database credentials.
// DO NOT commit real credentials.

return [
    'db' => [
        'host'    => 'localhost',
        'name'    => 'minsu_clearance',
        'user'    => 'root',
        'pass'    => '',
        'charset' => 'utf8mb4',
    ],

    // Auto-seed default admin on first request if missing.
    'admin' => [
        'email'    => 'admin@minsu.edu.ph',
        'password' => 'Admin@MinSU2025',
        'name'     => 'System Administrator',
    ],

    // Session cookie name (change if you host multiple apps under one domain).
    'session_name' => 'MINSU_SID',

    // Password policy (standard: >=8 chars, at least 1 letter + 1 number).
    'password_policy' => [
        'min_length'   => 8,
        'require_letter' => true,
        'require_digit'  => true,
    ],

    // Brute-force lockout.
    'lockout' => [
        'max_attempts'      => 5,
        'window_seconds'    => 15 * 60, // count failures within 15 minutes
        'lock_seconds'      => 15 * 60, // then block for 15 minutes
    ],
];
