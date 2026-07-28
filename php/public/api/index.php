<?php
// MinSU Clearance System — PHP API front controller
// All /api/* URLs land here (via .htaccess) or callers can hit /api/index.php?path=/...

require_once __DIR__ . '/lib/bootstrap.php';

// ---------- Router ----------
// Priority: explicit ?path=... (used when hitting api/index.php directly),
// otherwise strip the /api/ prefix from REQUEST_URI (used with .htaccess pretty URLs).
if (isset($_GET['path']) && $_GET['path'] !== '') {
    $requestUri = '/' . ltrim((string)$_GET['path'], '/');
} else {
    $requestUri = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?? '/';
    $requestUri = preg_replace('#^.*?/api(?=/|$)#', '', $requestUri);
    if ($requestUri === '' || $requestUri === false || $requestUri === null) $requestUri = '/';
}
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';

purge_old_attempts();

// Convenience: strip trailing slash
$path = rtrim($requestUri, '/');
if ($path === '') $path = '/';

// ============ ROOT ============
if ($path === '/' && $method === 'GET') {
    json_out(['message' => 'MinSU Clearance System PHP API', 'version' => '3.0.0-php']);
}

// ============ CONSTANTS ============
if ($path === '/constants' && $method === 'GET') {
    json_out([
        'offices'     => OFFICES,
        'courses'     => COURSES,
        'year_levels' => YEAR_LEVELS,
        'sections'    => SECTIONS,
        'campuses'    => CAMPUSES,
        'colleges'    => COLLEGES,
    ]);
}

// ============ AUTH: REGISTER ============
if ($path === '/auth/register' && $method === 'POST') {
    $b = json_body();
    $email = must_email($b['email'] ?? null);
    $password = must_string($b['password'] ?? null, 'password', 1, 128);
    validate_password_policy($password);
    $fullName = must_string($b['full_name'] ?? null, 'full_name', 2, 190);
    $role = must_in($b['role'] ?? 'student', ['student', 'faculty', 'admin'], 'role');

    // Role-specific validation
    $studentId = $office = $course = $yearLevel = $section = $campus = $college = null;
    if ($role === 'student') {
        $studentId = must_string($b['student_id'] ?? null, 'student_id', 2, 60);
        $course    = must_in($b['course'] ?? '', COURSES, 'course');
        $yearLevel = must_in($b['year_level'] ?? '', YEAR_LEVELS, 'year_level');
        $section   = must_in($b['section'] ?? '', SECTIONS, 'section');
        $campus    = optional_string($b['campus'] ?? null);
        if ($campus !== null && !in_array($campus, CAMPUSES, true)) json_error(400, 'Invalid campus');
        $college   = optional_string($b['college'] ?? null);
        if ($college !== null && !in_array($college, COLLEGES, true)) json_error(400, 'Invalid college');
    } elseif ($role === 'faculty') {
        $office = must_in($b['office'] ?? '', OFFICES, 'office');
    }

    // Uniqueness
    $stmt = db()->prepare('SELECT id FROM users WHERE email = ? LIMIT 1');
    $stmt->execute([$email]);
    if ($stmt->fetch()) {
        write_audit([
            'action' => 'user.register', 'resource_type' => 'user',
            'actor_email' => $email, 'actor_role' => $role,
            'status' => 'failure', 'details' => ['reason' => 'email_already_registered'],
        ]);
        json_error(400, 'Email already registered');
    }

    $id = uuid_v4();
    $hash = password_hash($password, PASSWORD_BCRYPT);
    $ins = db()->prepare(
        'INSERT INTO users
         (id, email, password_hash, full_name, role, student_id, office, course, year_level, section, campus, college, email_verified)
         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)'
    );
    $ins->execute([$id, $email, $hash, $fullName, $role, $studentId, $office, $course, $yearLevel, $section, $campus, $college]);

    write_audit([
        'action' => 'user.register', 'resource_type' => 'user', 'resource_id' => $id,
        'actor_id' => $id, 'actor_email' => $email, 'actor_role' => $role, 'status' => 'success',
        'details' => ['full_name' => $fullName],
    ]);

    // Log the new user in immediately
    session_regenerate_id(true);
    $_SESSION['user_id'] = $id;

    $stmt = db()->prepare('SELECT * FROM users WHERE id = ?');
    $stmt->execute([$id]);
    $u = $stmt->fetch();
    json_out(['success' => true, 'user' => public_user($u), 'message' => 'Registration successful!']);
}

