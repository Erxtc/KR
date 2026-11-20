"""Add a price to every claim in an existing kr.sqlite.

A new database gets these columns from ``create_all``. An old one does not, because
``create_all`` only creates tables - so this walks the live file and adds what is
missing. Idempotent: running it twice does nothing the second time.

    python db/migrate_market.py          # or: python -m db.migrate_market

The copy it leaves next to the file is the undo.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "kr.sqlite"

#: table -> [(column, sql type and default)]
COLUMNS: dict[str, list[tuple[str, str]]] = {
    "is_": [("belief", "REAL")],
    "assumptionmatching": [("belief", "REAL")],
    "value": [("belief", "REAL")],
    "market": [
        ("question", "VARCHAR NOT NULL DEFAULT ''"),
        ("binds", "VARCHAR NOT NULL DEFAULT ''"),
        ("price", "REAL"),
    ],
}


def columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f'pragma table_info("{table}")')}


def tables(con: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in con.execute("select name from sqlite_master where type = 'table'")
    }


def migrate(db: Path = DB) -> list[str]:
    if not db.exists():
        raise SystemExit(f"no database at {db}")

    con = sqlite3.connect(db)
    try:
        present = tables(con)
        todo = []
        for table, wanted in COLUMNS.items():
            if table not in present:
                todo.append(f"table {table} is missing: create the database first")
                continue
            have = columns(con, table)
            for name, spec in wanted:
                if name not in have:
                    todo.append(f"alter table {table} add column {name} {spec}")
        if not todo:
            return []

        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        backup = db.with_suffix(f".bak-{stamp}{db.suffix}")
        shutil.copy2(db, backup)
        print(f"backup: {backup.name}")

        for statement in todo:
            if statement.startswith("table"):
                raise SystemExit(f"cannot migrate: {statement}")
            con.execute(statement)
            print(statement.replace("alter table", "added:") .replace(" add column ", " . "))
        con.commit()
        return todo
    finally:
        con.close()


if __name__ == "__main__":
    changed = migrate()
    print("nothing to do" if not changed else f"{len(changed)} columns now carry a price")
    sys.exit(0)
