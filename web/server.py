"""Local web server for the Beacon client (docs/SPEC_M8.md). Standard library only.

    uv run python -m web.server [--port 8765] [--seed 1] [--human europe]

GET  /                      the client
GET  /api/view              the human player's fog-safe view
GET  /api/unit/<id>         options for one of the player's units
GET  /api/city/<id>         details of one of the player's cities
GET  /api/techs | /api/council | /api/population | /api/diplomacy | /api/projects | /api/scores
GET  /api/saves (newest first, with turn and player) | /api/status | /api/continents
POST /api/command           a command dict (the player is filled in)
POST /api/end_turn          AI players act, then the turn ends
POST /api/new               {"seed": int, "human": player id}
POST /api/save | /api/load  {"name": str}
"""

from __future__ import annotations

import argparse
import contextlib
import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from beacon import canonical
from beacon.config import load
from web.session import Session

STATIC = Path(__file__).resolve().parent / "static"


class App:
    def __init__(self, seed: int, human: str):
        self.session = Session(load(), seed, human)
        self.lock = threading.Lock()

    def get(self, path: str) -> Any:
        s = self.session
        parts = path.strip("/").split("/")
        if parts[:2] == ["api", "view"]:
            return s.view()
        if parts[:2] == ["api", "unit"] and len(parts) == 3:
            return s.unit_options(int(parts[2]))
        if parts[:2] == ["api", "city"] and len(parts) == 3:
            return s.city_detail(int(parts[2]))
        simple = {
            "techs": s.techs,
            "council": s.council,
            "population": s.population,
            "cities": s.cities_overview,
            "units": s.units_overview,
            "diplomacy": s.diplomacy,
            "projects": s.projects,
            "scores": s.scores,
            "saves": s.saves,
            "status": s.status,
            "continents": s.continents,
        }
        if len(parts) == 2 and parts[0] == "api" and parts[1] in simple:
            return simple[parts[1]]()
        raise LookupError(path)

    def post(self, path: str, body: dict[str, Any]) -> Any:
        s = self.session
        if path == "/api/command":
            return s.command(body)
        if path == "/api/end_turn":
            return s.end_turn()
        if path == "/api/new":
            s.new(int(body.get("seed", 1)), str(body.get("human", s.human)))
            return {"ok": True}
        if path == "/api/save":
            return {"ok": True, "name": s.save(str(body.get("name", "")))}
        if path == "/api/load":
            s.load(str(body.get("name", "")))
            return {"ok": True}
        raise LookupError(path)


def make_handler(app: App) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:  # keep the console quiet
            return

        def _send(self, code: int, payload: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, code: int, data: Any) -> None:
            self._send(code, canonical.dumps(data).encode("utf-8"), "application/json")

        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            path = self.path.split("?", 1)[0]
            if path.startswith("/api/"):
                try:
                    with app.lock:
                        self._json(200, app.get(path))
                except LookupError:
                    self._json(404, {"ok": False, "error": "not found"})
                except ValueError as err:
                    self._json(400, {"ok": False, "error": str(err)})
                return
            name = "index.html" if path in ("/", "") else path.lstrip("/")
            file = (STATIC / name).resolve()
            if STATIC not in file.parents or not file.is_file():
                self._send(404, b"not found", "text/plain")
                return
            ctype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            self._send(200, file.read_bytes(), ctype)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("expected a JSON object")
                with app.lock:
                    self._json(200, app.post(self.path, body))
            except LookupError:
                self._json(404, {"ok": False, "error": "not found"})
            except (ValueError, TypeError) as err:
                self._json(400, {"ok": False, "error": str(err)})

    return Handler


def serve(port: int = 8765, seed: int = 1, human: str = "europe") -> ThreadingHTTPServer:
    app = App(seed, human)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    server.app = app  # type: ignore[attr-defined]
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="web.server")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--human", default="europe")
    parser.add_argument(
        "--reveal", action="store_true", help="developer: show the whole map (art testing)"
    )
    args = parser.parse_args(argv)
    server = serve(args.port, args.seed, args.human)
    server.app.session.reveal = args.reveal  # type: ignore[attr-defined]
    print(f"Beacon running at http://127.0.0.1:{args.port}")
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
