"""Newline-delimited JSON IPC over Unix domain sockets."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import socket
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

MAX_MESSAGE_BYTES = 1024 * 1024
CommandHandler = Callable[
    [str, dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]
]


class IpcError(RuntimeError):
    """A structured IPC failure returned to the client."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


def _encode_request(
    method: str, params: dict[str, Any] | None, request_id: int
) -> bytes:
    if not method:
        raise ValueError("method must not be empty")
    request = {
        "id": request_id,
        "method": method,
        "params": params or {},
    }
    return (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")


def _decode_response(line: bytes) -> dict[str, Any]:
    if not line:
        raise IpcError("connection_closed", "daemon closed the connection")
    try:
        response = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IpcError("invalid_response", "daemon returned invalid JSON") from exc
    if not isinstance(response, dict):
        raise IpcError("invalid_response", "daemon response must be an object")
    if response.get("ok") is not True:
        error = response.get("error")
        if not isinstance(error, dict):
            raise IpcError("request_failed", "daemon request failed")
        raise IpcError(
            str(error.get("code", "request_failed")),
            str(error.get("message", "daemon request failed")),
        )
    result = response.get("result", {})
    return result if isinstance(result, dict) else {"value": result}


class JsonLineServer:
    """Serve JSON requests on a Unix socket and publish optional events."""

    def __init__(self, path: str | Path, handler: CommandHandler) -> None:
        self._path = Path(path)
        self._handler = handler
        self._server: asyncio.AbstractServer | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._write_lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        return self._path

    async def start(self) -> None:
        if self._server is not None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            if await asyncio.to_thread(self._is_live_endpoint):
                raise RuntimeError(f"IPC endpoint is already in use: {self._path}")
            self._path.unlink(missing_ok=True)

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self._path),
            limit=MAX_MESSAGE_BYTES + 1,
        )
        os.chmod(self._path, 0o600)

    def _is_live_endpoint(self) -> bool:
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(0.2)
        try:
            probe.connect(str(self._path))
        except OSError:
            return False
        else:
            return True
        finally:
            probe.close()

    async def close(self) -> None:
        if self._server is None:
            return
        server = self._server
        self._server = None
        server.close()
        await server.wait_closed()
        for writer in tuple(self._clients):
            writer.close()
        self._clients.clear()
        self._path.unlink(missing_ok=True)

    async def broadcast(self, event: str, data: dict[str, Any]) -> None:
        line = (
            json.dumps({"event": event, "data": data}, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        async with self._write_lock:
            for writer in tuple(self._clients):
                try:
                    writer.write(line)
                except Exception:
                    self._clients.discard(writer)
            for writer in tuple(self._clients):
                try:
                    await writer.drain()
                except Exception:
                    self._clients.discard(writer)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._clients.add(writer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    return
                response = await self._dispatch(line)
                async with self._write_lock:
                    writer.write(
                        (json.dumps(response, ensure_ascii=False) + "\n").encode(
                            "utf-8"
                        )
                    )
                    await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError, OSError):
            pass
        finally:
            self._clients.discard(writer)
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def _dispatch(self, line: bytes) -> dict[str, Any]:
        request_id = None
        try:
            request = json.loads(line.decode("utf-8"))
            if not isinstance(request, dict):
                raise IpcError("invalid_request", "request must be an object")
            request_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})
            if not isinstance(method, str) or not method:
                raise IpcError("invalid_request", "method must be a string")
            if not isinstance(params, dict):
                raise IpcError("invalid_request", "params must be an object")
            result = self._handler(method, params)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, dict):
                result = {"value": result}
            return {"id": request_id, "ok": True, "result": result}
        except IpcError as exc:
            return {
                "id": request_id,
                "ok": False,
                "error": {"code": exc.code, "message": str(exc)},
            }
        except Exception as exc:
            return {
                "id": request_id,
                "ok": False,
                "error": {"code": "internal_error", "message": str(exc)},
            }


async def request(
    path: str | Path,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: float = 5.0,
    request_id: int = 1,
) -> dict[str, Any]:
    """Send one asynchronous request to a daemon."""
    reader, writer = await asyncio.open_unix_connection(str(path))
    try:
        writer.write(_encode_request(method, params, request_id))
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass
    return _decode_response(line)


def request_sync(
    path: str | Path,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: float = 5.0,
    request_id: int = 1,
) -> dict[str, Any]:
    """Send one blocking request; use from a worker thread, not a UI thread."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(path))
        client.sendall(_encode_request(method, params, request_id))
        line = client.makefile("rb").readline()
    return _decode_response(line)
