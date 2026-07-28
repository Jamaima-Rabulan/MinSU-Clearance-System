<?php
// Session-backed auth helpers + brute-force lockout.
declare(strict_types=1);

function current_user(): ?array {
    $uid = $_SESSION['user_id'] ?? null;
    if (!$uid) return null;
    $stmt = db()->prepare('SELECT * FROM users WHERE id = ? LIMIT 1');
    $stmt->execute([$uid]);
    $u = $stmt->fetch();
    return $u ?: null;
}

function require_login(): array {
    $u = current_user();
    if (!$u) json_error(401, 'Not authenticated');
    return $u;
}

function require_role(string ...$roles): array {
    $u = require_login();
    if (!in_array($u['role'], $roles, true)) {
        json_error(403, 'Access denied for this role');
    }
    return $u;
}

function login_identifier(string $email): string {
    return client_ip() . ':' . strtolower($email);
}

function is_locked_out(string $email): array {
    global $CFG;
    $ident = login_identifier($email);
    $window = (int)$CFG['lockout']['window_seconds'];
    $max    = (int)$CFG['lockout']['max_attempts'];
    $lock   = (int)$CFG['lockout']['lock_seconds'];

    // Count attempts in the window
    $stmt = db()->prepare(
        'SELECT COUNT(*) AS c, MAX(attempted_at) AS last_at
         FROM login_attempts
         WHERE identifier = ? AND attempted_at >= (NOW() - INTERVAL ? SECOND)'
    );
    $stmt->execute([$ident, $window]);
    $row = $stmt->fetch();
    $count = (int)($row['c'] ?? 0);
    if ($count < $max) {
        return ['locked' => false, 'attempts' => $count, 'remaining' => $max - $count];
    }
    // Locked: compute seconds until earliest expiry from last_at
    $last = strtotime((string)$row['last_at']);
    $unlockAt = $last + $lock;
    $secs = max(0, $unlockAt - time());
    if ($secs <= 0) return ['locked' => false, 'attempts' => 0, 'remaining' => $max];
    return ['locked' => true, 'seconds_remaining' => $secs];
}

function record_failed_login(string $email): void {
    $stmt = db()->prepare('INSERT INTO login_attempts (identifier) VALUES (?)');
    $stmt->execute([login_identifier($email)]);
}

function clear_failed_logins(string $email): void {
    $stmt = db()->prepare('DELETE FROM login_attempts WHERE identifier = ?');
    $stmt->execute([login_identifier($email)]);
}

function purge_old_attempts(): void {
    global $CFG;
    // Non-critical housekeeping — remove attempts older than 24h
    try {
        db()->exec('DELETE FROM login_attempts WHERE attempted_at < (NOW() - INTERVAL 1 DAY)');
    } catch (Throwable $e) { /* best effort */ }
}
