"""S2-01 license entitlement and asset warranty management."""
from datetime import date
from flask import abort, flash, redirect, render_template, request, url_for

MANAGER_ROLES = ("admin", "asset_manager")
RENEWAL_STATES = ("active", "renewal_pending", "renewed", "expired")
SCHEMA = """
CREATE TABLE IF NOT EXISTS software_licenses (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
 product_name TEXT NOT NULL,
 vendor TEXT NOT NULL DEFAULT '',
 license_reference TEXT NOT NULL DEFAULT '',
 entitlement_count INTEGER NOT NULL CHECK(entitlement_count > 0),
 used_count INTEGER NOT NULL DEFAULT 0 CHECK(used_count >= 0),
 expiry_date TEXT NOT NULL,
 renewal_status TEXT NOT NULL DEFAULT 'active'
  CHECK(renewal_status IN ('active','renewal_pending','renewed','expired')),
 notes TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS software_licenses_expiry ON software_licenses(expiry_date);
CREATE INDEX IF NOT EXISTS software_licenses_asset ON software_licenses(asset_id);
CREATE TABLE IF NOT EXISTS warranties (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
 provider TEXT NOT NULL,
 warranty_reference TEXT NOT NULL DEFAULT '',
 start_date TEXT NOT NULL,
 end_date TEXT NOT NULL,
 notes TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK(start_date <= end_date)
);
CREATE INDEX IF NOT EXISTS warranties_end_date ON warranties(end_date);
CREATE INDEX IF NOT EXISTS warranties_asset ON warranties(asset_id);
"""

def _date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None

def _license_values(form):
    return {key: form.get(key, default).strip() for key, default in (
        ("asset_id", ""), ("product_name", ""), ("vendor", ""),
        ("license_reference", ""), ("entitlement_count", ""),
        ("used_count", "0"), ("expiry_date", ""),
        ("renewal_status", "active"), ("notes", ""))}

def validate_license(values, db):
    if not values["product_name"] or len(values["product_name"]) > 120:
        return "Product name is required and must be at most 120 characters."
    if len(values["vendor"]) > 120 or len(values["license_reference"]) > 100:
        return "Vendor or reference is too long."
    if len(values["notes"]) > 1000:
        return "Notes must be at most 1000 characters."
    try:
        entitlement, used = int(values["entitlement_count"]), int(values["used_count"])
    except (TypeError, ValueError):
        return "Entitlement and usage must be whole numbers."
    if entitlement < 1 or used < 0:
        return "Entitlement must be at least 1 and usage cannot be negative."
    if not _date(values["expiry_date"]):
        return "Expiry date must be a valid ISO date."
    if values["renewal_status"] not in RENEWAL_STATES:
        return "Select a valid renewal status."
    if values["asset_id"]:
        if not values["asset_id"].isdigit() or not db.execute(
            "SELECT 1 FROM assets WHERE id=?", (int(values["asset_id"]),)
        ).fetchone():
            return "Select an existing asset or leave the asset blank."
    return None

def _warranty_values(form):
    return {key: form.get(key, "").strip() for key in (
        "asset_id", "provider", "warranty_reference", "start_date", "end_date", "notes")}

def validate_warranty(values, db):
    if not values["asset_id"].isdigit() or not db.execute(
        "SELECT 1 FROM assets WHERE id=?", (int(values["asset_id"]),)
    ).fetchone():
        return "Select an existing asset."
    if not values["provider"] or len(values["provider"]) > 120:
        return "Warranty provider is required and must be at most 120 characters."
    if len(values["warranty_reference"]) > 100 or len(values["notes"]) > 1000:
        return "Warranty reference or notes are too long."
    start, end = _date(values["start_date"]), _date(values["end_date"])
    if not start or not end:
        return "Coverage start and end must be valid ISO dates."
    if start > end:
        return "Coverage end date cannot be before the start date."
    return None

def _license_row(row):
    item = dict(row)
    item["over_entitled"] = item["used_count"] > item["entitlement_count"]
    item["expired"] = bool(_date(item["expiry_date"]) and _date(item["expiry_date"]) < date.today())
    return item

