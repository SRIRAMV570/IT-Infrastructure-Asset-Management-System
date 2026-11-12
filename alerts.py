"""S2-03 alert generation and lifecycle management for ITAMS."""
import sqlite3
from datetime import date

import click
from flask import abort, flash, g, redirect, render_template, request, url_for


ALERT_MANAGER_ROLES = ("admin", "asset_manager")
ALERT_STATUSES = ("open", "acknowledged", "assigned", "resolved")
ALERT_TYPES = (
    "license_expiry",
    "warranty_expiry",
    "maintenance_overdue",
    "incomplete_record",
)
ASSET_COMPLETENESS_FIELDS = frozenset(
    {"manufacturer", "model", "serial_number", "location", "purchase_date"}
)

ALERT_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key TEXT NOT NULL,
    alert_type TEXT NOT NULL CHECK (
        alert_type IN (
            'license_expiry',
            'warranty_expiry',
            'maintenance_overdue',
            'incomplete_record'
        )
    ),
    source_type TEXT NOT NULL CHECK (
        source_type IN ('license', 'warranty', 'maintenance', 'asset')
    ),
    source_id INTEGER NOT NULL,
    asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (
        status IN ('open', 'acknowledged', 'assigned', 'resolved')
    ),
    assigned_to_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    assigned_username TEXT,
    resolution_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS alerts_one_active_dedupe
    ON alerts(dedupe_key) WHERE status <> 'resolved';
CREATE INDEX IF NOT EXISTS alerts_status_severity
    ON alerts(status, severity, due_date, id DESC);
CREATE INDEX IF NOT EXISTS alerts_asset
    ON alerts(asset_id, id DESC);
CREATE INDEX IF NOT EXISTS alerts_source
    ON alerts(source_type, source_id, alert_type);

CREATE TABLE IF NOT EXISTS alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE RESTRICT,
    actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    actor_username TEXT NOT NULL,
    event_type TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    from_assigned_username TEXT,
    to_assigned_username TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS alert_history_alert
    ON alert_history(alert_id, id DESC);

CREATE TRIGGER IF NOT EXISTS alert_history_no_update
BEFORE UPDATE ON alert_history
BEGIN
    SELECT RAISE(ABORT, 'alert history is immutable');
END;

CREATE TRIGGER IF NOT EXISTS alert_history_no_delete
BEFORE DELETE ON alert_history
BEGIN
    SELECT RAISE(ABORT, 'alert history is immutable');
END;
"""


def _table_exists(db, table_name):
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone() is not None


def _parse_date(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _config_days(config, key, default):
    try:
        value = int(config.get(key, default))
    except (TypeError, ValueError):
        return default
    return max(0, value)


def _record_history(
    db,
    alert_id,
    actor_id,
    actor_username,
    event_type,
    from_status=None,
    to_status=None,
    from_assigned_username=None,
    to_assigned_username=None,
    notes="",
):
    db.execute(
        """INSERT INTO alert_history
           (alert_id, actor_id, actor_username, event_type, from_status,
            to_status, from_assigned_username, to_assigned_username, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            alert_id,
            actor_id,
            actor_username,
            event_type,
            from_status,
            to_status,
            from_assigned_username,
            to_assigned_username,
            notes,
        ),
    )


def _severity_for_expiry(days_until_expiry):
    if days_until_expiry < 0:
        return "critical"
    if days_until_expiry <= 7:
        return "high"
    return "medium"


