"""
explore_db.py – Print a full human-readable dump of the audia SQLite database.

Usage:
    python scripts/explore_db.py
    python scripts/explore_db.py --db /path/to/custom/audia.db
"""

import argparse
import json
import sqlite3
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────────

def _default_db() -> Path:
    return Path.home() / ".audia" / "audia.db"


def _separator(char: str = "─", width: int = 72) -> str:
    return char * width


def _fmt_value(col_name: str, value: object) -> str:
    """Pretty-format a single cell value."""
    if value is None:
        return "NULL"
    # Try to pretty-print JSON columns (authors, paper_ids, …)
    if isinstance(value, str) and value.startswith(("[", "{")):
        try:
            parsed = json.loads(value)
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass
    return str(value)


# ── main logic ───────────────────────────────────────────────────────────────

def explore(db_path: Path) -> None:
    if not db_path.exists():
        print(f"[error] Database not found: {db_path}")
        return

    print(_separator("═"))
    print(f"  DATABASE: {db_path}  ({db_path.stat().st_size / 1024:.1f} KB)")
    print(_separator("═"))

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # ── list tables ──────────────────────────────────────────────────────────
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]

    print(f"\nTables ({len(tables)}): {', '.join(tables)}\n")

    for table in tables:
        print(_separator("═"))
        print(f"  TABLE: {table}")
        print(_separator("═"))

        # schema
        cur.execute(f"PRAGMA table_info({table})")
        columns = cur.fetchall()
        print("\nSchema:")
        print(f"  {'#':<4} {'name':<24} {'type':<16} {'notnull':<9} {'default':<16} {'pk'}")
        print(f"  {_separator('-', 70)}")
        for col in columns:
            print(
                f"  {col['cid']:<4} {col['name']:<24} {col['type']:<16} "
                f"{'YES' if col['notnull'] else 'no':<9} "
                f"{str(col['dflt_value']):<16} "
                f"{'PK' if col['pk'] else ''}"
            )

        # foreign keys
        cur.execute(f"PRAGMA foreign_key_list({table})")
        fks = cur.fetchall()
        if fks:
            print("\nForeign keys:")
            for fk in fks:
                print(f"  {fk['from']} → {fk['table']}.{fk['to']}")

        # row count
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"\nRows: {count}")

        if count == 0:
            print("  (empty)")
            print()
            continue

        # all rows
        cur.execute(f"SELECT * FROM {table}")
        rows = cur.fetchall()
        col_names = [d[0] for d in cur.description]

        print()
        for row_num, row in enumerate(rows, start=1):
            print(f"  ── Row {row_num} {'─' * 56}")
            for col_name in col_names:
                formatted = _fmt_value(col_name, row[col_name])
                # Multi-line values get indented
                if "\n" in formatted:
                    indented = "\n".join("       " + line for line in formatted.splitlines())
                    print(f"    {col_name}:")
                    print(indented)
                else:
                    print(f"    {col_name:<24} {formatted}")
            print()

    con.close()
    print(_separator("═"))
    print("  Done.")
    print(_separator("═"))


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Explore the audia SQLite database.")
    parser.add_argument(
        "--db",
        type=Path,
        default=_default_db(),
        help=f"Path to the database file (default: {_default_db()})",
    )
    args = parser.parse_args()
    explore(args.db)
