"""Local JSON-lines control server shared by the Android service and UI."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable

CommandHandler = Callable[[dict], dict | Awaitable[dict]]


class ControlServer:
    """Serve small JSON commands on localhost for the Kivy UI."""

    def __init__(
        self,
        handler: CommandHandler,
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> None:
        self._handler = handler
        self._host = host
        self._port = port
        self._server: asyncio.AbstractServer | None = None

    @property
    def port(self) -> int:
        if self._server is None or not self._server.sockets:
            return self._port
        return int(self._server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        if self._server is not None:
            return
        self._server = await asyncio.start_server(
            self._handle_client, self._host, self._port
        )

    async def close(self) -> None:
        if self._server is None:
            return
        server = self._server
        self._server = None
        server.close()
        await server.wait_closed()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    return
                try:
                    command = json.loads(line.decode("utf-8"))
                    if not isinstance(command, dict):
                        raise ValueError("command must be a JSON object")
                    result = self._handler(command)
                    if inspect.isawaitable(result):
                        result = await result
                    response = (
                        result
                        if isinstance(result, dict)
                        else {"ok": False, "error": "invalid handler response"}
                    )
                except Exception as exc:
                    response = {"ok": False, "error": str(exc)}
                writer.write(
                    (json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8")
                )
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError, OSError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
