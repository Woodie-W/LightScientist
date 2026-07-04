from __future__ import annotations

import json
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .webui_data import (
    build_overview,
    build_pipeline,
    build_workers,
    current_skill,
    list_artifacts,
    list_skills,
    process_excerpt,
    read_events,
    read_state,
    safe_read_workspace_file,
    stage_runs,
    workspace_root,
)


STATIC_ROOT = Path(__file__).with_name("webui_static")


class LightScientistWebUIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, workspace: Path, **kwargs) -> None:
        self.workspace = workspace
        super().__init__(*args, directory=str(STATIC_ROOT), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            if parsed.path in {"/", "/index.html", ""}:
                self.path = "/index.html"
            return super().do_GET()
        try:
            self._handle_api(parsed)
        except FileNotFoundError:
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"error": f"internal error: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args) -> None:
        return

    def _handle_api(self, parsed) -> None:
        query = parse_qs(parsed.query)
        if parsed.path == "/api/overview":
            return self._send_json(build_overview(self.workspace))
        if parsed.path == "/api/state":
            return self._send_json(read_state(self.workspace))
        if parsed.path == "/api/events":
            limit = int(query.get("limit", ["200"])[0])
            return self._send_json({"events": list(reversed(read_events(self.workspace, limit=limit)))})
        if parsed.path == "/api/pipeline":
            state = read_state(self.workspace)
            return self._send_json(build_pipeline(state, read_events(self.workspace, limit=300)))
        if parsed.path == "/api/workers":
            return self._send_json({"workers": build_workers(read_events(self.workspace, limit=300))})
        if parsed.path == "/api/artifacts":
            return self._send_json({"artifacts": list_artifacts(self.workspace)})
        if parsed.path == "/api/runs":
            return self._send_json({"stage_runs": stage_runs(self.workspace)})
        if parsed.path == "/api/knowledge":
            state = read_state(self.workspace)
            return self._send_json(
                {
                    "skills": list_skills(self.workspace),
                    "current_skill": current_skill(self.workspace, str(state.get("stage", ""))),
                    "process_excerpt": process_excerpt(self.workspace),
                }
            )
        if parsed.path == "/api/file":
            path = query.get("path", [""])[0]
            if not path:
                raise ValueError("missing path")
            return self._send_json(safe_read_workspace_file(self.workspace, path))
        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def serve_webui(workspace: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    root = workspace_root(workspace)
    handler = partial(LightScientistWebUIHandler, workspace=root)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"LightScientist WebUI serving {root} at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
