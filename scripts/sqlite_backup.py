"""Safe SQLite backup, integrity verification and non-destructive restore."""
import argparse
import sqlite3
from pathlib import Path

def verify_database(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as db:
        result = db.execute("PRAGMA quick_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {result}")
    return result

def backup_database(source, destination):
    source, destination = Path(source), Path(destination)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.resolve() == destination.resolve():
        raise ValueError("Backup destination must differ from the source database.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    verify_database(destination)
    return destination

def restore_database(backup, destination):
    backup, destination = Path(backup), Path(destination)
    if destination.exists():
        raise FileExistsError(f"Restore destination already exists: {destination}")
    verify_database(backup)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    verify_database(destination)
    return destination

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("backup")
    b.add_argument("source")
    b.add_argument("destination")
    v = sub.add_parser("verify")
    v.add_argument("database")
    r = sub.add_parser("restore")
    r.add_argument("backup")
    r.add_argument("destination")
    args = parser.parse_args()
    if args.command == "backup":
        print(backup_database(args.source, args.destination))
    elif args.command == "verify":
        print(verify_database(args.database))
    else:
        print(restore_database(args.backup, args.destination))

if __name__ == "__main__":
    main()