// ============ AUTH: LOGIN ============
if ($path === '/auth/login' && $method === 'POST') {
    $b = json_body();
    $email = must_email($b['email'] ?? null);
    $password = must_string($b['password'] ?? null, 'password', 1, 128);

    // Brute-force check FIRST
    $lock = is_locked_out($email);
    if (!empty($lock['locked'])) {
        write_audit([
            'action' => 'user.login', 'resource_type' => 'user',
            'actor_email' => $email, 'status' => 'failure',
            'details' => ['reason' => 'locked_out', 'seconds_remaining' => $lock['seconds_remaining']],
        ]);
        $mins = (int)ceil($lock['seconds_remaining'] / 60);
        json_error(429, "Too many failed attempts. Try again in ~{$mins} minute(s).");
    }

    $stmt = db()->prepare('SELECT * FROM users WHERE email = ? LIMIT 1');
    $stmt->execute([$email]);
    $u = $stmt->fetch();

    if (!$u) {
        record_failed_login($email);
        write_audit([
            'action' => 'user.login', 'resource_type' => 'user',
            'actor_email' => $email, 'status' => 'failure',
            'details' => ['reason' => 'user_not_found'],
        ]);
        json_error(401, 'Invalid credentials');
    }

    // Support both bcrypt (new) and legacy sha256 (in case old data is imported)
    $ok = false;
    $hash = $u['password_hash'];
    if (strlen($hash) > 3 && $hash[0] === '$' && $hash[1] === '2') {
        $ok = password_verify($password, $hash);
    } else {
        $ok = hash_equals(hash('sha256', $password), $hash);
        if ($ok) {
            // Upgrade to bcrypt
            $upd = db()->prepare('UPDATE users SET password_hash = ? WHERE id = ?');
            $upd->execute([password_hash($password, PASSWORD_BCRYPT), $u['id']]);
        }
    }

    if (!$ok) {
        record_failed_login($email);
        write_audit([
            'action' => 'user.login', 'resource_type' => 'user', 'resource_id' => $u['id'],
            'actor_id' => $u['id'], 'actor_email' => $email, 'actor_role' => $u['role'],
            'status' => 'failure', 'details' => ['reason' => 'invalid_password'],
        ]);
        json_error(401, 'Invalid credentials');
    }

    clear_failed_logins($email);
    session_regenerate_id(true);
    $_SESSION['user_id'] = $u['id'];

    write_audit([
        'action' => 'user.login', 'resource_type' => 'user', 'resource_id' => $u['id'],
        'actor_id' => $u['id'], 'actor_email' => $email, 'actor_role' => $u['role'],
        'status' => 'success',
    ]);

    json_out(['success' => true, 'user' => public_user($u)]);
}

// ============ AUTH: LOGOUT ============
if ($path === '/auth/logout' && $method === 'POST') {
    $u = current_user();
    if ($u) {
        write_audit([
            'action' => 'user.logout', 'resource_type' => 'user', 'resource_id' => $u['id'],
            'actor_id' => $u['id'], 'actor_email' => $u['email'], 'actor_role' => $u['role'],
        ]);
    }
    $_SESSION = [];
    if (ini_get('session.use_cookies')) {
        $params = session_get_cookie_params();
        setcookie(session_name(), '', time() - 42000, $params['path'], $params['domain'] ?? '', $params['secure'], $params['httponly']);
    }
    session_destroy();
    json_out(['success' => true]);
}

// ============ AUTH: ME ============
if ($path === '/auth/me' && $method === 'GET') {
    $u = current_user();
    if (!$u) json_error(401, 'Not authenticated');
    json_out(['user' => public_user($u)]);
}

