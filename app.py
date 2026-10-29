import os
import re
import secrets
import sqlite3
from functools import wraps
from pathlib import Path

import click
from flask import (
    Flask,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


ASSET_STATUSES = ("available", "allocated", "maintenance", "retired")
USER_ROLES = (
    "admin",
    "asset_manager",
    "department_manager",
    "employee",
    "auditor",
)
ASSET_MANAGER_ROLES = ("admin", "asset_manager")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
MIN_PASSWORD_LENGTH = 12
DUMMY_PASSWORD_HASH = generate_password_hash("nonexistent-account-password")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (
        role IN (
            'admin',
            'asset_manager',
            'department_manager',
            'employee',
            'auditor'
        )
    ),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

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
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    secret_key = os.environ.get("FLASK_SECRET_KEY")
    if not secret_key and test_config:
        secret_key = test_config.get("SECRET_KEY")
    if not secret_key:
        secret_key = _load_development_secret(app.instance_path)

    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "itams.sqlite3"),
        SECRET_KEY=secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
    )
    if test_config:
        app.config.update(test_config)

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

    @app.context_processor
    def inject_auth_context():
        return {
            "csrf_token": session.get("csrf_token", ""),
            "current_user": getattr(g, "user", None),
        }

    @app.before_request
    def authenticate_request():
        session.setdefault("csrf_token", secrets.token_urlsafe(32))
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            supplied_token = request.form.get("csrf_token", "")
            if not secrets.compare_digest(
                session["csrf_token"], supplied_token
            ):
                abort(400, description="Invalid or missing CSRF token.")

        if request.endpoint == "login":
            user_id = session.get("user_id")
            if user_id is not None:
                user = get_db().execute(
                    "SELECT id, username, role FROM users WHERE id = ?", (user_id,)
                ).fetchone()
                if user is None:
                    session.clear()
                    session["csrf_token"] = secrets.token_urlsafe(32)
                else:
                    g.user = user
            return None

        if request.endpoint in {"static", None}:
            return None

        user_id = session.get("user_id")
        if user_id is None:
            return redirect(url_for("login"))

        user = get_db().execute(
            "SELECT id, username, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is None:
            session.clear()
            return redirect(url_for("login"))
        g.user = user
        return None

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.option(
        "--password",
        prompt=True,
        hide_input=True,
        confirmation_prompt=True,
    )
    def create_admin(username, password):
        """Create the first administrator for a new installation."""
        _validate_new_user(username, password)
        db = get_db()
        if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            raise click.ClickException(
                "An account already exists; use create-user to add accounts."
            )
        _create_user(db, username, password, "admin")
        db.commit()
        click.echo(f"Administrator '{username}' created.")

    @app.cli.command("create-user")
    @click.option("--username", prompt=True)
    @click.option(
        "--role",
        type=click.Choice(USER_ROLES, case_sensitive=False),
        prompt=True,
    )
    @click.option(
        "--password",
        prompt=True,
        hide_input=True,
        confirmation_prompt=True,
    )
    def create_user(username, role, password):
        """Create a user account with the selected application role."""
        _validate_new_user(username, password)
        db = get_db()
        if not db.execute(
            "SELECT 1 FROM users WHERE role = 'admin' LIMIT 1"
        ).fetchone():
            raise click.ClickException(
                "Create the first administrator before adding other users."
            )
        try:
            _create_user(db, username, password, role)
            db.commit()
        except sqlite3.IntegrityError as error:
            db.rollback()
            if "users.username" in str(error):
                raise click.ClickException("That username already exists.") from error
            raise
        click.echo(f"User '{username}' created with role '{role}'.")

    @app.route("/login", methods=("GET", "POST"))
    def login():
        if getattr(g, "user", None) is not None:
            return redirect(url_for("index"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = get_db().execute(
                "SELECT id, username, password_hash, role FROM users "
                "WHERE username = ?",
                (username,),
            ).fetchone()
            password_hash = (
                user["password_hash"] if user else DUMMY_PASSWORD_HASH
            )
            if not check_password_hash(password_hash, password) or user is None:
                flash("Invalid username or password.", "error")
            else:
                session.clear()
                session["user_id"] = user["id"]
                flash(f"Signed in as {user['username']}.", "success")
                return redirect(url_for("index"))

        account_count = get_db().execute(
            "SELECT COUNT(*) AS count FROM users"
        ).fetchone()["count"]
        return render_template("login.html", account_count=account_count)

    @app.post("/logout")
    def logout():
        session.clear()
        flash("You have been signed out.", "success")
        return redirect(url_for("login"))

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
    @roles_required(*ASSET_MANAGER_ROLES)
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
    @roles_required(*ASSET_MANAGER_ROLES)
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
    @roles_required(*ASSET_MANAGER_ROLES)
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
    @roles_required(*ASSET_MANAGER_ROLES)
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

    # S1-02: register lifecycle operations with the shared authorization policy.
    from sprint1_asset_lifecycle import register_asset_lifecycle
    register_asset_lifecycle(
        app, get_db, get_asset_or_404, asset_form_values,
        validate_asset, roles_required,
    )

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


def roles_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user["role"] not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def _load_development_secret(instance_path):
    secret_path = Path(instance_path) / ".flask_secret_key"
    try:
        with secret_path.open("x", encoding="utf-8") as secret_file:
            secret = secrets.token_hex(32)
            secret_file.write(secret)
            return secret
    except FileExistsError:
        secret = secret_path.read_text(encoding="utf-8").strip()
        if not secret:
            raise RuntimeError(f"Flask secret key file is empty: {secret_path}")
        return secret


def _validate_new_user(username, password):
    if not USERNAME_PATTERN.fullmatch(username):
        raise click.ClickException(
            "Username must be 3-64 characters and contain only letters, "
            "numbers, dots, underscores, or hyphens."
        )
    if len(password) < MIN_PASSWORD_LENGTH:
        raise click.ClickException(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )


def _create_user(db, username, password, role):
    db.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username, generate_password_hash(password), role.lower()),
    )


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
