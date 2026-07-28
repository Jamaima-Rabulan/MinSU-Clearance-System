<?php
// Audit log writer.
declare(strict_types=1);

function write_audit(array $entry): void {
    $stmt = db()->prepare(
        'INSERT INTO audit_logs
         (id, actor_id, actor_email, actor_role, action, resource_type, resource_id, status, details, ip_address, user_agent)
         VALUES (?,?,?,?,?,?,?,?,?,?,?)'
    );
    try {
        $stmt->execute([
            uuid_v4(),
            $entry['actor_id']      ?? null,
            $entry['actor_email']   ?? null,
            $entry['actor_role']    ?? null,
            $entry['action'],
            $entry['resource_type'],
            $entry['resource_id']   ?? null,
            $entry['status']        ?? 'success',
            isset($entry['details']) ? json_encode($entry['details'], JSON_UNESCAPED_SLASHES) : null,
            client_ip(),
            user_agent(),
        ]);
    } catch (Throwable $e) {
        error_log('audit write failed: ' . $e->getMessage());
    }
}
