from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("easytier_pyo3")

from ECL.services.connector import ConnectorService


def test_scan_ports_returns_only_protocol_confirmed_minecraft_port(monkeypatch) -> None:
    service = ConnectorService()
    monkeypatch.setattr(service, "_minecraft_listener_ports", lambda: [25565, 38123])
    monkeypatch.setattr(service, "_is_minecraft_server", lambda port: port == 38123)

    assert service.scan_ports() == {"port": 38123}


def test_minecraft_listener_ports_limits_candidates_to_java_processes(monkeypatch) -> None:
    java_process = SimpleNamespace(info={"pid": 101, "name": "javaw.exe", "exe": "C:/Java/bin/javaw.exe"})
    other_process = SimpleNamespace(info={"pid": 102, "name": "python.exe", "exe": "C:/Python/python.exe"})
    connections = [
        SimpleNamespace(pid=101, status="LISTEN", laddr=SimpleNamespace(port=38123)),
        SimpleNamespace(pid=101, status="ESTABLISHED", laddr=SimpleNamespace(port=25565)),
        SimpleNamespace(pid=102, status="LISTEN", laddr=SimpleNamespace(port=25565)),
    ]
    monkeypatch.setattr("ECL.services.connector.psutil.process_iter", lambda _attrs: [java_process, other_process])
    monkeypatch.setattr("ECL.services.connector.psutil.net_connections", lambda kind: connections)
    monkeypatch.setattr("ECL.services.connector.psutil.CONN_LISTEN", "LISTEN")

    assert ConnectorService._minecraft_listener_ports() == [38123]


def test_decode_varint_rejects_incomplete_input() -> None:
    assert ConnectorService._decode_varint(b"\x80") == (None, 0)
    assert ConnectorService._decode_varint(ConnectorService._encode_varint(758)) == (758, 2)


def test_minecraft_status_probe_accepts_valid_status_response(monkeypatch) -> None:
    status = json.dumps({"version": {"name": "1.21.1", "protocol": 767}}).encode()
    packet = b"\x00" + ConnectorService._encode_varint(len(status)) + status
    response = ConnectorService._encode_varint(len(packet)) + packet

    class Connection:
        def __init__(self) -> None:
            self.response = bytearray(response)

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def settimeout(self, _timeout: float) -> None:
            return None

        def sendall(self, _data: bytes) -> None:
            return None

        def recv(self, length: int) -> bytes:
            chunk = self.response[:length]
            del self.response[:length]
            return bytes(chunk)

    monkeypatch.setattr("ECL.services.connector.socket.create_connection", lambda *_args, **_kwargs: Connection())

    assert ConnectorService._is_minecraft_server(38123) is True
