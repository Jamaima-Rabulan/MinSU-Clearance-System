<?php
// Small utilities used across all endpoints.

declare(strict_types=1);

const OFFICES = [
    'University Librarian',
    'Guidance Counselor',
    'SAS Director/Coordinator',
    'Student Affairs/Finance',
    'College Dean/Program Chair',
    'Registrar',
];
const CAMPUSES = ['MMC', 'MBC', 'MCC'];
const COLLEGES = ['CAAF', 'CAS', 'CBM', 'CCS', 'CCJE', 'CTE', 'IABE', 'IF'];
const COURSES  = [
    'BSIT','BSIS','BSBio','BSMath','BAPolSci','ABEnglish','BSPsych',
    'BSED','BEED','BPEd','BTLEd','BSNEd',
    'BSBA','BSOA','BSA','BSMA',
    'BSCrim',
    'BSCS','BSEMC','ACT',
    'BSA-Crop Science','BSA-Animal Science','BSF','BSFi',
    'BSEntrep','BSHRM','BSTM','BSHM',
    'BSFisheries','BFT',
    'BSCPE','BSEE','BSCE','BSME',
];
const YEAR_LEVELS = ['1st Year','2nd Year','3rd Year','4th Year'];
const SECTIONS    = ['F1','F2','F3'];

function uuid_v4(): string {
    $data = random_bytes(16);
    $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
    $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
    return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
}

function client_ip(): string {
    $xff = $_SERVER['HTTP_X_FORWARDED_FOR'] ?? '';
    if ($xff !== '') {
        return trim(explode(',', $xff)[0]);
    }
    return $_SERVER['REMOTE_ADDR'] ?? '-';
}

function user_agent(): string {
    return substr($_SERVER['HTTP_USER_AGENT'] ?? '-', 0, 255);
}

function json_body(): array {
    $raw = file_get_contents('php://input');
    if (!$raw) return [];
    $data = json_decode($raw, true);
    return is_array($data) ? $data : [];
}

function json_out($data, int $status = 200): void {
    http_response_code($status);
    echo json_encode($data, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    exit;
}

function json_error(int $status, string $detail): void {
    json_out(['detail' => $detail], $status);
}

function require_method(string ...$methods): void {
    $m = $_SERVER['REQUEST_METHOD'] ?? 'GET';
    if (!in_array($m, $methods, true)) {
        json_error(405, "Method not allowed");
    }
}

function must_string($v, string $field, int $min = 1, int $max = 255): string {
    if (!is_string($v) || strlen(trim($v)) < $min || strlen($v) > $max) {
        json_error(400, "$field is required (min $min, max $max)");
    }
    return trim($v);
}

function must_email($v, string $field = 'email'): string {
    if (!is_string($v) || !filter_var(trim($v), FILTER_VALIDATE_EMAIL)) {
        json_error(400, "A valid $field is required");
    }
    return strtolower(trim($v));
}

function must_in($v, array $allowed, string $field): string {
    if (!is_string($v) || !in_array($v, $allowed, true)) {
        json_error(400, "Invalid value for $field");
    }
    return $v;
}

function optional_string($v, string $field = '', int $max = 255): ?string {
    if ($v === null || $v === '') return null;
    if (!is_string($v) || strlen($v) > $max) {
        if ($field) json_error(400, "Invalid value for $field");
        return null;
    }
    return trim($v);
}

function public_user(array $u): array {
    return [
        'id'             => $u['id'],
        'email'          => $u['email'],
        'full_name'      => $u['full_name'],
        'role'           => $u['role'],
        'student_id'     => $u['student_id']   ?? null,
        'office'         => $u['office']       ?? null,
        'course'         => $u['course']       ?? null,
        'year_level'     => $u['year_level']   ?? null,
        'section'        => $u['section']      ?? null,
        'campus'         => $u['campus']       ?? null,
        'college'        => $u['college']      ?? null,
        'email_verified' => (bool)($u['email_verified'] ?? true),
    ];
}

function generate_approval_code(): string {
    $ts = date('ymd');
    $chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    $rand = '';
    for ($i = 0; $i < 6; $i++) {
        $rand .= $chars[random_int(0, strlen($chars) - 1)];
    }
    return "CLR-$ts-$rand";
}

function validate_password_policy(string $pw): void {
    global $CFG;
    $p = $CFG['password_policy'];
    if (strlen($pw) < $p['min_length']) {
        json_error(400, "Password must be at least {$p['min_length']} characters.");
    }
    if (!empty($p['require_letter']) && !preg_match('/[A-Za-z]/', $pw)) {
        json_error(400, "Password must contain at least one letter.");
    }
    if (!empty($p['require_digit']) && !preg_match('/[0-9]/', $pw)) {
        json_error(400, "Password must contain at least one number.");
    }
    if (strlen($pw) > 128) {
        json_error(400, "Password must be at most 128 characters.");
    }
}

function get_query(string $key, ?string $default = null): ?string {
    if (!isset($_GET[$key])) return $default;
    $v = $_GET[$key];
    return is_string($v) ? $v : $default;
}
