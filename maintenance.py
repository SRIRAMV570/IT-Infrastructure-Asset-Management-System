"""Maintenance scheduling and immutable service-history workflows for ITAMS."""
import re
import sqlite3
from datetime import date

from flask import abort, flash, g, redirect, render_template, request, url_for


MAINTENANCE_PRIORITIES = ("low", "medium", "high", "critical")
MAINTENANCE_STATUSES = ("scheduled", "in_progress", "completed")

MAINTENANCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS maintenance_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
    title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 3 AND 120),
    due_date TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'in_progress', 'completed')),
    assigned_to TEXT NOT NULL CHECK (length(trim(assigned_to)) BETWEEN 2 AND 120),
    notes TEXT NOT NULL DEFAULT '',
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS maintenance_due_status
    ON maintenance_schedules(status, due_date, id);
CREATE INDEX IF NOT EXISTS maintenance_asset_history
    ON maintenance_schedules(asset_id, due_date DESC, id DESC);

CREATE TABLE IF NOT EXISTS maintenance_service_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
    maintenance_id INTEGER NOT NULL UNIQUE
        REFERENCES maintenance_schedules(id) ON DELETE RESTRICT,
    service_date TEXT NOT NULL,
    performed_by TEXT NOT NULL CHECK (length(trim(performed_by)) BETWEEN 2 AND 120),
    notes TEXT NOT NULL CHECK (length(trim(notes)) BETWEEN 3 AND 2000),
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS maintenance_service_asset_history
    ON maintenance_service_history(asset_id, service_date DESC, id DESC);

CREATE TRIGGER IF NOT EXISTS maintenance_service_history_no_update
BEFORE UPDATE ON maintenance_service_history
BEGIN
    SELECT RAISE(ABORT, 'maintenance service history is immutable');
END;

CREATE TRIGGER IF NOT EXISTS maintenance_service_history_no_delete
BEFORE DELETE ON maintenance_service_history
BEGIN
    SELECT RAISE(ABORT, 'maintenance service history is immutable');
END;
"""


def _valid_iso_date(value):
    """Return whether value is a real YYYY-MM-DD calendar date."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _maintenance_assets(get_db):
    return get_db().execute(
        """
        SELECT id, asset_tag, name
        FROM assets
        WHERE status <> 'retired'
        ORDER BY name COLLATE NOCASE, asset_tag COLLATE NOCASE
        """
    ).fetchall()