def _enqueue_alert(
    db,
    *,
    dedupe_key,
    alert_type,
    source_type,
    source_id,
    asset_id,
    title,
    message,
    severity,
    due_date,
    actor_id,
    actor_username,
):
    """Create an alert once while active; refresh its text without duplicating it."""
    existing = db.execute(
        """SELECT id, status, message, severity, assigned_username
           FROM alerts WHERE dedupe_key=? AND status <> 'resolved'""",
        (dedupe_key,),
    ).fetchone()
    if existing:
        if existing["message"] != message or existing["severity"] != severity:
            db.execute(
                """UPDATE alerts SET message=?, severity=?,
                   updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (message, severity, existing["id"]),
            )
            _record_history(
                db,
                existing["id"],
                actor_id,
                actor_username,
                "refreshed",
                from_status=existing["status"],
                to_status=existing["status"],
                from_assigned_username=existing["assigned_username"],
                to_assigned_username=existing["assigned_username"],
                notes="Alert condition was re-evaluated.",
            )
        return None

    try:
        cursor = db.execute(
            """INSERT INTO alerts
               (dedupe_key, alert_type, source_type, source_id, asset_id,
                title, message, severity, due_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                dedupe_key,
                alert_type,
                source_type,
                source_id,
                asset_id,
                title,
                message,
                severity,
                due_date,
            ),
        )
    except sqlite3.IntegrityError:
        # Another generator may have inserted the same active alert concurrently.
        return None

    alert_id = cursor.lastrowid
    _record_history(
        db,
        alert_id,
        actor_id,
        actor_username,
        "generated",
        from_status=None,
        to_status="open",
        notes="Alert generated from a configured rule.",
    )
    return {
        "id": alert_id,
        "alert_type": alert_type,
        "source_type": source_type,
        "source_id": source_id,
    }


