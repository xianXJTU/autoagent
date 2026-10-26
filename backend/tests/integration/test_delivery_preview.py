from __future__ import annotations

import sys
import urllib.request
import zipfile
from pathlib import Path

from backend.app.services.delivery import package_project, write_start_script
from backend.app.services.preview import PreviewManager
from backend.app.workspace.ports import PortAllocator


SERVER = """\
import argparse, http.server, socketserver
parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8000)
args = parser.parse_args()
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *args):
        pass
with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as httpd:
    httpd.serve_forever()
"""


def test_start_script_and_zip(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "main.py").write_text("app = None\n", encoding="utf-8")
    (repo / "README.md").write_text("# 项目\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")
    (repo / ".git").mkdir()
    (repo / ".git" / "config").write_text("x", encoding="utf-8")

    script = write_start_script(repo)
    assert "app.main:app" in script.read_text(encoding="utf-8")

    archive = package_project(repo, tmp_path / "out" / "project.zip")
    with zipfile.ZipFile(archive) as handle:
        names = set(handle.namelist())
    assert "README.md" in names
    assert "start.ps1" in names
    assert "tests/test_a.py" in names
    assert not any(name.startswith(".git/") for name in names)


def test_preview_start_and_stop(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text(SERVER, encoding="utf-8")
    allocator = PortAllocator(start=18900, end=18910)
    manager = PreviewManager(allocator)
    session = manager.start("p1", repo, python=Path(sys.executable), timeout=20)
    try:
        with urllib.request.urlopen(session.url, timeout=5) as response:
            assert response.status == 200
            assert response.read() == b"ok"
    finally:
        assert manager.stop("p1")
    assert allocator.allocated() == set()