def register_maintenance(app, get_db, get_asset_or_404, roles_required, record_audit_event):
    """Install the maintenance schema and register authenticated routes."""
    connection = sqlite3.connect(app.config["DATABASE"])
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(MAINTENANCE_SCHEMA)
    finally:
        connection.close()

    manager_required = roles_required("admin", "asset_manager")

    @app.get("/maintenance")
    def maintenance_list():
        status_filter = request.args.get("status", "").strip()
        if status_filter not in MAINTENANCE_STATUSES:
            status_filter = ""

        raw_asset_id = request.args.get("asset_id", "").strip()
        asset_id_filter = None
        if raw_asset_id:
            try:
                candidate = int(raw_asset_id)
                if candidate > 0:
                    asset_id_filter = candidate
            except ValueError:
                pass

        query = """
            SELECT
                m.id, m.asset_id, m.title, m.due_date, m.priority, m.status,
                m.assigned_to, m.notes, m.created_at, m.completed_at,
                a.asset_tag, a.name AS asset_name,
                CASE
                    WHEN m.status = 'completed' THEN 'completed'
                    WHEN m.due_date < date('now') THEN 'overdue'
                    WHEN m.due_date = date('now') THEN 'due today'
                    ELSE 'upcoming'
                END AS due_state
            FROM maintenance_schedules AS m
            JOIN assets AS a ON a.id = m.asset_id
            WHERE 1 = 1
        """
        parameters = []
        if status_filter:
            query += " AND m.status = ?"
            parameters.append(status_filter)
        if asset_id_filter is not None:
            query += " AND m.asset_id = ?"
            parameters.append(asset_id_filter)
        query += """
            ORDER BY
                CASE
                    WHEN m.status <> 'completed' AND m.due_date < date('now') THEN 0
                    WHEN m.status <> 'completed' AND m.due_date = date('now') THEN 1
                    WHEN m.status = 'completed' THEN 3
                    ELSE 2
                END,
                m.due_date ASC,
                m.id DESC
        """
        schedules = get_db().execute(query, parameters).fetchall()

        history_query = """
            SELECT
                h.id, h.asset_id, h.maintenance_id, h.service_date,
                h.performed_by, h.notes, h.created_at,
                a.asset_tag, a.name AS asset_name,
                m.title AS maintenance_title
            FROM maintenance_service_history AS h
            JOIN assets AS a ON a.id = h.asset_id
            JOIN maintenance_schedules AS m ON m.id = h.maintenance_id
            WHERE 1 = 1
        """
        history_parameters = []
        if asset_id_filter is not None:
            history_query += " AND h.asset_id = ?"
            history_parameters.append(asset_id_filter)
        history_query += " ORDER BY h.service_date DESC, h.id DESC"
        service_history = get_db().execute(history_query, history_parameters).fetchall()

        return render_template(
            "maintenance.html",
            schedules=schedules,
            service_history=service_history,
            status_filter=status_filter,
            asset_id_filter=asset_id_filter,
        )

    @app.route("/maintenance/new", methods=("GET", "POST"))
    @manager_required
    def maintenance_create():
        assets = _maintenance_assets(get_db)
        values = {
            "asset_id": request.form.get("asset_id", "").strip(),
            "title": request.form.get("title", "").strip(),
            "due_date": request.form.get("due_date", "").strip(),
            "priority": request.form.get("priority", "medium").strip(),
            "assigned_to": request.form.get("assigned_to", "").strip(),
            "notes": request.form.get("notes", "").strip(),
        }

        if request.method == "POST":
            field_errors = {}
            try:
                asset_id = int(values["asset_id"])
            except (TypeError, ValueError):
                asset_id = None
            asset = None
            if asset_id is not None and asset_id > 0:
                asset = get_db().execute(
                    "SELECT id, status FROM assets WHERE id = ?", (asset_id,)
                ).fetchone()
            if asset is None:
                field_errors["asset_id"] = "Choose an existing asset."
            elif asset["status"] == "retired":
                field_errors["asset_id"] = "Retired assets cannot be scheduled for maintenance."

            if not 3 <= len(values["title"]) <= 120:
                field_errors["title"] = "Enter a maintenance title between 3 and 120 characters."
            if not _valid_iso_date(values["due_date"]):
                field_errors["due_date"] = "Enter a valid due date."
            if values["priority"] not in MAINTENANCE_PRIORITIES:
                field_errors["priority"] = "Choose a valid priority."
            if not 2 <= len(values["assigned_to"]) <= 120:
                field_errors["assigned_to"] = "Enter a responsible team or technician."
            if len(values["notes"]) > 1000:
                field_errors["notes"] = "Notes must be 1,000 characters or fewer."

            if field_errors:
                flash("Correct the highlighted maintenance details and try again.", "error")
                return render_template(
                    "maintenance_form.html",
                    assets=assets,
                    values=values,
                    field_errors=field_errors,
                    priorities=MAINTENANCE_PRIORITIES,
                ), 400

            db = get_db()
            cursor = db.execute(
                """
                INSERT INTO maintenance_schedules
                    (asset_id, title, due_date, priority, assigned_to, notes, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    values["title"],
                    values["due_date"],
                    values["priority"],
                    values["assigned_to"],
                    values["notes"],
                    g.user["id"],
                ),
            )
            record_audit_event(
                db,
                "maintenance.scheduled",
                "asset",
                asset_id,
                {
                    "maintenance_id": cursor.lastrowid,
                    "title": values["title"],
                    "due_date": values["due_date"],
                    "priority": values["priority"],
                    "assigned_to": values["assigned_to"],
                },
            )
            db.commit()
            flash("Maintenance scheduled.", "success")
            return redirect(url_for("maintenance_list", asset_id=asset_id))

        return render_template(
            "maintenance_form.html",
            assets=assets,
            values=values,
            field_errors={},
            priorities=MAINTENANCE_PRIORITIES,
        )

    @app.post("/maintenance/<int:maintenance_id>/start")
    @manager_required
    def maintenance_start(maintenance_id):
        schedule = get_db().execute(
            "SELECT id, asset_id, status, title FROM maintenance_schedules WHERE id = ?",
            (maintenance_id,),
        ).fetchone()
        if schedule is None:
            abort(404)
        if schedule["status"] != "scheduled":
            abort(409, description="Only scheduled maintenance can be started.")

        db = get_db()
        updated = db.execute(
            """
            UPDATE maintenance_schedules
            SET status = 'in_progress'
            WHERE id = ? AND status = 'scheduled'
            """,
            (maintenance_id,),
        )
        if updated.rowcount != 1:
            db.rollback()
            abort(409, description="The maintenance status changed; refresh and try again.")
        record_audit_event(
            db,
            "maintenance.started",
            "asset",
            schedule["asset_id"],
            {"maintenance_id": maintenance_id, "title": schedule["title"]},
        )
        db.commit()
        flash("Maintenance marked as in progress.", "success")
        return redirect(url_for("maintenance_list", asset_id=schedule["asset_id"]))

    @app.route("/maintenance/<int:maintenance_id>/complete", methods=("GET", "POST"))
    @manager_required
    def maintenance_complete(maintenance_id):
        schedule = get_db().execute(
            """
            SELECT m.*, a.asset_tag, a.name AS asset_name
            FROM maintenance_schedules AS m
            JOIN assets AS a ON a.id = m.asset_id
            WHERE m.id = ?
            """,
            (maintenance_id,),
        ).fetchone()
        if schedule is None:
            abort(404)
        if schedule["status"] == "completed":
            abort(409, description="This maintenance record is already completed.")

        values = {
            "service_date": request.form.get("service_date", date.today().isoformat()).strip(),
            "performed_by": request.form.get("performed_by", "").strip(),
            "notes": request.form.get("notes", "").strip(),
        }

        if request.method == "POST":
            field_errors = {}
            if not _valid_iso_date(values["service_date"]):
                field_errors["service_date"] = "Enter a valid service date."
            elif date.fromisoformat(values["service_date"]) > date.today():
                field_errors["service_date"] = "Service date cannot be in the future."
            if not 2 <= len(values["performed_by"]) <= 120:
                field_errors["performed_by"] = "Enter the technician or service provider."
            if not 3 <= len(values["notes"]) <= 2000:
                field_errors["notes"] = "Enter service notes (3 to 2,000 characters)."

            if field_errors:
                flash("Correct the service details and try again.", "error")
                return render_template(
                    "maintenance_complete.html",
                    schedule=schedule,
                    values=values,
                    field_errors=field_errors,
                ), 400

            db = get_db()
            updated = db.execute(
                """
                UPDATE maintenance_schedules
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status IN ('scheduled', 'in_progress')
                """,
                (maintenance_id,),
            )
            if updated.rowcount != 1:
                db.rollback()
                abort(409, description="The maintenance status changed; refresh and try again.")

            try:
                db.execute(
                    """
                    INSERT INTO maintenance_service_history
                        (asset_id, maintenance_id, service_date, performed_by, notes, created_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        schedule["asset_id"],
                        maintenance_id,
                        values["service_date"],
                        values["performed_by"],
                        values["notes"],
                        g.user["id"],
                    ),
                )
            except sqlite3.IntegrityError:
                db.rollback()
                abort(409, description="Service history already exists for this maintenance record.")

            record_audit_event(
                db,
                "maintenance.completed",
                "asset",
                schedule["asset_id"],
                {
                    "maintenance_id": maintenance_id,
                    "service_date": values["service_date"],
                    "performed_by": values["performed_by"],
                },
            )
            db.commit()
            flash("Maintenance completed and service history recorded.", "success")
            return redirect(url_for("maintenance_list", asset_id=schedule["asset_id"]))

        return render_template(
            "maintenance_complete.html",
            schedule=schedule,
            values=values,
            field_errors={},
        )
