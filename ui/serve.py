"""Serve the object database as a small web app.

    python ui/serve.py            # http://127.0.0.1:8788
    python ui/serve.py --port 9000 --db other.sqlite

Standard library only, no build step: the browser gets three static files and a
JSON snapshot of the database, and every change posts one operation back and
receives the new snapshot. State lives in ``kr.sqlite``, so closing the tab does
not lose anything and two tabs see the same rows.

Before the first write of a session the database is copied into ``ui/backups/``.
Writes are not versioned and the schema has no history table, so that copy is the
undo.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import threading
import traceback
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import krstore  # noqa: E402  (after sys.path so `python ui/serve.py` works)

UI = HERE
BACKUPS = UI / "backups"
KEEP_BACKUPS = 10

STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/favicon.ico": ("favicon.svg", "image/svg+xml"),
}

LOCK = threading.RLock()


def backup(db: Path) -> Path | None:
    """One copy per session, kept in a short stack, before anything is written."""
    if not db.exists():
        return None
    BACKUPS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    dest = BACKUPS / f"{db.stem}-{stamp}{db.suffix}"
    if not dest.exists():
        shutil.copy2(db, dest)
    for old in sorted(BACKUPS.glob(f"{db.stem}-*{db.suffix}"))[:-KEEP_BACKUPS]:
        try:
            old.unlink()
        except OSError:
            pass
    return dest


class App:
    def __init__(self, db: Path) -> None:
        self.db = db
        self.saved: Path | None = None

    def state(self) -> dict:
        with LOCK:
            payload = krstore.state(self.db)
            payload["backup"] = str(self.saved) if self.saved else None
            return payload

    def mutate(self, op: str, body: dict) -> dict:
        with LOCK:
            if self.saved is None:
                # the copy happens once, before the first thing that cannot be undone
                self.saved = backup(self.db)
            payload = krstore.mutate(op, body, self.db)
            payload["backup"] = str(self.saved) if self.saved else None
            return payload


class Handler(BaseHTTPRequestHandler):
    app: App
    server_version = "KR-UI/0.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # quiet unless asked
        import os

        if os.environ.get("KR_HTTP_LOG"):
            super().log_message(fmt, *args)

    def handle_one_request(self) -> None:
        """A tab closing is not an event; a reset does not deserve a traceback."""
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            self.close_connection = True

    # -- plumbing ----------------------------------------------------------
    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise krstore.StoreError(f"body is not JSON: {exc}") from None
        return body if isinstance(body, dict) else {}

    def _path(self) -> str:
        return self.path.split("?", 1)[0]

    # -- routes ------------------------------------------------------------
    def do_GET(self) -> None:
        route = self._path()
        if route == "/api/state":
            try:
                self._json(200, self.app.state())
            except Exception as exc:  # noqa: BLE001 - the browser needs the reason
                self._json(500, {"error": str(exc), "trace": traceback.format_exc()})
            return
        if route == "/api/health":
            self._json(200, {"ok": True, "db": str(self.app.db), "exists": self.app.db.exists()})
            return
        entry = STATIC.get(route)
        if entry is None:
            self._send(404, b"not found\n", "text/plain; charset=utf-8")
            return
        name, ctype = entry
        file = UI / name
        if not file.exists():
            self._send(404, f"{name} is missing\n".encode(), "text/plain; charset=utf-8")
            return
        self._send(200, file.read_bytes(), ctype)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        if self._path() != "/api/mutate":
            self._json(404, {"error": "not found"})
            return
        try:
            body = self._body()
            op = body.pop("op", "")
            if not op:
                raise krstore.StoreError("op is required")
            self._json(200, self.app.mutate(op, body))
        except krstore.StoreError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"error": str(exc), "trace": traceback.format_exc()})


def serve(db: Path, port: int = 8788, host: str = "127.0.0.1") -> None:
    if not db.exists():
        print(f"no database at {db}", file=sys.stderr)
        print("run db/init.py first, or pass --db", file=sys.stderr)
        raise SystemExit(2)
    app = App(db)
    handler = type("Bound", (Handler,), {"app": app})
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    print(f"kr ui    http://{host}:{port}    db {db}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


def main() -> None:
    p = argparse.ArgumentParser(description="serve kr.sqlite as a web app")
    p.add_argument("--db", default=str(krstore.SCHEMA))
    p.add_argument("--port", type=int, default=8788)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args()
    serve(Path(args.db), args.port, args.host)


if __name__ == "__main__":
    main()