// ============ CLEARANCE: CREATE ============
if ($path === '/clearances/create' && $method === 'POST') {
    $u = require_role('student');
    $b = json_body();
    $semester = must_in($b['semester'] ?? '', ['1st Semester', '2nd Semester', 'Summer'], 'semester');
    $ay = must_string($b['academic_year'] ?? null, 'academic_year', 4, 20);
    if (!preg_match('/^\d{4}-\d{4}$/', $ay)) json_error(400, 'academic_year must be YYYY-YYYY');

    $id = uuid_v4();
    $pdo = db();
    $pdo->beginTransaction();
    try {
        $ins = $pdo->prepare(
            'INSERT INTO clearances
             (id, student_id, student_name, student_email, student_number, course, year_level, section, campus, college, semester, academic_year, overall_status)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?, "pending")'
        );
        $ins->execute([
            $id, $u['id'], $u['full_name'], $u['email'],
            $u['student_id'] ?? '', $u['course'] ?? '',
            $u['year_level'] ?? '', $u['section'] ?? '',
            $u['campus'] ?? null, $u['college'] ?? null,
            $semester, $ay,
        ]);
        $ap = $pdo->prepare('INSERT INTO clearance_approvals (clearance_id, office, display_order) VALUES (?,?,?)');
        foreach (OFFICES as $i => $off) $ap->execute([$id, $off, $i]);
        $pdo->commit();
    } catch (Throwable $e) {
        $pdo->rollBack();
        error_log('create_clearance: ' . $e->getMessage());
        json_error(500, 'Failed to create clearance');
    }

    write_audit([
        'action' => 'clearance.create', 'resource_type' => 'clearance', 'resource_id' => $id,
        'actor_id' => $u['id'], 'actor_email' => $u['email'], 'actor_role' => $u['role'],
        'details' => ['semester' => $semester, 'academic_year' => $ay],
    ]);
    json_out(['success' => true, 'clearance_id' => $id]);
}

