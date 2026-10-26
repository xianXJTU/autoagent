"""端口分配器。"""

from __future__ import annotations

import socket


class PortAllocator:
    def __init__(self, start: int = 8600, end: int = 8999, host: str = "127.0.0.1") -> None:
        if start > end:
            raise ValueError("端口区间不合法")
        self.start = start
        self.end = end
        self.host = host
        self._allocated: set[int] = set()

    def allocate(self) -> int:
        for port in range(self.start, self.end + 1):
            if port in self._allocated:
                continue
            if self._port_free(port):
                self._allocated.add(port)
                return port
        raise RuntimeError("端口区间已耗尽")

    def release(self, port: int) -> None:
        self._allocated.discard(port)

    def allocated(self) -> set[int]:
        return set(self._allocated)

    def _port_free(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((self.host, port))
                sock.listen(1)
                return True
            except OSError:
                return False
