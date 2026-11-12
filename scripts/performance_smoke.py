"""Repeatable, non-gating inventory query performance smoke check."""
import sqlite3
import tempfile
import time
from pathlib import Path

def run(rows=5000):
    with tempfile.TemporaryDirectory() as folder:
        db_path = Path(folder) / "benchmark.sqlite3"
        with sqlite3.connect(db_path) as db:
            db.execute("CREATE TABLE assets (id INTEGER PRIMARY KEY, asset_tag TEXT, name TEXT, category TEXT, status TEXT)")
            db.execute("CREATE INDEX idx_assets_category_status ON assets(category, status)")
            db.executemany(
                "INSERT INTO assets(asset_tag,name,category,status) VALUES(?,?,?,?)",
                ((f"TAG-{i:06d}", f"Device {i}", "Laptop" if i % 3 else "Monitor",
                  "available" if i % 2 else "allocated") for i in range(rows)))
            db.commit()
            started = time.perf_counter()
            found = db.execute(
                "SELECT COUNT(*) FROM assets WHERE category=? AND status=?",
                ("Laptop", "available")).fetchone()[0]
            elapsed_ms = (time.perf_counter() - started) * 1000
            plan = db.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM assets WHERE category=? AND status=?",
                ("Laptop", "available")).fetchone()[3]
        print(f"rows={rows} matched={found} query_ms={elapsed_ms:.3f} plan={plan}")
        return elapsed_ms, found, plan

if __name__ == "__main__":
    run()
