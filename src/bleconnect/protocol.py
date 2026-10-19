"""Shared packet model and RFCOMM v2 framing."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

PROTOCOL_VERSION = 2
MAX_HEADER_SIZE = 64 * 1024
MAX_PAYLOAD_SIZE = 1024 * 1024


class ProtocolError(ValueError):
    """Raised when a packet or frame is malformed or unsupported."""


@dataclass(frozen=True)
class Packet:
    """One application message with an optional binary payload."""

    type: str
    body: dict[str, Any] = field(default_factory=dict)
    payload: bytes = b""
    id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.type, str) or not self.type:
            raise ProtocolError("packet type must be a non-empty string")
        if not isinstance(self.body, dict):
            raise ProtocolError("packet body must be an object")
        if not isinstance(self.payload, bytes):
            raise ProtocolError("packet payload must be bytes")
        if self.id is not None and (not isinstance(self.id, str) or not self.id):
            raise ProtocolError("packet id must be a non-empty string")

    def header(self) -> dict[str, Any]:
        header: dict[str, Any] = {
            "version": PROTOCOL_VERSION,
            "type": self.type,
            "body": self.body,
        }
        if self.id is not None:
            header["id"] = self.id
        return header


def encode_packet(packet: Packet) -> bytes:
    """Encode one RFCOMM v2 frame."""
    try:
        header_bytes = json.dumps(
            packet.header(), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError("packet is not JSON serializable") from exc

    if not header_bytes or len(header_bytes) > MAX_HEADER_SIZE:
        raise ProtocolError("header size is outside the allowed range")
    if len(packet.payload) > MAX_PAYLOAD_SIZE:
        raise ProtocolError("payload size is outside the allowed range")

    return (
        len(header_bytes).to_bytes(4, "big")
        + header_bytes
        + len(packet.payload).to_bytes(4, "big")
        + packet.payload
    )


async def read_packet(reader: asyncio.StreamReader) -> Packet:
    """Read one RFCOMM v2 frame from an async stream."""
    header_size = int.from_bytes(await reader.readexactly(4), "big")
    if header_size == 0 or header_size > MAX_HEADER_SIZE:
        raise ProtocolError(f"invalid header size: {header_size}")

    header_bytes = await reader.readexactly(header_size)
    payload_size = int.from_bytes(await reader.readexactly(4), "big")
    if payload_size > MAX_PAYLOAD_SIZE:
        raise ProtocolError(f"invalid payload size: {payload_size}")

    payload = await reader.readexactly(payload_size)
    return _parse_packet(header_bytes, payload)


def decode_packet(data: bytes) -> Packet:
    """Decode exactly one complete RFCOMM v2 frame."""
    if len(data) < 8:
        raise ProtocolError("frame is too short")

    header_size = int.from_bytes(data[:4], "big")
    if header_size == 0 or header_size > MAX_HEADER_SIZE:
        raise ProtocolError(f"invalid header size: {header_size}")

    header_end = 4 + header_size
    if len(data) < header_end + 4:
        raise ProtocolError("frame is too short")

    payload_size = int.from_bytes(data[header_end : header_end + 4], "big")
    if payload_size > MAX_PAYLOAD_SIZE:
        raise ProtocolError(f"invalid payload size: {payload_size}")

    payload_start = header_end + 4
    payload_end = payload_start + payload_size
    if len(data) != payload_end:
        raise ProtocolError("frame has trailing or missing bytes")

    return _parse_packet(data[4:header_end], data[payload_start:payload_end])


def _parse_packet(header_bytes: bytes, payload: bytes) -> Packet:
    try:
        header = json.loads(header_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("header is not valid UTF-8 JSON") from exc

    if not isinstance(header, dict):
        raise ProtocolError("header must be a JSON object")
    version = header.get("version")
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version != PROTOCOL_VERSION
    ):
        raise ProtocolError("unsupported protocol version")

    packet_type = header.get("type")
    body = header.get("body", {})
    packet_id = header.get("id")
    if not isinstance(packet_type, str) or not packet_type:
        raise ProtocolError("packet type must be a non-empty string")
    if not isinstance(body, dict):
        raise ProtocolError("packet body must be an object")
    if packet_id is not None and (not isinstance(packet_id, str) or not packet_id):
        raise ProtocolError("packet id must be a non-empty string")

    return Packet(packet_type, body, payload, packet_id)
