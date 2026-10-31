"""ClamAV scan of uploaded materials (spec 14.1, "Жүктелген файлдар")."""

import socket
import struct
from typing import Protocol

CHUNK = 64 * 1024


class ScanError(RuntimeError):
    pass


class Scanner(Protocol):
    def scan(self, data: bytes) -> str | None:
        """Return the name of the found threat, or None if the file is clean."""
        ...


class ClamdScanner:
    """clamd INSTREAM protocol over TCP."""

    def __init__(self, host: str, port: int, timeout_s: float = 60.0) -> None:
        self._address = (host, port)
        self._timeout = timeout_s

    def scan(self, data: bytes) -> str | None:
        try:
            with socket.create_connection(self._address, timeout=self._timeout) as sock:
                sock.sendall(b"zINSTREAM\0")
                for start in range(0, len(data), CHUNK):
                    part = data[start : start + CHUNK]
                    sock.sendall(struct.pack("!L", len(part)) + part)
                sock.sendall(struct.pack("!L", 0))
                reply = b""
                while not reply.endswith(b"\0"):
                    received = sock.recv(4096)
                    if not received:
                        break
                    reply += received
        except OSError as exc:
            raise ScanError(f"clamd unavailable: {exc}") from exc
        text = reply.rstrip(b"\0").decode(errors="replace")
        if text.endswith("OK"):
            return None
        if text.endswith("FOUND"):
            return text.split(":", 1)[-1].removesuffix("FOUND").strip()
        raise ScanError(f"clamd error: {text}")
