import os
import secrets
import sqlite3
from pathlib import Path

from flask import (
    Flask,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)


ASSET_STATUSES = ("available", "allocated", "maintenance", "retired")

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_tag TEXT NOT NULL COLLATE NOCASE UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    manufacturer TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    serial_number TEXT COLLATE NOCASE UNIQUE,
    status TEXT NOT NULL DEFAULT 'available'
        CHECK (status IN ('available', 'allocated', 'maintenance', 'retired')),
    location TEXT NOT NULL DEFAULT '',
    purchase_date TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL REFERENCES assets(id),
    assignee TEXT NOT NULL,
    allocated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    returned_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_allocation_per_asset
    ON allocations(asset_id) WHERE returned_at IS NULL;
"""


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "itams.sqlite3"),
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32),
    )
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(app.config["DATABASE"])
    try:
        connection.executescript(SCHEMA)
    finally:
        connection.close()

    @app.teardown_appcontext
    def close_db(_error=None):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    @app.get("/")
    def index():
        db = get_db()
        counts = {
            row["status"]: row["count"]
            for row in db.execute(
                "SELECT status, COUNT(*) AS count FROM assets GROUP BY status"
            )
        }
        return render_template(
            "index.html",
            counts={status: counts.get(status, 0) for status in ASSET_STATUSES},
            total=sum(counts.values()),
        )

    @app.get("/assets")
    def asset_list():
        search = request.args.get("q", "").strip()
        status = request.args.get("status", "").strip()
        if status not in ASSET_STATUSES:
            status = ""

        query = "SELECT * FROM assets WHERE 1 = 1"
        parameters = []
        if search:
            wildcard = f"%{search}%"
            query += (
                " AND (asset_tag LIKE ? OR name LIKE ? OR category LIKE ?"
                " OR serial_number LIKE ? OR location LIKE ?)"
            )
            parameters.extend([wildcard] * 5)
        if status:
            query += " AND status = ?"
            parameters.append(status)
        query += " ORDER BY created_at DESC, id DESC"

        assets = get_db().execute(query, parameters).fetchall()
        return render_template(
            "assets.html", assets=assets, search=search, selected_status=status
        )

    @app.route("/assets/new", methods=("GET", "POST"))
    def asset_create():
        if request.method == "POST":
            values = asset_form_values()
            error = validate_asset(values)
            if error:
                flash(error, "error")
                return render_template("asset_form.html", asset=values), 400

            try:
                cursor = get_db().execute(
                    """
                    INSERT INTO assets
                        (asset_tag, name, category, manufacturer, model,
                         serial_number, location, purchase_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    tuple(
                        values[field] or None
                        if field == "serial_number"
                        else values[field]
                        for field in (
                            "asset_tag",
                            "name",
                            "category",
                            "manufacturer",
                            "model",
                            "serial_number",
                            "location",
                            "purchase_date",
                        )
                    ),
                )
                get_db().commit()
            except sqlite3.IntegrityError as error:
                get_db().rollback()
                if not any(
                    constraint in str(error)
                    for constraint in (
                        "UNIQUE constraint failed: assets.asset_tag",
                        "UNIQUE constraint failed: assets.serial_number",
                    )
                ):
                    raise
                flash("Asset tag and serial number must be unique.", "error")
                return render_template("asset_form.html", asset=values), 400

            flash("Asset created.", "success")
            return redirect(url_for("asset_detail", asset_id=cursor.lastrowid))

        return render_template("asset_form.html", asset={})

    @app.get("/assets/<int:asset_id>")
    def asset_detail(asset_id):
        asset = get_asset_or_404(asset_id)
        allocations = get_db().execute(
            """
            SELECT * FROM allocations
            WHERE asset_id = ?
            ORDER BY allocated_at DESC, id DESC
            """,
            (asset_id,),
        ).fetchall()
        return render_template(
            "asset_detail.html", asset=asset, allocations=allocations
        )

    @app.post("/assets/<int:asset_id>/allocate")
    def asset_allocate(asset_id):
        get_asset_or_404(asset_id)
        assignee = request.form.get("assignee", "").strip()
        if not assignee:
            flash("Enter the person, team, or department receiving the asset.", "error")
        else:
            db = get_db()
            updated = db.execute(
                """
                UPDATE assets SET status = 'allocated'
                WHERE id = ? AND status = 'available'
                """,
                (asset_id,),
            )
            if updated.rowcount != 1:
                db.rollback()
                flash("Only available assets can be allocated.", "error")
            else:
                db.execute(
                    "INSERT INTO allocations (asset_id, assignee) VALUES (?, ?)",
                    (asset_id, assignee),
                )
                db.commit()
                flash("Asset allocated.", "success")
        return redirect(url_for("asset_detail", asset_id=asset_id))

    @app.post("/assets/<int:asset_id>/return")
    def asset_return(asset_id):
        get_asset_or_404(asset_id)
        db = get_db()
        updated = db.execute(
            """
            UPDATE assets SET status = 'available'
            WHERE id = ? AND status = 'allocated'
            """,
            (asset_id,),
        )
        if updated.rowcount != 1:
            db.rollback()
            flash("Only allocated assets can be returned.", "error")
        else:
            allocation = db.execute(
                """
                UPDATE allocations SET returned_at = CURRENT_TIMESTAMP
                WHERE asset_id = ? AND returned_at IS NULL
                """,
                (asset_id,),
            )
            if allocation.rowcount != 1:
                db.rollback()
                abort(409, description="The asset has no active allocation record.")
            db.commit()
            flash("Asset returned and made available.", "success")
        return redirect(url_for("asset_detail", asset_id=asset_id))

    @app.post("/assets/<int:asset_id>/retire")
    def asset_retire(asset_id):
        get_asset_or_404(asset_id)
        updated = get_db().execute(
            """
            UPDATE assets SET status = 'retired'
            WHERE id = ? AND status = 'available'
            """,
            (asset_id,),
        )
        if updated.rowcount != 1:
            get_db().rollback()
            flash("Only available assets can be retired.", "error")
        else:
            get_db().commit()
            flash("Asset retired.", "success")
        return redirect(url_for("asset_detail", asset_id=asset_id))

    # Sprint 1 S1-02: asset editing and direct transfers.
    from sprint1_asset_lifecycle import register_asset_lifecycle
    register_asset_lifecycle(app, get_db, get_asset_or_404, asset_form_values, validate_asset)

    return app


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"], detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def get_asset_or_404(asset_id):
    asset = get_db().execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if asset is None:
        abort(404)
    return asset


def asset_form_values():
    return {
        field: request.form.get(field, "").strip()
        for field in (
            "asset_tag",
            "name",
            "category",
            "manufacturer",
            "model",
            "serial_number",
            "location",
            "purchase_date",
        )
    }


def validate_asset(values):
    if not values["asset_tag"] or not values["name"] or not values["category"]:
        return "Asset tag, name, and category are required."
    if values["purchase_date"]:
        try:
            from datetime import date

            date.fromisoformat(values["purchase_date"])
        except ValueError:
            return "Purchase date must be a valid date."
    return None


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
