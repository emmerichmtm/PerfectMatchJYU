"""Local-only browser interface. Run directly or package with PerfectMatch.spec."""
from __future__ import annotations

import argparse
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
from urllib.parse import urlsplit
import webbrowser

import run_matching

ASSETS = Path(__file__).resolve().parent
MAX_REQUEST_BYTES = 10 * 1024 * 1024


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port=8765):
        # Never bind to the LAN, including in the packaged application.
        super().__init__(("127.0.0.1", port), RequestHandler)
        self.token = secrets.token_urlsafe(32)
        self.run_lock = threading.Lock()
        self.origin = f"http://localhost:{self.server_port}"
        self.allowed_hosts = {f"localhost:{self.server_port}", f"127.0.0.1:{self.server_port}"}


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "PerfectMatch"
    sys_version = ""

    def log_message(self, *_):
        pass

    def reply(self, status, content, content_type="application/json; charset=utf-8"):
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False, allow_nan=False).encode("utf-8")
        elif isinstance(content, str):
            content = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        token = self.server.token
        self.send_header("Content-Security-Policy", f"default-src 'self'; script-src 'nonce-{token}'; "
                         f"style-src 'nonce-{token}'; connect-src 'self'; img-src 'self' data:; "
                         "object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def valid_host(self):
        if self.headers.get("Host", "").lower() not in self.server.allowed_hosts:
            self.reply(403, {"error": "Open this application using its localhost address."})
            return False
        return True

    def do_GET(self):
        if not self.valid_host():
            return
        path = urlsplit(self.path).path
        if path == "/":
            page = (ASSETS / "browser.html").read_text(encoding="utf-8")
            self.reply(200, page.replace("__SESSION_TOKEN__", self.server.token), "text/html; charset=utf-8")
        elif path == "/api/example":
            self.reply(200, {name: (ASSETS / "examples" / f"{name}.csv").read_text(encoding="utf-8-sig")
                             for name in ("config", "problem")})
        elif path in {"/templates/config.csv", "/templates/problem.csv"}:
            self.reply(200, (ASSETS / "examples" / Path(path).name).read_bytes(), "text/csv; charset=utf-8")
        elif path == "/manual.pdf":
            self.reply(200, (ASSETS / "manual.pdf").read_bytes(), "application/pdf")
        elif path == "/favicon.ico":
            self.reply(204, b"", "image/x-icon")
        else:
            self.reply(404, {"error": "Page not found."})

    def do_POST(self):
        if not self.valid_host():
            return
        origin = self.headers.get("Origin", "")
        if origin not in {f"http://{host}" for host in self.server.allowed_hosts}:
            self.reply(403, {"error": "Only this application's local browser page can submit files."})
            return
        if not secrets.compare_digest(self.headers.get("X-Session-Token", ""), self.server.token):
            self.reply(403, {"error": "This session has changed. Reload the page and try again."})
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            self.reply(415, {"error": "Expected JSON containing the two CSV files."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                self.reply(413, {"error": "Choose CSV files with a combined size below 10 MB."})
                return
            self.connection.settimeout(30)
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Expected the two CSV files.")
        except (ValueError, UnicodeError, OSError) as exc:
            self.reply(400, {"error": f"Could not read the request: {exc}"})
            return
        path = urlsplit(self.path).path
        if path not in {"/api/run", "/api/stop"}:
            self.reply(404, {"error": "Unknown action."})
            return
        if not self.server.run_lock.acquire(blocking=False):
            self.reply(409, {"error": "A matching run is still in progress. Wait for it to finish."})
            return
        try:
            if path == "/api/stop":
                self.reply(200, {"stopped": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if any(not isinstance(data.get(key), str) or not data[key].strip() for key in ("config", "problem")):
                raise ValueError("Choose both the settings CSV and the participants CSV.")
            with tempfile.TemporaryDirectory(prefix="perfectmatch-") as temp:
                folder = Path(temp)
                for name in ("config", "problem"):
                    (folder / f"{name}.csv").write_text(data[name], encoding="utf-8", newline="")
                result_path, report_path = folder / "result.csv", folder / "report.txt"
                result = run_matching.run(folder / "config.csv", folder / "problem.csv",
                                          result_path, report_path, quiet=True)
                payload = {"summary": result.attrs["summary"], "pairs": result.to_dict(orient="records"),
                           "csv": result_path.read_text(encoding="utf-8-sig"),
                           "report": report_path.read_text(encoding="utf-8")}
            # Temporary inputs and solver outputs have been removed before returning.
            self.reply(200, payload)
        except (ValueError, csv.Error, OSError, RuntimeError, run_matching.core.pulp.PulpSolverError) as exc:
            self.reply(422, {"error": str(exc)})
        except Exception:
            self.reply(500, {"error": "The matching run could not finish. Restart the app and try again."})
        finally:
            self.server.run_lock.release()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765, help="Local port; 0 selects an available port")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the default browser")
    args = parser.parse_args(argv)
    try:
        try:
            server = LocalServer(args.port)
        except OSError:
            if args.port != 8765:
                raise
            server = LocalServer(0)
        if sys.stdout is not None:
            print(f"PerfectMatch JYU is running at {server.origin}", flush=True)
        if not args.no_browser:
            webbrowser.open(server.origin)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    except Exception as exc:
        message = f"PerfectMatch could not start: {exc}"
        if getattr(sys, "frozen", False) and os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, "PerfectMatch JYU", 16)
        else:
            print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
