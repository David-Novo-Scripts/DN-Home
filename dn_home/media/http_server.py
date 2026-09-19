"""One-file HTTP server used by a Cast receiver to fetch generated audio."""

from __future__ import annotations

from contextlib import AbstractContextManager
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import logging
from pathlib import Path
import re
import secrets
import threading
from typing import Any

from dn_home.voice.models import AudioAsset


LOGGER = logging.getLogger(__name__)
RANGE_PATTERN = re.compile(r"bytes=(\d*)-(\d*)$")


class MediaServerError(RuntimeError):
    """Raised when temporary media cannot be served safely."""


class _MediaHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class TemporaryAudioServer(AbstractContextManager["TemporaryAudioServer"]):
    def __init__(self, asset: AudioAsset, bind_host: str, *, port: int = 0):
        address = ipaddress.ip_address(bind_host)
        if address.version != 4 or address.is_unspecified or address.is_loopback:
            raise MediaServerError(f"Refusing unsafe media bind address: {bind_host}")
        if not asset.path.is_file():
            raise MediaServerError(f"Audio file does not exist: {asset.path}")
        self.asset = asset
        self.bind_host = bind_host
        self.requested_port = port
        self.token = secrets.token_urlsafe(32)
        self.route = f"/{self.token}{asset.path.suffix}"
        self.request_started = threading.Event()
        self.request_completed = threading.Event()
        self._server: _MediaHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if not self._server:
            raise MediaServerError("Media server has not been started")
        return int(self._server.server_address[1])

    @property
    def url(self) -> str:
        return f"http://{self.bind_host}:{self.port}{self.route}"

    @property
    def sanitized_url(self) -> str:
        return f"http://{self.bind_host}:{self.port}/<redacted>{self.asset.path.suffix}"

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "DNHomeMedia/1"

            def log_message(self, format_string: str, *args: Any) -> None:
                LOGGER.debug("event=http.request client=%s", self.client_address[0])

            def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
                self._serve(send_body=False)

            def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
                self._serve(send_body=True)

            def _serve(self, *, send_body: bool) -> None:
                if self.path != owner.route:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                owner.request_started.set()
                try:
                    file_size = owner.asset.path.stat().st_size
                    start, end, status = 0, file_size - 1, HTTPStatus.OK
                    range_header = self.headers.get("Range")
                    if range_header:
                        match = RANGE_PATTERN.fullmatch(range_header.strip())
                        if not match:
                            self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                            return
                        start_text, end_text = match.groups()
                        if not start_text:
                            length = int(end_text or "0")
                            start = max(0, file_size - length)
                        else:
                            start = int(start_text)
                        end = min(int(end_text) if end_text else file_size - 1, file_size - 1)
                        if start > end or start >= file_size:
                            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                            self.send_header("Content-Range", f"bytes */{file_size}")
                            self.end_headers()
                            return
                        status = HTTPStatus.PARTIAL_CONTENT

                    length = end - start + 1
                    self.send_response(status)
                    self.send_header("Content-Type", owner.asset.content_type)
                    self.send_header("Content-Length", str(length))
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    if status == HTTPStatus.PARTIAL_CONTENT:
                        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                    self.end_headers()
                    if send_body:
                        with owner.asset.path.open("rb") as audio:
                            audio.seek(start)
                            remaining = length
                            while remaining:
                                chunk = audio.read(min(64 * 1024, remaining))
                                if not chunk:
                                    break
                                self.wfile.write(chunk)
                                remaining -= len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    LOGGER.debug("event=http.client_disconnected")
                finally:
                    owner.request_completed.set()

        return Handler

    def start(self) -> "TemporaryAudioServer":
        if self._server:
            return self
        try:
            self._server = _MediaHTTPServer(
                (self.bind_host, self.requested_port), self._handler_class()
            )
        except OSError as error:
            raise MediaServerError(
                f"Unable to bind temporary HTTP server to {self.bind_host}: {error}"
            ) from error
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="dn-home-media",
            daemon=True,
        )
        self._thread.start()
        LOGGER.debug(
            "event=http.started bind=%s port=%d route_token=redacted",
            self.bind_host,
            self.port,
        )
        return self

    def stop(self) -> None:
        if not self._server:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=2)
        LOGGER.debug("event=http.stopped bind=%s port=%d", self.bind_host, self.port)
        self._thread = None
        self._server = None

    def __enter__(self) -> "TemporaryAudioServer":
        return self.start()

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.stop()