// ---------- helper: hydrate clearance with approvals ----------
function fetch_clearance_full(string $clearanceId): ?array {
    $stmt = db()->prepare('SELECT * FROM clearances WHERE id = ? LIMIT 1');
    $stmt->execute([$clearanceId]);
    $c = $stmt->fetch();
    if (!$c) return null;
    $ap = db()->prepare('SELECT office, status, approved_by, approved_by_name, approved_at, comments, approval_code
                         FROM clearance_approvals WHERE clearance_id = ? ORDER BY display_order');
    $ap->execute([$clearanceId]);
    $c['approvals'] = $ap->fetchAll();
    return $c;
}

// ============ CLEARANCE: LIST ============
if ($path === '/clearances/list' && $method === 'GET') {
    $u = require_login();
    $filters = [];
    $where = [];
    $params = [];

    if ($u['role'] === 'student') {
        $where[] = 'c.student_id = ?';
        $params[] = $u['id'];
    } elseif ($u['role'] === 'faculty') {
        // Clearances with a pending approval for this office
        $where[] = 'EXISTS (SELECT 1 FROM clearance_approvals ca WHERE ca.clearance_id = c.id AND ca.office = ? AND ca.status = "pending")';
        $params[] = $u['office'];
    }

    foreach (['course', 'year_level', 'section', 'campus', 'college'] as $k) {
        $v = get_query($k);
        if ($v) { $where[] = "c.$k = ?"; $params[] = $v; }
    }
    $status = get_query('status');
    if ($status) { $where[] = 'c.overall_status = ?'; $params[] = $status; }

    $sql = 'SELECT c.* FROM clearances c';
    if ($where) $sql .= ' WHERE ' . implode(' AND ', $where);
    $sql .= ' ORDER BY c.created_at DESC LIMIT 1000';
    $stmt = db()->prepare($sql);
    $stmt->execute($params);
    $rows = $stmt->fetchAll();

    // Attach approvals for each
    if ($rows) {
        $ids = array_column($rows, 'id');
        $placeholders = implode(',', array_fill(0, count($ids), '?'));
        $ap = db()->prepare("SELECT * FROM clearance_approvals WHERE clearance_id IN ($placeholders) ORDER BY display_order");
        $ap->execute($ids);
        $grouped = [];
        foreach ($ap->fetchAll() as $a) {
            $grouped[$a['clearance_id']][] = [
                'office' => $a['office'], 'status' => $a['status'],
                'approved_by' => $a['approved_by'], 'approved_by_name' => $a['approved_by_name'],
                'approved_at' => $a['approved_at'], 'comments' => $a['comments'],
                'approval_code' => $a['approval_code'],
            ];
        }
        foreach ($rows as &$r) $r['approvals'] = $grouped[$r['id']] ?? [];
    }

    json_out(['clearances' => $rows]);
}

// ============ CLEARANCE: GET ============
if (preg_match('#^/clearances/([a-f0-9-]{36})$#', $path, $m) && $method === 'GET') {
    $u = require_login();
    $c = fetch_clearance_full($m[1]);
    if (!$c) json_error(404, 'Clearance not found');
    if ($u['role'] === 'student' && $c['student_id'] !== $u['id']) json_error(403, 'Access denied');
    json_out(['clearance' => $c]);
}

// ============ CLEARANCE: PROCESS ============
if (preg_match('#^/clearances/([a-f0-9-]{36})/process$#', $path, $m) && $method === 'POST') {
    $u = require_role('faculty');
    $office = $u['office'];
    if (!$office) json_error(400, 'Faculty must have an assigned office');

    $b = json_body();
    $action = must_in($b['action'] ?? '', ['approve', 'reject'], 'action');
    $comments = optional_string($b['comments'] ?? null, 'comments', 1000);
    // signature_data accepted but not enforced/stored beyond size cap
    $signature = $b['signature_data'] ?? null;
    if ($signature && !is_string($signature)) json_error(400, 'Invalid signature_data');
    if (is_string($signature) && strlen($signature) > 2_000_000) json_error(400, 'signature_data too large');

    $clearanceId = $m[1];
    $c = fetch_clearance_full($clearanceId);
    if (!$c) json_error(404, 'Clearance not found');

    // Registrar gate
    if ($office === 'Registrar') {
        $pending = 0;
        foreach ($c['approvals'] as $a) {
            if ($a['office'] !== 'Registrar' && $a['status'] === 'pending') $pending++;
        }
        if ($pending > 0) {
            json_error(400, "Registrar can only approve after all other offices. $pending office(s) still pending.");
        }
    }

    // Find this office's approval row
    $target = null;
    foreach ($c['approvals'] as $a) if ($a['office'] === $office) { $target = $a; break; }
    if (!$target) json_error(400, 'No approval slot for your office');
    if ($target['status'] !== 'pending') json_error(400, 'This clearance has already been processed by your office');

    $newStatus = $action === 'approve' ? 'approved' : 'rejected';
    $code = generate_approval_code();

    $pdo = db();
    $pdo->beginTransaction();
    try {
        $upd = $pdo->prepare(
            'UPDATE clearance_approvals
             SET status = ?, approved_by = ?, approved_by_name = ?, approved_at = NOW(),
                 comments = ?, approval_code = ?, signature_data = ?
             WHERE clearance_id = ? AND office = ?'
        );
        $upd->execute([$newStatus, $u['id'], $u['full_name'], $comments, $code, $signature, $clearanceId, $office]);

        // Reload approvals to compute overall
        $ap = $pdo->prepare('SELECT status FROM clearance_approvals WHERE clearance_id = ?');
        $ap->execute([$clearanceId]);
        $statuses = array_column($ap->fetchAll(), 'status');

        $overall = 'pending';
        if ($action === 'reject') $overall = 'rejected';
        elseif (count(array_filter($statuses, fn($s) => $s === 'approved')) === count($statuses)) $overall = 'approved';

        $completed = ($overall === 'approved' || $overall === 'rejected') ? date('Y-m-d H:i:s') : null;
        $u2 = $pdo->prepare('UPDATE clearances SET overall_status = ?, completed_at = ? WHERE id = ?');
        $u2->execute([$overall, $completed, $clearanceId]);
        $pdo->commit();
    } catch (Throwable $e) {
        $pdo->rollBack();
        error_log('process_clearance: ' . $e->getMessage());
        json_error(500, 'Failed to process clearance');
    }

    write_audit([
        'action' => "clearance.$action", 'resource_type' => 'clearance', 'resource_id' => $clearanceId,
        'actor_id' => $u['id'], 'actor_email' => $u['email'], 'actor_role' => 'faculty',
        'details' => [
            'office' => $office, 'student_id' => $c['student_id'], 'student_name' => $c['student_name'],
            'overall_status' => $overall, 'comments' => $comments,
        ],
    ]);
    json_out(['success' => true, 'message' => "Clearance {$action}d successfully"]);
}

// ============ CLEARANCE: AUDIT TRAIL ============
if (preg_match('#^/clearances/([a-f0-9-]{36})/audit-trail$#', $path, $m) && $method === 'GET') {
    $u = require_login();
    $c = fetch_clearance_full($m[1]);
    if (!$c) json_error(404, 'Clearance not found');
    if ($u['role'] === 'student' && $c['student_id'] !== $u['id']) json_error(403, 'Access denied');

    $stmt = db()->prepare(
        'SELECT id, ts AS timestamp, actor_id, actor_email, actor_role, action, resource_type,
                resource_id, status, details, ip_address, user_agent
         FROM audit_logs WHERE resource_type = "clearance" AND resource_id = ?
         ORDER BY ts ASC LIMIT 500'
    );
    $stmt->execute([$m[1]]);
    $rows = $stmt->fetchAll();
    foreach ($rows as &$r) if ($r['details']) $r['details'] = json_decode($r['details'], true);
    json_out(['trail' => $rows]);
}

// ============ STATS ============
if ($path === '/stats' && $method === 'GET') {
    $u = require_login();
    $pdo = db();
    if ($u['role'] === 'student') {
        $total    = $pdo->prepare('SELECT COUNT(*) FROM clearances WHERE student_id = ?');            $total->execute([$u['id']]);
        $pending  = $pdo->prepare('SELECT COUNT(*) FROM clearances WHERE student_id = ? AND overall_status = "pending"');  $pending->execute([$u['id']]);
        $approved = $pdo->prepare('SELECT COUNT(*) FROM clearances WHERE student_id = ? AND overall_status = "approved"'); $approved->execute([$u['id']]);
        $rejected = $pdo->prepare('SELECT COUNT(*) FROM clearances WHERE student_id = ? AND overall_status = "rejected"'); $rejected->execute([$u['id']]);
        json_out(['total' => (int)$total->fetchColumn(), 'pending' => (int)$pending->fetchColumn(),
                  'approved' => (int)$approved->fetchColumn(), 'rejected' => (int)$rejected->fetchColumn()]);
    } elseif ($u['role'] === 'faculty') {
        $office = $u['office'];
        $total    = $pdo->prepare('SELECT COUNT(DISTINCT clearance_id) FROM clearance_approvals WHERE office = ?'); $total->execute([$office]);
        $pending  = $pdo->prepare('SELECT COUNT(*) FROM clearance_approvals WHERE office = ? AND status = "pending"');  $pending->execute([$office]);
        $approved = $pdo->prepare('SELECT COUNT(*) FROM clearance_approvals WHERE office = ? AND status = "approved"'); $approved->execute([$office]);
        $rejected = $pdo->prepare('SELECT COUNT(*) FROM clearance_approvals WHERE office = ? AND status = "rejected"'); $rejected->execute([$office]);
        json_out(['total' => (int)$total->fetchColumn(), 'pending' => (int)$pending->fetchColumn(),
                  'approved' => (int)$approved->fetchColumn(), 'rejected' => (int)$rejected->fetchColumn()]);
    } else {
        $t = (int)$pdo->query('SELECT COUNT(*) FROM clearances')->fetchColumn();
        $p = (int)$pdo->query('SELECT COUNT(*) FROM clearances WHERE overall_status = "pending"')->fetchColumn();
        $a = (int)$pdo->query('SELECT COUNT(*) FROM clearances WHERE overall_status = "approved"')->fetchColumn();
        $r = (int)$pdo->query('SELECT COUNT(*) FROM clearances WHERE overall_status = "rejected"')->fetchColumn();
        json_out(['total' => $t, 'pending' => $p, 'approved' => $a, 'rejected' => $r]);
    }
}

// ============ ADMIN: USERS ============
if ($path === '/admin/users' && $method === 'GET') {
    require_role('admin');
    $stmt = db()->query(
        'SELECT id, email, full_name, role, student_id, office, course, year_level, section, campus, college, email_verified, created_at
         FROM users ORDER BY created_at DESC LIMIT 1000'
    );
    json_out(['users' => $stmt->fetchAll()]);
}

// ============ ADMIN: DELETE USER ============
if (preg_match('#^/admin/users/([a-f0-9-]{36})$#', $path, $m) && $method === 'DELETE') {
    $admin = require_role('admin');
    $target = null;
    $stmt = db()->prepare('SELECT id, email, role FROM users WHERE id = ?');
    $stmt->execute([$m[1]]);
    $target = $stmt->fetch();
    $del = db()->prepare('DELETE FROM users WHERE id = ?');
    $del->execute([$m[1]]);
    if ($del->rowCount() === 0) json_error(404, 'User not found');

    write_audit([
        'action' => 'admin.delete_user', 'resource_type' => 'user', 'resource_id' => $m[1],
        'actor_id' => $admin['id'], 'actor_email' => $admin['email'], 'actor_role' => 'admin',
        'details' => ['target_email' => $target['email'] ?? null, 'target_role' => $target['role'] ?? null],
    ]);
    json_out(['success' => true, 'message' => 'User deleted successfully']);
}

// ============ ADMIN: AUDIT LOGS ============
if ($path === '/admin/audit-logs' && $method === 'GET') {
    require_role('admin');
    $q = ['1=1']; $p = [];
    if ($a = get_query('action'))        { $q[] = 'action = ?';        $p[] = $a; }
    if ($r = get_query('resource_type')) { $q[] = 'resource_type = ?'; $p[] = $r; }
    if ($s = get_query('status'))        { $q[] = 'status = ?';        $p[] = $s; }
    if ($e = get_query('actor_email'))   { $q[] = 'actor_email LIKE ?'; $p[] = '%' . $e . '%'; }

    $limit = (int)(get_query('limit', '200'));
    $limit = max(1, min($limit, 1000));
    $sql = 'SELECT id, ts AS timestamp, actor_id, actor_email, actor_role, action, resource_type, resource_id, status, details, ip_address, user_agent
            FROM audit_logs WHERE ' . implode(' AND ', $q) . " ORDER BY ts DESC LIMIT $limit";
    $stmt = db()->prepare($sql);
    $stmt->execute($p);
    $rows = $stmt->fetchAll();
    foreach ($rows as &$row) if ($row['details']) $row['details'] = json_decode($row['details'], true);
    json_out(['logs' => $rows, 'count' => count($rows)]);
}

// ============ ADMIN: AUDIT LOG ACTIONS (distinct values for filters) ============
if ($path === '/admin/audit-logs/actions' && $method === 'GET') {
    require_role('admin');
    $actions = array_column(db()->query('SELECT DISTINCT action FROM audit_logs ORDER BY action')->fetchAll(), 'action');
    $resources = array_column(db()->query('SELECT DISTINCT resource_type FROM audit_logs ORDER BY resource_type')->fetchAll(), 'resource_type');
    json_out(['actions' => $actions, 'resource_types' => $resources]);
}

// ---------- 404 fallback ----------
json_error(404, "Route not found: $method $path");