def generate_alerts(db, config, today=None, actor_id=None, actor_username="system"):
    """Create alerts from available source tables using configured date thresholds.

    S2-01 and S2-02 source tables are optional until their PRs are merged into main.
    """
    today = today or date.today()
    created = []
    duplicates = 0
    skipped_sources = []

    license_days = _config_days(config, "ALERT_LICENSE_EXPIRY_DAYS", 30)
    warranty_days = _config_days(config, "ALERT_WARRANTY_EXPIRY_DAYS", 30)
    maintenance_days = max(
        1, _config_days(config, "ALERT_MAINTENANCE_OVERDUE_DAYS", 1)
    )
    maintenance_high_days = max(
        1, _config_days(config, "ALERT_MAINTENANCE_HIGH_DAYS", 7)
    )
    maintenance_critical_days = max(
        maintenance_high_days,
        _config_days(config, "ALERT_MAINTENANCE_CRITICAL_DAYS", 30),
    )

    def queue(**values):
        nonlocal duplicates
        result = _enqueue_alert(
            db,
            actor_id=actor_id,
            actor_username=actor_username,
            **values,
        )
        if result is None:
            duplicates += 1
        else:
            created.append(result)

    if _table_exists(db, "software_licenses"):
        rows = db.execute(
            """SELECT l.id, l.asset_id, l.product_name, l.expiry_date,
                      l.renewal_status, a.asset_tag
               FROM software_licenses AS l
               LEFT JOIN assets AS a ON a.id=l.asset_id"""
        ).fetchall()
        for row in rows:
            expiry = _parse_date(row["expiry_date"])
            if expiry is None:
                continue
            days_left = (expiry - today).days
            if days_left > license_days:
                continue
            context = (
                f" for asset {row['asset_tag']}" if row["asset_tag"] else ""
            )
            if days_left < 0:
                timing = f"expired {abs(days_left)} day(s) ago"
            elif days_left == 0:
                timing = "expires today"
            else:
                timing = f"expires in {days_left} day(s)"
            queue(
                dedupe_key=f"license-expiry:{row['id']}:{row['expiry_date']}",
                alert_type="license_expiry",
                source_type="license",
                source_id=row["id"],
                asset_id=row["asset_id"],
                title=f"Software license expiry: {row['product_name']}",
                message=(
                    f"{row['product_name']}{context} {timing} "
                    f"({row['expiry_date']}); renewal state: {row['renewal_status']}."
                ),
                severity=_severity_for_expiry(days_left),
                due_date=row["expiry_date"],
            )
    else:
        skipped_sources.append("software_licenses")

    if _table_exists(db, "warranties"):
        rows = db.execute(
            """SELECT w.id, w.asset_id, w.provider, w.start_date, w.end_date,
                      a.asset_tag
               FROM warranties AS w
               LEFT JOIN assets AS a ON a.id=w.asset_id"""
        ).fetchall()
        for row in rows:
            start = _parse_date(row["start_date"])
            expiry = _parse_date(row["end_date"])
            if start is None or expiry is None or start > today:
                continue
            days_left = (expiry - today).days
            if days_left > warranty_days:
                continue
            if days_left < 0:
                timing = f"expired {abs(days_left)} day(s) ago"
            elif days_left == 0:
                timing = "expires today"
            else:
                timing = f"expires in {days_left} day(s)"
            asset_context = (
                f" for asset {row['asset_tag']}" if row["asset_tag"] else ""
            )
            queue(
                dedupe_key=f"warranty-expiry:{row['id']}:{row['end_date']}",
                alert_type="warranty_expiry",
                source_type="warranty",
                source_id=row["id"],
                asset_id=row["asset_id"],
                title=f"Warranty expiry: {row['provider']}",
                message=(
                    f"Warranty from {row['provider']}{asset_context} {timing} "
                    f"({row['end_date']})."
                ),
                severity=_severity_for_expiry(days_left),
                due_date=row["end_date"],
            )
    else:
        skipped_sources.append("warranties")

    if _table_exists(db, "maintenance_schedules"):
        rows = db.execute(
            """SELECT m.id, m.asset_id, m.title, m.due_date, m.priority,
                      m.status, m.assigned_to, a.asset_tag
               FROM maintenance_schedules AS m
               LEFT JOIN assets AS a ON a.id=m.asset_id
               WHERE m.status <> 'completed'"""
        ).fetchall()
        for row in rows:
            due = _parse_date(row["due_date"])
            if due is None:
                continue
            days_overdue = (today - due).days
            if days_overdue < maintenance_days:
                continue
            if days_overdue >= maintenance_critical_days:
                severity = "critical"
            elif days_overdue >= maintenance_high_days:
                severity = "high"
            else:
                severity = "medium"
            asset_context = (
                f" for asset {row['asset_tag']}" if row["asset_tag"] else ""
            )
            queue(
                dedupe_key=f"maintenance-overdue:{row['id']}:{row['due_date']}",
                alert_type="maintenance_overdue",
                source_type="maintenance",
                source_id=row["id"],
                asset_id=row["asset_id"],
                title=f"Overdue maintenance: {row['title']}",
                message=(
                    f"{row['title']}{asset_context} was due on {row['due_date']} "
                    f"and is {days_overdue} day(s) overdue. Priority: {row['priority']}; "
                    f"responsible: {row['assigned_to']}."
                ),
                severity=severity,
                due_date=row["due_date"],
            )
    else:
        skipped_sources.append("maintenance_schedules")

    configured_fields = config.get(
        "ALERT_INCOMPLETE_ASSET_FIELDS",
        ("manufacturer", "model", "serial_number", "location", "purchase_date"),
    )
    fields = tuple(
        field
        for field in configured_fields
        if isinstance(field, str) and field in ASSET_COMPLETENESS_FIELDS
    )
    if fields:
        for row in db.execute(
            "SELECT * FROM assets WHERE status <> 'retired'"
        ).fetchall():
            missing = [
                field for field in fields
                if not str(row[field] or "").strip()
            ]
            if not missing:
                continue
            labels = ", ".join(field.replace("_", " ") for field in missing)
            queue(
                dedupe_key=f"asset-incomplete:{row['id']}",
                alert_type="incomplete_record",
                source_type="asset",
                source_id=row["id"],
                asset_id=row["id"],
                title=f"Incomplete asset record: {row['asset_tag']}",
                message=(
                    f"{row['asset_tag']} ({row['name']}) is missing: {labels}."
                ),
                severity="medium",
                due_date=None,
            )

    return {
        "created": created,
        "created_count": len(created),
        "duplicate_count": duplicates,
        "skipped_sources": skipped_sources,
    }


def _get_alert_or_404(db, alert_id):
    alert = db.execute(
        """SELECT a.*, asset.asset_tag, asset.name AS asset_name
           FROM alerts AS a
           LEFT JOIN assets AS asset ON asset.id=a.asset_id
           WHERE a.id=?""",
        (alert_id,),
    ).fetchone()
    if alert is None:
        abort(404)
    return alert


def _assignable_users(db):
    return db.execute(
        """SELECT id, username, role FROM users
           WHERE role <> 'auditor'
           ORDER BY username COLLATE NOCASE"""
    ).fetchall()