def register_license_warranty(app, get_db, get_asset_or_404, roles_required, record_audit_event):
    with app.app_context():
        get_db().executescript(SCHEMA)

    @app.get("/licenses")
    def license_list():
        rows = get_db().execute(
            """SELECT l.*, a.asset_tag FROM software_licenses l
               LEFT JOIN assets a ON a.id=l.asset_id ORDER BY l.expiry_date, l.id"""
        ).fetchall()
        return render_template("licenses.html", licenses=[_license_row(r) for r in rows])

    @app.route("/licenses/new", methods=("GET", "POST"))
    @roles_required(*MANAGER_ROLES)
    def license_create():
        assets = get_db().execute("SELECT id, asset_tag, name FROM assets ORDER BY asset_tag").fetchall()
        values = _license_values(request.form) if request.method == "POST" else {}
        if request.method == "POST":
            error = validate_license(values, get_db())
            if error:
                flash(error, "error")
                return render_template("license_form.html", license=values, assets=assets, states=RENEWAL_STATES), 400
            db = get_db()
            cursor = db.execute(
                """INSERT INTO software_licenses
                   (asset_id, product_name, vendor, license_reference, entitlement_count,
                    used_count, expiry_date, renewal_status, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (int(values["asset_id"]) if values["asset_id"] else None,
                 values["product_name"], values["vendor"], values["license_reference"],
                 int(values["entitlement_count"]), int(values["used_count"]),
                 values["expiry_date"], values["renewal_status"], values["notes"]))
            record_audit_event(db, "license.created", "license", cursor.lastrowid,
                {"product_name": values["product_name"], "entitlement_count": int(values["entitlement_count"]),
                 "used_count": int(values["used_count"]), "expiry_date": values["expiry_date"]})
            db.commit()
            flash("License record created.", "success")
            return redirect(url_for("license_list"))
        return render_template("license_form.html", license=values, assets=assets, states=RENEWAL_STATES)

    @app.route("/licenses/<int:license_id>/edit", methods=("GET", "POST"))
    @roles_required(*MANAGER_ROLES)
    def license_edit(license_id):
        db = get_db()
        existing = db.execute("SELECT * FROM software_licenses WHERE id=?", (license_id,)).fetchone()
        if existing is None:
            abort(404)
        assets = db.execute("SELECT id, asset_tag, name FROM assets ORDER BY asset_tag").fetchall()
        values = _license_values(request.form) if request.method == "POST" else dict(existing)
        if request.method == "POST":
            error = validate_license(values, db)
            if error:
                flash(error, "error")
                return render_template("license_form.html", license=values, assets=assets, states=RENEWAL_STATES), 400
            db.execute(
                """UPDATE software_licenses SET asset_id=?, product_name=?, vendor=?,
                   license_reference=?, entitlement_count=?, used_count=?, expiry_date=?,
                   renewal_status=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (int(values["asset_id"]) if values["asset_id"] else None, values["product_name"],
                 values["vendor"], values["license_reference"], int(values["entitlement_count"]),
                 int(values["used_count"]), values["expiry_date"], values["renewal_status"],
                 values["notes"], license_id))
            record_audit_event(db, "license.updated", "license", license_id,
                {"product_name": values["product_name"], "entitlement_count": int(values["entitlement_count"]),
                 "used_count": int(values["used_count"]), "expiry_date": values["expiry_date"]})
            db.commit()
            flash("License record updated.", "success")
            return redirect(url_for("license_list"))
        return render_template("license_form.html", license=values, assets=assets, states=RENEWAL_STATES)

    @app.get("/warranties")
    def warranty_list():
        rows = get_db().execute(
            """SELECT w.*, a.asset_tag, a.name AS asset_name FROM warranties w
               JOIN assets a ON a.id=w.asset_id ORDER BY w.end_date, w.id"""
        ).fetchall()
        return render_template("warranties.html", warranties=rows)

    @app.route("/warranties/new", methods=("GET", "POST"))
    @roles_required(*MANAGER_ROLES)
    def warranty_create():
        assets = get_db().execute("SELECT id, asset_tag, name FROM assets ORDER BY asset_tag").fetchall()
        values = _warranty_values(request.form) if request.method == "POST" else {}
        if request.method == "POST":
            error = validate_warranty(values, get_db())
            if error:
                flash(error, "error")
                return render_template("warranty_form.html", warranty=values, assets=assets), 400
            db = get_db()
            cursor = db.execute(
                """INSERT INTO warranties (asset_id, provider, warranty_reference, start_date, end_date, notes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (int(values["asset_id"]), values["provider"], values["warranty_reference"],
                 values["start_date"], values["end_date"], values["notes"]))
            record_audit_event(db, "warranty.created", "warranty", cursor.lastrowid,
                {"asset_id": int(values["asset_id"]), "provider": values["provider"],
                 "start_date": values["start_date"], "end_date": values["end_date"]})
            db.commit()
            flash("Warranty record created.", "success")
            return redirect(url_for("warranty_list"))
        return render_template("warranty_form.html", warranty=values, assets=assets)

    @app.route("/warranties/<int:warranty_id>/edit", methods=("GET", "POST"))
    @roles_required(*MANAGER_ROLES)
    def warranty_edit(warranty_id):
        db = get_db()
        existing = db.execute("SELECT * FROM warranties WHERE id=?", (warranty_id,)).fetchone()
        if existing is None:
            abort(404)
        assets = db.execute("SELECT id, asset_tag, name FROM assets ORDER BY asset_tag").fetchall()
        values = _warranty_values(request.form) if request.method == "POST" else dict(existing)
        if request.method == "POST":
            error = validate_warranty(values, db)
            if error:
                flash(error, "error")
                return render_template("warranty_form.html", warranty=values, assets=assets), 400
            db.execute(
                """UPDATE warranties SET asset_id=?, provider=?, warranty_reference=?,
                   start_date=?, end_date=?, notes=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (int(values["asset_id"]), values["provider"], values["warranty_reference"],
                 values["start_date"], values["end_date"], values["notes"], warranty_id))
            record_audit_event(db, "warranty.updated", "warranty", warranty_id,
                {"asset_id": int(values["asset_id"]), "provider": values["provider"],
                 "start_date": values["start_date"], "end_date": values["end_date"], "notes": values["notes"]})
            db.commit()
            flash("Warranty record updated.", "success")
            return redirect(url_for("warranty_list"))
        return render_template("warranty_form.html", warranty=values, assets=assets)
