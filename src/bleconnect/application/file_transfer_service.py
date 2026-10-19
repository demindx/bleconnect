"""File transfer state machine shared by both platforms."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..messages import (
    FILE_ACCEPT,
    FILE_CANCEL,
    FILE_CHUNK,
    FILE_COMPLETE,
    FILE_OFFER,
    FILE_REJECT,
    FILE_RESULT,
    file_packet,
)
from ..protocol import Packet
from .ports import FileSink, FileSinkFactory, FileSource, PacketLink

DEFAULT_CHUNK_SIZE = 64 * 1024
DEFAULT_MAX_FILE_SIZE = 100 * 1024 * 1024
DEFAULT_ACCEPT_TIMEOUT = 30.0
DEFAULT_RESULT_TIMEOUT = 30.0


class TransferDirection(Enum):
    SEND = "send"
    RECEIVE = "receive"


class TransferState(Enum):
    IDLE = "idle"
    OFFERING = "offering"
    AWAITING_ACCEPT = "awaiting_accept"
    SENDING = "sending"
    RECEIVING = "receiving"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TransferProgress:
    transfer_id: str
    name: str
    direction: TransferDirection
    transferred: int
    total: int
    state: TransferState


class TransferError(RuntimeError):
    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class _Incoming:
    sink: FileSink
    name: str
    size: int
    received: int = 0
    hasher: Any = field(default_factory=hashlib.sha256)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class FileTransferService:
    """Send and receive files over a packet link."""

    def __init__(
        self,
        link: PacketLink,
        sink_factory: FileSinkFactory,
        *,
        max_bytes: int = DEFAULT_MAX_FILE_SIZE,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        on_progress: Callable[[TransferProgress], None] | None = None,
        accept_timeout: float = DEFAULT_ACCEPT_TIMEOUT,
        result_timeout: float = DEFAULT_RESULT_TIMEOUT,
    ) -> None:
        if max_bytes <= 0 or chunk_size <= 0:
            raise ValueError("file limits must be positive")
        if accept_timeout <= 0 or result_timeout <= 0:
            raise ValueError("timeouts must be positive")
        self._link = link
        self._sink_factory = sink_factory
        self._max_bytes = max_bytes
        self._chunk_size = chunk_size
        self._on_progress = on_progress
        self._accept_timeout = accept_timeout
        self._result_timeout = result_timeout
        self._pending: dict[str, asyncio.Future[Packet]] = {}
        self._incoming: dict[str, _Incoming] = {}
        self._cancelled: set[str] = set()
        self._lock = asyncio.Lock()
        self._state = TransferState.IDLE
        self._progress: TransferProgress | None = None

    @property
    def state(self) -> TransferState:
        return self._state

    @property
    def progress(self) -> TransferProgress | None:
        return self._progress

    def set_progress_listener(
        self, listener: Callable[[TransferProgress], None] | None
    ) -> None:
        self._on_progress = listener

    async def send(self, source: FileSource) -> TransferProgress:
        if not _is_int(source.size) or source.size < 0:
            raise TransferError("invalid_size", "file size is invalid")
        if source.size > self._max_bytes:
            raise TransferError("file_too_large", "file exceeds the configured limit")

        async with self._lock:
            if self._incoming:
                raise TransferError("busy", "a receive is already in progress")

            transfer_id = str(uuid.uuid4())
            name = source.name
            self._cancelled.discard(transfer_id)
            self._set_state(
                TransferState.OFFERING,
                transfer_id,
                name,
                TransferDirection.SEND,
                0,
                source.size,
            )
            await self._link.send(
                file_packet(
                    FILE_OFFER,
                    {
                        "transfer_id": transfer_id,
                        "name": name,
                        "size": source.size,
                        "mime": "application/octet-stream",
                    },
                )
            )

            self._set_state(
                TransferState.AWAITING_ACCEPT,
                transfer_id,
                name,
                TransferDirection.SEND,
                0,
                source.size,
            )
            response = await self._wait_for_response(
                transfer_id, self._accept_timeout
            )
            self._check_response(response, transfer_id, name, source.size)

            self._set_state(
                TransferState.SENDING,
                transfer_id,
                name,
                TransferDirection.SEND,
                0,
                source.size,
            )
            hasher = hashlib.sha256()
            offset = 0
            try:
                async for chunk in source.read_chunks(self._chunk_size):
                    if not isinstance(chunk, bytes) or not chunk:
                        raise TransferError("invalid_chunk", "empty or invalid chunk")
                    if offset + len(chunk) > source.size:
                        raise TransferError("size_mismatch", "source changed size")
                    hasher.update(chunk)
                    await self._link.send(
                        file_packet(
                            FILE_CHUNK,
                            {"transfer_id": transfer_id, "offset": offset},
                            chunk,
                        )
                    )
                    offset += len(chunk)
                    self._set_state(
                        TransferState.SENDING,
                        transfer_id,
                        name,
                        TransferDirection.SEND,
                        offset,
                        source.size,
                    )
                    if transfer_id in self._cancelled:
                        raise TransferError(
                            "cancelled", "peer cancelled the transfer"
                        )

                if offset != source.size:
                    raise TransferError("size_mismatch", "source changed size")

                await self._link.send(
                    file_packet(
                        FILE_COMPLETE,
                        {"transfer_id": transfer_id, "sha256": hasher.hexdigest()},
                    )
                )
                self._set_state(
                    TransferState.VERIFYING,
                    transfer_id,
                    name,
                    TransferDirection.SEND,
                    offset,
                    source.size,
                )
                result = await self._wait_for_response(
                    transfer_id, self._result_timeout
                )
                if result.type == FILE_CANCEL:
                    raise TransferError("cancelled", "peer cancelled the transfer")
                if result.type != FILE_RESULT or result.body.get("ok") is not True:
                    code = result.body.get("error", "transfer_failed")
                    raise TransferError(
                        code if isinstance(code, str) else "transfer_failed"
                    )

                self._set_state(
                    TransferState.COMPLETED,
                    transfer_id,
                    name,
                    TransferDirection.SEND,
                    source.size,
                    source.size,
                )
                return self._progress_or_raise()
            except asyncio.CancelledError:
                await self._send_cancel(transfer_id, "cancelled")
                self._set_state(
                    TransferState.CANCELLED,
                    transfer_id,
                    name,
                    TransferDirection.SEND,
                    offset,
                    source.size,
                )
                raise
            except TransferError as exc:
                await self._send_cancel(transfer_id, exc.code)
                self._set_state(
                    TransferState.FAILED,
                    transfer_id,
                    name,
                    TransferDirection.SEND,
                    offset,
                    source.size,
                )
                raise
            except Exception as exc:
                await self._send_cancel(transfer_id, "transfer_failed")
                self._set_state(
                    TransferState.FAILED,
                    transfer_id,
                    name,
                    TransferDirection.SEND,
                    offset,
                    source.size,
                )
                raise TransferError("transfer_failed", str(exc)) from exc
            finally:
                self._pending.pop(transfer_id, None)
                self._cancelled.discard(transfer_id)

    async def handle_packet(self, packet: Packet) -> bool:
        if packet.type in (FILE_ACCEPT, FILE_REJECT, FILE_RESULT):
            return self._resolve_response(packet)
        if packet.type == FILE_OFFER:
            await self._handle_offer(packet)
            return True
        if packet.type == FILE_CHUNK:
            await self._handle_chunk(packet)
            return True
        if packet.type == FILE_COMPLETE:
            await self._handle_complete(packet)
            return True
        if packet.type == FILE_CANCEL:
            self._resolve_response(packet)
            await self._handle_cancel(packet)
            return True
        return False

    async def close(self) -> None:
        for transfer_id in list(self._incoming):
            await self._abort_incoming(transfer_id, "closed")
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionError("file link closed"))
        self._pending.clear()
        self._cancelled.clear()
        await self._link.close()

    def _check_response(
        self, response: Packet, transfer_id: str, name: str, size: int
    ) -> None:
        if response.type == FILE_ACCEPT:
            return
        if response.type == FILE_REJECT:
            self._set_state(
                TransferState.FAILED,
                transfer_id,
                name,
                TransferDirection.SEND,
                0,
                size,
            )
            reason = response.body.get("reason", "rejected")
            raise TransferError(str(reason))
        if response.type == FILE_CANCEL:
            self._set_state(
                TransferState.CANCELLED,
                transfer_id,
                name,
                TransferDirection.SEND,
                0,
                size,
            )
            raise TransferError("cancelled")
        raise TransferError("protocol_error", "unexpected file response")

    async def _wait_for_response(
        self, transfer_id: str, timeout: float
    ) -> Packet:
        if transfer_id in self._pending:
            raise TransferError("busy", "a response is already pending")
        future: asyncio.Future[Packet] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[transfer_id] = future
        try:
            return await asyncio.wait_for(future, timeout)
        except TimeoutError as exc:
            self._pending.pop(transfer_id, None)
            raise TransferError("timeout", "peer did not respond") from exc
        except asyncio.CancelledError:
            self._pending.pop(transfer_id, None)
            raise

    def _resolve_response(self, packet: Packet) -> bool:
        transfer_id = packet.body.get("transfer_id")
        if not isinstance(transfer_id, str):
            return False
        future = self._pending.pop(transfer_id, None)
        if future is None or future.done():
            return False
        future.set_result(packet)
        return True

    async def _handle_offer(self, packet: Packet) -> None:
        transfer_id = packet.body.get("transfer_id")
        name = packet.body.get("name")
        size = packet.body.get("size")

        if self._lock.locked() or self._incoming:
            await self._send_reject(transfer_id, "busy")
            return
        if (
            not isinstance(transfer_id, str)
            or not transfer_id
            or not isinstance(name, str)
            or not name
            or not _is_int(size)
            or size < 0
        ):
            await self._send_reject(transfer_id, "invalid_offer")
            return
        if size > self._max_bytes:
            await self._send_reject(transfer_id, "file_too_large")
            return

        try:
            sink = await self._sink_factory.create(name, size)
        except ValueError:
            await self._send_reject(transfer_id, "invalid_name")
            return
        except OSError:
            await self._send_reject(transfer_id, "storage_error")
            return

        self._incoming[transfer_id] = _Incoming(sink, name, size)
        self._set_state(
            TransferState.RECEIVING,
            transfer_id,
            name,
            TransferDirection.RECEIVE,
            0,
            size,
        )
        await self._link.send(
            file_packet(FILE_ACCEPT, {"transfer_id": transfer_id, "offset": 0})
        )

    async def _handle_chunk(self, packet: Packet) -> None:
        transfer_id = packet.body.get("transfer_id")
        incoming = self._incoming.get(transfer_id) if isinstance(transfer_id, str) else None
        if incoming is None:
            await self._send_cancel(transfer_id, "unknown_transfer")
            return

        offset = packet.body.get("offset")
        if not _is_int(offset) or offset != incoming.received:
            await self._abort_incoming(transfer_id, "invalid_offset")
            return
        if not packet.payload:
            await self._abort_incoming(transfer_id, "empty_chunk")
            return
        if incoming.received + len(packet.payload) > incoming.size:
            await self._abort_incoming(transfer_id, "size_mismatch")
            return

        try:
            await incoming.sink.write(packet.payload)
        except OSError:
            await self._abort_incoming(transfer_id, "storage_error", result=True)
            return

        incoming.hasher.update(packet.payload)
        incoming.received += len(packet.payload)
        self._set_state(
            TransferState.RECEIVING,
            transfer_id,
            incoming.name,
            TransferDirection.RECEIVE,
            incoming.received,
            incoming.size,
        )

    async def _handle_complete(self, packet: Packet) -> None:
        transfer_id = packet.body.get("transfer_id")
        incoming = self._incoming.get(transfer_id) if isinstance(transfer_id, str) else None
        if incoming is None:
            await self._send_cancel(transfer_id, "unknown_transfer")
            return

        expected = packet.body.get("sha256")
        digest = incoming.hasher.hexdigest()
        if incoming.received != incoming.size:
            await self._abort_incoming(transfer_id, "size_mismatch", result=True)
            return
        if not isinstance(expected, str) or expected.lower() != digest:
            await self._abort_incoming(transfer_id, "hash_mismatch", result=True)
            return

        try:
            await incoming.sink.finish(digest)
        except OSError:
            await self._abort_incoming(transfer_id, "storage_error", result=True)
            return

        del self._incoming[transfer_id]
        self._set_state(
            TransferState.COMPLETED,
            transfer_id,
            incoming.name,
            TransferDirection.RECEIVE,
            incoming.size,
            incoming.size,
        )
        await self._link.send(
            file_packet(FILE_RESULT, {"transfer_id": transfer_id, "ok": True})
        )

    async def _handle_cancel(self, packet: Packet) -> None:
        transfer_id = packet.body.get("transfer_id")
        if not isinstance(transfer_id, str):
            return
        self._cancelled.add(transfer_id)
        incoming = self._incoming.pop(transfer_id, None)
        if incoming is None:
            return
        try:
            await incoming.sink.abort()
        except OSError:
            pass
        self._set_state(
            TransferState.CANCELLED,
            transfer_id,
            incoming.name,
            TransferDirection.RECEIVE,
            incoming.received,
            incoming.size,
        )

    async def _abort_incoming(
        self, transfer_id: str, reason: str, *, result: bool = False
    ) -> None:
        incoming = self._incoming.pop(transfer_id, None)
        if incoming is None:
            return
        try:
            await incoming.sink.abort()
        except OSError:
            pass
        self._set_state(
            TransferState.FAILED,
            transfer_id,
            incoming.name,
            TransferDirection.RECEIVE,
            incoming.received,
            incoming.size,
        )
        if result:
            await self._link.send(
                file_packet(
                    FILE_RESULT,
                    {"transfer_id": transfer_id, "ok": False, "error": reason},
                )
            )
        else:
            await self._send_cancel(transfer_id, reason)

    async def _send_reject(self, transfer_id: object, reason: str) -> None:
        if isinstance(transfer_id, str) and transfer_id:
            await self._link.send(
                file_packet(
                    FILE_REJECT,
                    {"transfer_id": transfer_id, "reason": reason},
                )
            )

    async def _send_cancel(self, transfer_id: object, reason: str) -> None:
        if not isinstance(transfer_id, str) or not transfer_id:
            return
        try:
            await self._link.send(
                file_packet(
                    FILE_CANCEL,
                    {"transfer_id": transfer_id, "reason": reason},
                )
            )
        except Exception:
            pass

    def _set_state(
        self,
        state: TransferState,
        transfer_id: str,
        name: str,
        direction: TransferDirection,
        transferred: int,
        total: int,
    ) -> None:
        self._state = state
        self._progress = TransferProgress(
            transfer_id, name, direction, transferred, total, state
        )
        if self._on_progress is not None:
            self._on_progress(self._progress)

    def _progress_or_raise(self) -> TransferProgress:
        if self._progress is None:
            raise TransferError("protocol_error", "transfer has no progress")
        return self._progress
