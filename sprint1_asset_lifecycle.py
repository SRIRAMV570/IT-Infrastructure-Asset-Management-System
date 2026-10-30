"""S1-02 asset lifecycle extension. S1-01 authorization and CSRF are enforced; S1-03 owns auditing."""
import sqlite3
from flask import abort, flash, g, redirect, render_template, request, url_for
import json


def register_asset_lifecycle(
    app, get_db, get_asset_or_404, asset_form_values,
    validate_asset, roles_required,
):
    @app.route("/assets/<int:asset_id>/edit", methods=("GET", "POST"))
    @roles_required("admin", "asset_manager")
    def asset_edit(asset_id):
        asset = get_asset_or_404(asset_id)
        if asset["status"] == "retired":
            abort(409, description="Retired assets cannot be edited.")
        if request.method == "GET":
            return render_template("asset_form.html", asset=dict(asset), is_edit=True)

        values = asset_form_values()
        error = validate_asset(values)
        if error:
            flash(error, "error")
            return render_template("asset_form.html", asset=values, is_edit=True), 400

        db = get_db()
        try:
            before = dict(asset)
            changed = db.execute(
                """UPDATE assets SET asset_tag=?, name=?, category=?,
                   manufacturer=?, model=?, serial_number=?, location=?, purchase_date=?
                   WHERE id=? AND status != 'retired'""",
                (values["asset_tag"], values["name"], values["category"],
                 values["manufacturer"], values["model"], values["serial_number"] or None,
                 values["location"], values["purchase_date"], asset_id),
            )
            if changed.rowcount != 1:
                db.rollback()
                abort(409, description="Asset state changed; retry the edit.")
            after = db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
            db.execute(
                """INSERT INTO audit_events
                   (actor_id, actor_username, action, target_type, target_id, details)
                   VALUES (?, ?, ?, 'asset', ?, ?)""",
                (g.user["id"], g.user["username"], "asset.updated", asset_id,
                 json.dumps({
                     key: {"from": before[key], "to": after[key]}
                     for key in ("asset_tag", "name", "category", "manufacturer",
                                 "model", "serial_number", "location", "purchase_date")
                     if before[key] != after[key]
                 }, sort_keys=True, separators=(",", ":"))),
            )
            db.commit()
        except sqlite3.IntegrityError as exc:
            db.rollback()
            if "UNIQUE constraint failed:" not in str(exc):
                raise
            flash("Asset tag and serial number must be unique.", "error")
            return render_template("asset_form.html", asset=values, is_edit=True), 400
        flash("Asset updated.", "success")
        return redirect(url_for("asset_detail", asset_id=asset_id))

    @app.post("/assets/<int:asset_id>/transfer")
    @roles_required("admin", "asset_manager")
    def asset_transfer(asset_id):
        # Validate before modifying any existing holder.
        assignee = request.form.get("assignee", "").strip()
        if not assignee:
            flash("Enter the new person, team, or department.", "error")
            return redirect(url_for("asset_detail", asset_id=asset_id))
        if len(assignee) > 120:
            flash("Assignee must be 120 characters or fewer.", "error")
            return redirect(url_for("asset_detail", asset_id=asset_id))

        db = get_db()
        try:
            # Serialize competing transfers; preserve old and new holder together.
            db.execute("BEGIN IMMEDIATE")
            asset = db.execute(
                "SELECT status FROM assets WHERE id=?", (asset_id,)
            ).fetchone()
            if asset is None:
                db.rollback()
                abort(404)
            if asset["status"] != "allocated":
                db.rollback()
                flash("Only allocated assets can be transferred.", "error")
                return redirect(url_for("asset_detail", asset_id=asset_id))
            current = db.execute(
                """SELECT id, assignee FROM allocations
                   WHERE asset_id=? AND returned_at IS NULL""",
                (asset_id,),
            ).fetchone()
            if current is None:
                db.rollback()
                abort(409, description="No active allocation record exists.")
            if current["assignee"].casefold() == assignee.casefold():
                db.rollback()
                flash("The asset is already assigned to this holder.", "error")
                return redirect(url_for("asset_detail", asset_id=asset_id))
            closed = db.execute(
                """UPDATE allocations SET returned_at=CURRENT_TIMESTAMP
                   WHERE id=? AND returned_at IS NULL""",
                (current["id"],),
            )
            if closed.rowcount != 1:
                db.rollback()
                abort(409, description="Allocation changed during transfer.")
            db.execute(
                "INSERT INTO allocations (asset_id, assignee) VALUES (?, ?)",
                (asset_id, assignee),
            )
            db.execute(
                """INSERT INTO audit_events
                   (actor_id, actor_username, action, target_type, target_id, details)
                   VALUES (?, ?, 'asset.transferred', 'asset', ?, ?)""",
                (g.user["id"], g.user["username"], asset_id,
                 json.dumps({"from_assignee": current["assignee"],
                             "to_assignee": assignee},
                            sort_keys=True, separators=(",", ":"))),
            )
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            abort(409, description="Transfer conflicted with another allocation.")
        flash("Asset transferred.", "success")
        return redirect(url_for("asset_detail", asset_id=asset_id))
