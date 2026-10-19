"""BLE GATT frame format, chunking, and reassembly."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .messages import CLIPBOARD, CONTROL_TYPES
from .protocol import Packet, ProtocolError

BLE_SERVICE_UUID = "d37b4a31-8e74-4f36-9a01-7d3a8f7c2b10"
BLE_INFO_CHARACTERISTIC_UUID = "d37b4a32-8e74-4f36-9a01-7d3a8f7c2b10"
BLE_CONTROL_CHARACTERISTIC_UUID = "d37b4a33-8e74-4f36-9a01-7d3a8f7c2b10"
BLE_CLIPBOARD_CHARACTERISTIC_UUID = "d37b4a34-8e74-4f36-9a01-7d3a8f7c2b10"

BLE_FRAME_VERSION = 1
FRAME_TYPE_CONTROL = 1
FRAME_TYPE_CLIPBOARD = 2
HEADER_SIZE = 10
MAX_CHUNK_PAYLOAD = 512
MAX_CONTROL_BYTES = 4 * 1024
MAX_CLIPBOARD_BYTES = 64 * 1024
DEFAULT_MTU = 23


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class BleFrame:
    """One value written to or notified from a GATT characteristic."""

    frame_type: int
    message_id: int
    chunk_index: int
    chunk_count: int
    payload: bytes = b""

    def __post_init__(self) -> None:
        if (
            not _is_int(self.frame_type)
            or self.frame_type not in (FRAME_TYPE_CONTROL, FRAME_TYPE_CLIPBOARD)
        ):
            raise ProtocolError("unsupported BLE frame type")
        if not _is_int(self.message_id) or not 0 <= self.message_id <= 0xFFFFFFFF:
            raise ProtocolError("message_id is outside uint32")
        if not _is_int(self.chunk_index) or not 0 <= self.chunk_index <= 0xFFFF:
            raise ProtocolError("chunk_index is outside uint16")
        if not _is_int(self.chunk_count) or not 1 <= self.chunk_count <= 0xFFFF:
            raise ProtocolError("chunk_count is outside uint16")
        if self.chunk_index >= self.chunk_count:
            raise ProtocolError("chunk_index must be below chunk_count")
        if not isinstance(self.payload, bytes):
            raise ProtocolError("frame payload must be bytes")
        if len(self.payload) > MAX_CHUNK_PAYLOAD:
            raise ProtocolError("frame payload is too large")


def encode_frame(frame: BleFrame) -> bytes:
    """Encode one complete BLE characteristic value."""
    return (
        bytes((BLE_FRAME_VERSION, frame.frame_type))
        + frame.message_id.to_bytes(4, "big")
        + frame.chunk_index.to_bytes(2, "big")
        + frame.chunk_count.to_bytes(2, "big")
        + frame.payload
    )


def decode_frame(data: bytes) -> BleFrame:
    """Decode one complete BLE characteristic value."""
    if len(data) < HEADER_SIZE:
        raise ProtocolError("BLE frame is too short")
    if data[0] != BLE_FRAME_VERSION:
        raise ProtocolError("unsupported BLE frame version")
    if len(data) - HEADER_SIZE > MAX_CHUNK_PAYLOAD:
        raise ProtocolError("BLE frame payload is too large")

    return BleFrame(
        frame_type=data[1],
        message_id=int.from_bytes(data[2:6], "big"),
        chunk_index=int.from_bytes(data[6:8], "big"),
        chunk_count=int.from_bytes(data[8:10], "big"),
        payload=data[HEADER_SIZE:],
    )


def chunk_size_for_mtu(mtu: int) -> int:
    """Return the payload size that fits one ATT write for the given MTU."""
    return max(1, min(MAX_CHUNK_PAYLOAD, mtu - 3 - HEADER_SIZE))


def encode_packet_chunks(packet: Packet, message_id: int, mtu: int) -> list[BleFrame]:
    """Split a control or clipboard packet into BLE frames."""
    if packet.payload:
        raise ProtocolError("BLE framing does not carry binary payloads")

    if packet.type == CLIPBOARD:
        text = packet.body.get("text")
        if not isinstance(text, str):
            raise ProtocolError("clipboard packet must contain text")
        data = text.encode("utf-8")
        if len(data) > MAX_CLIPBOARD_BYTES:
            raise ProtocolError("clipboard text is too large")
        frame_type = FRAME_TYPE_CLIPBOARD
    else:
        if packet.type not in CONTROL_TYPES:
            raise ProtocolError(f"unsupported BLE message type: {packet.type}")
        try:
            data = json.dumps(
                {"type": packet.type, "body": packet.body},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ProtocolError("control packet is not JSON serializable") from exc
        if len(data) > MAX_CONTROL_BYTES:
            raise ProtocolError("control packet is too large")
        frame_type = FRAME_TYPE_CONTROL

    chunk_size = chunk_size_for_mtu(mtu)
    chunks = [data[index : index + chunk_size] for index in range(0, len(data), chunk_size)]
    if not chunks:
        chunks = [b""]
    if len(chunks) > 0xFFFF:
        raise ProtocolError("message needs too many BLE chunks")

    return [
        BleFrame(frame_type, message_id, index, len(chunks), chunk)
        for index, chunk in enumerate(chunks)
    ]


@dataclass
class _PendingMessage:
    frame_type: int
    chunk_count: int
    started_at: float
    parts: dict[int, bytes] = field(default_factory=dict)


class MessageAssembler:
    """Reassemble BLE frames into packets and suppress duplicate messages."""

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        max_pending: int = 4,
        dedupe_window: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if timeout <= 0 or max_pending <= 0 or dedupe_window < 0:
            raise ValueError("assembler limits must be positive")
        self._timeout = timeout
        self._max_pending = max_pending
        self._dedupe_window = dedupe_window
        self._clock = clock
        self._pending: dict[int, _PendingMessage] = {}
        self._completed: dict[int, float] = {}

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def add(self, frame: BleFrame) -> Packet | None:
        """Add one frame and return a packet once all chunks are present."""
        now = self._clock()
        self._prune_completed(now)

        if frame.message_id in self._completed:
            return None

        pending = self._pending.get(frame.message_id)
        if pending is None:
            if len(self._pending) >= self._max_pending:
                oldest_id = min(
                    self._pending, key=lambda key: self._pending[key].started_at
                )
                del self._pending[oldest_id]
            pending = _PendingMessage(frame.frame_type, frame.chunk_count, now)
            self._pending[frame.message_id] = pending
        elif (
            pending.frame_type != frame.frame_type
            or pending.chunk_count != frame.chunk_count
        ):
            del self._pending[frame.message_id]
            raise ProtocolError("inconsistent BLE chunk metadata")

        pending.parts[frame.chunk_index] = frame.payload
        if len(pending.parts) != pending.chunk_count:
            return None

        try:
            data = b"".join(
                pending.parts[index] for index in range(pending.chunk_count)
            )
        except KeyError as exc:
            raise ProtocolError("BLE message is missing a chunk") from exc

        del self._pending[frame.message_id]
        self._completed[frame.message_id] = now
        return _decode_message(frame.frame_type, data)

    def expire(self, now: float | None = None) -> int:
        """Drop incomplete messages older than the timeout."""
        current = self._clock() if now is None else now
        expired = [
            message_id
            for message_id, pending in self._pending.items()
            if current - pending.started_at > self._timeout
        ]
        for message_id in expired:
            del self._pending[message_id]
        self._prune_completed(current)
        return len(expired)

    def _prune_completed(self, now: float) -> None:
        if self._dedupe_window == 0:
            self._completed.clear()
            return
        stale = [
            message_id
            for message_id, completed_at in self._completed.items()
            if now - completed_at > self._dedupe_window
        ]
        for message_id in stale:
            del self._completed[message_id]


def _decode_message(frame_type: int, data: bytes) -> Packet:
    if frame_type == FRAME_TYPE_CLIPBOARD:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("clipboard payload is not valid UTF-8") from exc
        return Packet(CLIPBOARD, {"text": text})

    if frame_type == FRAME_TYPE_CONTROL:
        try:
            message = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtocolError("control payload is not valid UTF-8 JSON") from exc
        if not isinstance(message, dict):
            raise ProtocolError("control payload must be a JSON object")
        packet_type = message.get("type")
        body = message.get("body", {})
        if not isinstance(packet_type, str) or packet_type not in CONTROL_TYPES:
            raise ProtocolError("unsupported control message type")
        if not isinstance(body, dict):
            raise ProtocolError("control message body must be an object")
        return Packet(packet_type, body)

    raise ProtocolError("unsupported BLE frame type")
