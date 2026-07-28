<?php
// Shared bootstrap for every /api endpoint.
// Handles: CORS, JSON headers, session, PDO connection, DB seed, JSON body parsing.

declare(strict_types=1);

// Suppress error output leaking to clients; log server-side.
ini_set('display_errors', '0');
ini_set('log_errors', '1');
error_reporting(E_ALL);

$CFG = require __DIR__ . '/../config.php';

// ---------- CORS (relaxed same-origin friendly) ----------
$origin = $_SERVER['HTTP_ORIGIN'] ?? '';
if ($origin !== '') {
    header('Access-Control-Allow-Origin: ' . $origin);
    header('Vary: Origin');
    header('Access-Control-Allow-Credentials: true');
} else {
    header('Access-Control-Allow-Origin: *');
}
header('Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, X-Requested-With');
header('Content-Type: application/json; charset=utf-8');

if (($_SERVER['REQUEST_METHOD'] ?? '') === 'OPTIONS') {
    http_response_code(204);
    exit;
}

// ---------- Sessions ----------
session_name($CFG['session_name']);
session_set_cookie_params([
    'lifetime' => 0,
    'path'     => '/',
    'httponly' => true,
    'secure'   => (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off'),
    'samesite' => 'Lax',
]);
if (session_status() !== PHP_SESSION_ACTIVE) {
    session_start();
}

// ---------- helpers used everywhere (load BEFORE db so json_error is available) ----------
require_once __DIR__ . '/util.php';
require_once __DIR__ . '/auth.php';
require_once __DIR__ . '/audit.php';

// ---------- DB (PDO) ----------
function db(): PDO {
    static $pdo = null;
    if ($pdo instanceof PDO) return $pdo;
    global $CFG;
    $dsn = sprintf(
        'mysql:host=%s;dbname=%s;charset=%s',
        $CFG['db']['host'], $CFG['db']['name'], $CFG['db']['charset']
    );
    try {
        $pdo = new PDO($dsn, $CFG['db']['user'], $CFG['db']['pass'], [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES   => false,
        ]);
    } catch (Throwable $e) {
        error_log('DB connect failed: ' . $e->getMessage());
        json_error(500, 'Database connection failed. Check /api/config.php.');
    }
    return $pdo;
}

// ---------- One-time admin seed (idempotent, cheap) ----------
function seed_admin_if_needed(): void {
    global $CFG;
    $pdo = db();
    $exists = $pdo->prepare('SELECT id, password_hash FROM users WHERE email = ? LIMIT 1');
    $exists->execute([strtolower($CFG['admin']['email'])]);
    $row = $exists->fetch();
    if (!$row) {
        $stmt = $pdo->prepare('INSERT INTO users (id, email, password_hash, full_name, role, email_verified) VALUES (?,?,?,?,?,1)');
        $stmt->execute([
            uuid_v4(),
            strtolower($CFG['admin']['email']),
            password_hash($CFG['admin']['password'], PASSWORD_BCRYPT),
            $CFG['admin']['name'],
            'admin',
        ]);
    } else if (!password_verify($CFG['admin']['password'], $row['password_hash'])) {
        // Keep env-admin password in sync
        $upd = $pdo->prepare('UPDATE users SET password_hash = ? WHERE id = ?');
        $upd->execute([password_hash($CFG['admin']['password'], PASSWORD_BCRYPT), $row['id']]);
    }
}
seed_admin_if_needed();
