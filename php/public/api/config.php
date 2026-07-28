<?php
// Local development config — for /app testing. On Hostinger, replace with real creds.
return [
    'db' => [
        'host'    => getenv('DB_HOST') ?: '127.0.0.1',
        'name'    => getenv('DB_NAME') ?: 'minsu_clearance',
        'user'    => getenv('DB_USER') ?: 'minsu',
        'pass'    => getenv('DB_PASS') ?: 'MinSU2025',
        'charset' => 'utf8mb4',
    ],
    'admin' => [
        'email'    => 'admin@minsu.edu.ph',
        'password' => 'Admin@MinSU2025',
        'name'     => 'System Administrator',
    ],
    'session_name' => 'MINSU_SID',
    'password_policy' => [
        'min_length'     => 8,
        'require_letter' => true,
        'require_digit'  => true,
    ],
    'lockout' => [
        'max_attempts'   => 5,
        'window_seconds' => 15 * 60,
        'lock_seconds'   => 15 * 60,
    ],
];