def register_alerts(app, get_db, roles_required, record_audit_event):
    """Install alert tables, UI routes and the scheduled-generation CLI command."""
    connection = sqlite3.connect(app.config["DATABASE"])
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(ALERT_SCHEMA)
    finally:
        connection.close()

    manager_required = roles_required(*ALERT_MANAGER_ROLES)

    @app.get("/alerts")
    def alerts_list():
        status_filter = request.args.get("status", "").strip()
        if status_filter not in ALERT_STATUSES:
            status_filter = ""
        type_filter = request.args.get("type", "").strip()
        if type_filter not in ALERT_TYPES:
            type_filter = ""

        query = """
            SELECT a.*, asset.asset_tag, asset.name AS asset_name
            FROM alerts AS a
            LEFT JOIN assets AS asset ON asset.id=a.asset_id
            WHERE 1=1
        """
        parameters = []
        if status_filter:
            query += " AND a.status=?"
            parameters.append(status_filter)
        if type_filter:
            query += " AND a.alert_type=?"
            parameters.append(type_filter)
        query += """
            ORDER BY
                CASE a.severity
                    WHEN 'critical' THEN 0
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    ELSE 3
                END,
                CASE WHEN a.status='resolved' THEN 1 ELSE 0 END,
                a.due_date ASC,
                a.id DESC
        """
        alerts = get_db().execute(query, parameters).fetchall()
        counts = {
            row["status"]: row["count"]
            for row in get_db().execute(
                "SELECT status, COUNT(*) AS count FROM alerts GROUP BY status"
            )
        }
        return render_template(
            "alerts.html",
            alerts=alerts,
            counts={status: counts.get(status, 0) for status in ALERT_STATUSES},
            status_filter=status_filter,
            type_filter=type_filter,
            alert_types=ALERT_TYPES,
        )

    @app.get("/alerts/<int:alert_id>")
    def alert_detail(alert_id):
        db = get_db()
        alert = _get_alert_or_404(db, alert_id)
        history = db.execute(
            """SELECT * FROM alert_history WHERE alert_id=?
               ORDER BY id DESC""",
            (alert_id,),
        ).fetchall()
        return render_template(
            "alert_detail.html",
            alert=alert,
            history=history,
            users=_assignable_users(db),
        )

    @app.post("/alerts/generate")
    @manager_required
    def alerts_generate():
        db = get_db()
        result = generate_alerts(
            db,
            app.config,
            actor_id=g.user["id"],
            actor_username=g.user["username"],
        )
        for item in result["created"]:
            record_audit_event(
                db,
                "alert.generated",
                "alert",
                item["id"],
                {
                    "alert_type": item["alert_type"],
                    "source_type": item["source_type"],
                    "source_id": item["source_id"],
                },
            )
        db.commit()
        flash(
            f"Alert generation completed: {result['created_count']} new alert(s), "
            f"{result['duplicate_count']} existing alert(s) retained.",
            "success",
        )
        if result["skipped_sources"]:
            flash(
                "Some source modules are not installed yet: "
                + ", ".join(result["skipped_sources"])
                + ". Their alerts will be available after those modules are integrated.",
                "warning",
            )
        return redirect(url_for("alerts_list"))

    @app.post("/alerts/<int:alert_id>/acknowledge")
    @manager_required
    def alert_acknowledge(alert_id):
        db = get_db()
        db.execute("BEGIN IMMEDIATE")
        alert = _get_alert_or_404(db, alert_id)
        if alert["status"] not in ("open", "assigned"):
            db.rollback()
            abort(409, description="Only open or assigned alerts can be acknowledged.")
        db.execute(
            """UPDATE alerts SET status='acknowledged',
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (alert_id,),
        )
        _record_history(
            db,
            alert_id,
            g.user["id"],
            g.user["username"],
            "acknowledged",
            from_status=alert["status"],
            to_status="acknowledged",
            from_assigned_username=alert["assigned_username"],
            to_assigned_username=alert["assigned_username"],
        )
        record_audit_event(
            db, "alert.acknowledged", "alert", alert_id,
            {"from_status": alert["status"], "to_status": "acknowledged"},
        )
        db.commit()
        flash("Alert acknowledged.", "success")
        return redirect(url_for("alert_detail", alert_id=alert_id))

    @app.post("/alerts/<int:alert_id>/assign")
    @manager_required
    def alert_assign(alert_id):
        user_value = request.form.get("user_id", "").strip()
        try:
            user_id = int(user_value)
        except (TypeError, ValueError):
            flash("Select a valid user to assign this alert.", "error")
            return redirect(url_for("alert_detail", alert_id=alert_id))
        db = get_db()
        db.execute("BEGIN IMMEDIATE")
        alert = _get_alert_or_404(db, alert_id)
        if alert["status"] == "resolved":
            db.rollback()
            abort(409, description="Resolved alerts cannot be assigned.")
        user = db.execute(
            "SELECT id, username FROM users WHERE id=? AND role <> 'auditor'",
            (user_id,),
        ).fetchone()
        if user is None:
            db.rollback()
            abort(400, description="The selected assignee does not exist or cannot be assigned.")
        prior_assignee = alert["assigned_username"]
        if prior_assignee == user["username"] and alert["status"] == "assigned":
            db.rollback()
            flash("This alert is already assigned to that user.", "info")
            return redirect(url_for("alert_detail", alert_id=alert_id))
        event_type = "reassigned" if prior_assignee else "assigned"
        db.execute(
            """UPDATE alerts SET status='assigned', assigned_to_id=?,
               assigned_username=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (user["id"], user["username"], alert_id),
        )
        _record_history(
            db,
            alert_id,
            g.user["id"],
            g.user["username"],
            event_type,
            from_status=alert["status"],
            to_status="assigned",
            from_assigned_username=prior_assignee,
            to_assigned_username=user["username"],
        )
        record_audit_event(
            db, "alert.assigned", "alert", alert_id,
            {"from_status": alert["status"], "to_status": "assigned"},
        )
        db.commit()
        flash(f"Alert assigned to {user['username']}.", "success")
        return redirect(url_for("alert_detail", alert_id=alert_id))

    @app.post("/alerts/<int:alert_id>/resolve")
    @manager_required
    def alert_resolve(alert_id):
        notes = request.form.get("resolution_notes", "").strip()
        if len(notes) > 500:
            flash("Resolution notes must be 500 characters or fewer.", "error")
            return redirect(url_for("alert_detail", alert_id=alert_id))
        db = get_db()
        db.execute("BEGIN IMMEDIATE")
        alert = _get_alert_or_404(db, alert_id)
        if alert["status"] == "resolved":
            db.rollback()
            abort(409, description="This alert is already resolved.")
        db.execute(
            """UPDATE alerts SET status='resolved', resolution_notes=?,
               resolved_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (notes, alert_id),
        )
        _record_history(
            db,
            alert_id,
            g.user["id"],
            g.user["username"],
            "resolved",
            from_status=alert["status"],
            to_status="resolved",
            from_assigned_username=alert["assigned_username"],
            to_assigned_username=alert["assigned_username"],
            notes=notes,
        )
        record_audit_event(
            db, "alert.resolved", "alert", alert_id,
            {"from_status": alert["status"], "to_status": "resolved"},
        )
        db.commit()
        flash("Alert resolved.", "success")
        return redirect(url_for("alert_detail", alert_id=alert_id))

    @app.cli.command("generate-alerts")
    @click.option(
        "--as-of",
        default=None,
        help="Evaluate alert thresholds against this YYYY-MM-DD date (defaults to today).",
    )
    def generate_alerts_command(as_of):
        """Generate alerts from current license, warranty, maintenance and asset data."""
        evaluation_date = date.today()
        if as_of:
            parsed = _parse_date(as_of)
            if parsed is None:
                raise click.BadParameter("Use a valid YYYY-MM-DD date.")
            evaluation_date = parsed
        with app.app_context():
            db = get_db()
            result = generate_alerts(
                db,
                app.config,
                today=evaluation_date,
                actor_id=None,
                actor_username="system",
            )
            db.commit()
        click.echo(
            f"Created {result['created_count']} alert(s); "
            f"{result['duplicate_count']} existing alert(s) retained."
        )
        if result["skipped_sources"]:
            click.echo(
                "Source tables not available: " + ", ".join(result["skipped_sources"])
            )


__all__ = [
    "ALERT_SCHEMA",
    "generate_alerts",
    "register_alerts",
]
