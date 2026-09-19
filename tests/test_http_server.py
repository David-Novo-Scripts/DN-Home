from http.client import HTTPConnection
from pathlib import Path
import socket

import pytest

from dn_home.media.http_server import MediaServerError, TemporaryAudioServer
from dn_home.voice.models import AudioAsset


def _assigned_private_ip() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(("192.0.2.1", 9))
        address = sock.getsockname()[0]
    if address.startswith("127."):
        pytest.skip("No non-loopback IPv4 address available")
    return address


def _fetch_with_server_initiated_close(bind_ip: str, port: int, route: str) -> bytes:
    with socket.create_connection((bind_ip, port), timeout=2) as client:
        client.sendall(
            f"GET {route} HTTP/1.0\r\nHost: {bind_ip}\r\n\r\n".encode("ascii")
        )
        response = bytearray()
        while chunk := client.recv(4096):
            response.extend(chunk)
    return bytes(response)


def test_serves_only_random_exact_path_and_ranges(tmp_path: Path) -> None:
    path = tmp_path / "speech.tts.mp3"
    path.write_bytes(b"0123456789")
    asset = AudioAsset(path, "audio/mpeg")
    bind_ip = _assigned_private_ip()

    with TemporaryAudioServer(asset, bind_ip) as server:
        assert server.token not in server.sanitized_url
        assert "<redacted>" in server.sanitized_url

        connection = HTTPConnection(bind_ip, server.port, timeout=2)
        connection.request("GET", "/not-the-token.mp3")
        assert connection.getresponse().status == 404
        connection.close()

        connection = HTTPConnection(bind_ip, server.port, timeout=2)
        connection.request("GET", server.route, headers={"Range": "bytes=2-5"})
        response = connection.getresponse()
        assert response.status == 206
        assert response.read() == b"2345"
        assert response.getheader("Content-Range") == "bytes 2-5/10"
        connection.close()

        assert server.request_started.is_set()
        assert server.request_completed.is_set()


def test_refuses_wildcard_and_loopback(tmp_path: Path) -> None:
    path = tmp_path / "speech.tts.mp3"
    path.write_bytes(b"ID3")
    asset = AudioAsset(path, "audio/mpeg")

    with pytest.raises(MediaServerError, match="unsafe"):
        TemporaryAudioServer(asset, "0.0.0.0")
    with pytest.raises(MediaServerError, match="unsafe"):
        TemporaryAudioServer(asset, "127.0.0.1")


def test_server_stops_and_releases_port(tmp_path: Path) -> None:
    path = tmp_path / "speech.tts.mp3"
    path.write_bytes(b"ID3")
    bind_ip = _assigned_private_ip()
    server = TemporaryAudioServer(AudioAsset(path, "audio/mpeg"), bind_ip).start()
    port = server.port

    server.stop()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        assert sock.connect_ex((bind_ip, port)) != 0


def test_server_reuses_same_port_immediately_after_completed_request(
    tmp_path: Path,
) -> None:
    path = tmp_path / "speech.tts.mp3"
    path.write_bytes(b"ID3-reuse-test")
    asset = AudioAsset(path, "audio/mpeg")
    bind_ip = _assigned_private_ip()

    first = TemporaryAudioServer(asset, bind_ip).start()
    port = first.port
    first_response = _fetch_with_server_initiated_close(bind_ip, port, first.route)
    first_thread = first._thread
    first.stop()

    assert b"200 OK" in first_response
    assert first_thread is not None and not first_thread.is_alive()

    second = TemporaryAudioServer(asset, bind_ip, port=port).start()
    try:
        second_response = _fetch_with_server_initiated_close(
            bind_ip, port, second.route
        )
        assert b"200 OK" in second_response
    finally:
        second.stop()


def test_server_does_not_allow_concurrent_bind_on_same_port(tmp_path: Path) -> None:
    path = tmp_path / "speech.tts.mp3"
    path.write_bytes(b"ID3-single-server-test")
    asset = AudioAsset(path, "audio/mpeg")
    bind_ip = _assigned_private_ip()
    first = TemporaryAudioServer(asset, bind_ip).start()

    try:
        with pytest.raises(MediaServerError, match="Unable to bind"):
            TemporaryAudioServer(asset, bind_ip, port=first.port).start()
    finally:
        first.stop()
