"""S2-04 reporting and validated CSV import/export routes."""
import csv
import io
import sqlite3
from datetime import date

from flask import abort, flash, make_response, redirect, render_template, request, url_for

CSV_COLUMNS = (
    "asset_tag", "name", "category", "manufacturer", "model",
    "serial_number", "status", "location", "purchase_date", "assignee",
)
ASSET_STATUSES = {"available", "allocated", "maintenance", "retired"}
MAX_IMPORT_BYTES = 1_048_576
MAX_IMPORT_ROWS = 500


def register_reports(app, get_db, roles_required, record_audit_event):
    @app.get("/reports")
    def reports():
        db = get_db()
        summary = db.execute(
            """SELECT status, COUNT(*) AS count FROM assets
               GROUP BY status ORDER BY status"""
        ).fetchall()
        categories = db.execute(
            """SELECT category, COUNT(*) AS count FROM assets
               GROUP BY category COLLATE NOCASE
               ORDER BY category COLLATE NOCASE"""
        ).fetchall()
        return render_template(
            "reports.html", summary=summary, categories=categories,
            import_limit=MAX_IMPORT_ROWS,
        )

    @app.get("/reports/assets.csv")
    def export_assets_csv():
        status = request.args.get("status", "").strip()
        if status and status not in ASSET_STATUSES:
            abort(400, description="Invalid asset status filter.")

        query = """SELECT a.asset_tag, a.name, a.category, a.manufacturer,
                          a.model, a.serial_number, a.status, a.location,
                          a.purchase_date, COALESCE(al.assignee, '') AS assignee,
                          a.created_at
                   FROM assets AS a
                   LEFT JOIN allocations AS al
                     ON al.asset_id = a.id AND al.returned_at IS NULL"""
        params = ()
        if status:
            query += " WHERE a.status = ?"
            params = (status,)
        query += " ORDER BY a.asset_tag COLLATE NOCASE"
        rows = get_db().execute(query, params).fetchall()

        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow((*CSV_COLUMNS, "created_at"))
        for row in rows:
            writer.writerow([row[column] or "" for column in
                (*CSV_COLUMNS, "created_at")])

        response = make_response("\ufeff" + output.getvalue())
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = 'attachment; filename="itams-assets.csv"'
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/reports/import")
    @roles_required("admin", "asset_manager")
    def import_assets_csv():
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            flash("Choose a CSV file to import.", "error")
            return redirect(url_for("reports"))

        raw = upload.read(MAX_IMPORT_BYTES + 1)
        if not raw:
            flash("The uploaded CSV file is empty.", "error")
            return redirect(url_for("reports"))
        if len(raw) > MAX_IMPORT_BYTES:
            flash("CSV file exceeds the 1 MB import limit.", "error")
            return redirect(url_for("reports"))
        try:
            text = raw.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text, newline=""))
            if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError("CSV header is missing or contains duplicate columns.")
            if tuple(reader.fieldnames) != CSV_COLUMNS:
                raise ValueError("CSV columns must match the documented template and order.")
            records = []
            seen_tags, seen_serials = set(), set()
            for line_number, raw_row in enumerate(reader, start=2):
                if line_number - 1 > MAX_IMPORT_ROWS:
                    raise ValueError(f"CSV may contain at most {MAX_IMPORT_ROWS} data rows.")
                if None in raw_row:
                    raise ValueError(f"Row {line_number} has more columns than the header.")
                row = {key: (raw_row.get(key) or "").strip() for key in CSV_COLUMNS}
                if not row["asset_tag"] or not row["name"] or not row["category"]:
                    raise ValueError(f"Row {line_number}: asset_tag, name and category are required.")
                if row["status"] not in ASSET_STATUSES:
                    raise ValueError(f"Row {line_number}: invalid status.")
                if row["status"] == "allocated" and not row["assignee"]:
                    raise ValueError(f"Row {line_number}: allocated assets require an assignee.")
                if row["status"] != "allocated" and row["assignee"]:
                    raise ValueError(f"Row {line_number}: assignee is only valid for allocated assets.")
                if row["purchase_date"]:
                    try:
                        date.fromisoformat(row["purchase_date"])
                    except ValueError as error:
                        raise ValueError(f"Row {line_number}: purchase_date must use YYYY-MM-DD.") from error
                tag_key = row["asset_tag"].casefold()
                serial_key = row["serial_number"].casefold()
                if tag_key in seen_tags:
                    raise ValueError(f"Row {line_number}: duplicate asset_tag in CSV.")
                if serial_key and serial_key in seen_serials:
                    raise ValueError(f"Row {line_number}: duplicate serial_number in CSV.")
                seen_tags.add(tag_key)
                if serial_key:
                    seen_serials.add(serial_key)
                records.append(row)
            if not records:
                raise ValueError("CSV contains a header but no asset rows.")

            db = get_db()
            for row in records:
                duplicate = db.execute(
                    """SELECT 1 FROM assets WHERE asset_tag = ?
                       OR (? <> '' AND serial_number = ?) LIMIT 1""",
                    (row["asset_tag"], row["serial_number"], row["serial_number"]),
                ).fetchone()
                if duplicate:
                    raise ValueError(f"Asset tag or serial number already exists: {row['asset_tag']}.")

            try:
                for row in records:
                    cursor = db.execute(
                        """INSERT INTO assets
                           (asset_tag, name, category, manufacturer, model,
                            serial_number, status, location, purchase_date)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        tuple(
                            row[column] or None if column == "serial_number" else row[column]
                            for column in CSV_COLUMNS if column != "assignee"
                        ),
                    )
                    if row["status"] == "allocated":
                        db.execute(
                            "INSERT INTO allocations (asset_id, assignee) VALUES (?, ?)",
                            (cursor.lastrowid, row["assignee"]),
                        )
                    record_audit_event(
                        db, "asset.imported", "asset", cursor.lastrowid,
                        {"asset_tag": row["asset_tag"], "source": "csv",
                         "status": row["status"]},
                    )
                db.commit()
            except Exception:
                db.rollback()
                raise
        except (UnicodeDecodeError, csv.Error, ValueError, sqlite3.IntegrityError) as error:
            get_db().rollback()
            flash(f"CSV import rejected: {error}", "error")
            return redirect(url_for("reports"))

        flash(f"Successfully imported {len(records)} assets.", "success")
        return redirect(url_for("reports"))
