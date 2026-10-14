"""Length-prefixed JSON protocol shared by the Android app and Linux service."""

from __future__ import annotations

import asyncio
import json
from typing import Any

PROTOCOL_VERSION = 1
MAX_FRAME_SIZE = 1024 * 1024


class ProtocolError(ValueError):
    """Raised when a peer sends an invalid or unsupported frame."""


def encode_packet(packet: dict[str, Any]) -> bytes:
    """Encode one JSON packet with a four-byte big-endian size prefix."""
    try:
        payload = json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    except (TypeError, ValueError) as exc:
        raise ProtocolError("packet is not JSON serializable") from exc

    if not payload or len(payload) > MAX_FRAME_SIZE:
        raise ProtocolError("packet size is outside the allowed range")
    return len(payload).to_bytes(4, "big") + payload


async def read_packet(reader: asyncio.StreamReader) -> dict[str, Any]:
    """Read and validate one framed JSON packet from an async stream."""
    header = await reader.readexactly(4)
    size = int.from_bytes(header, "big")
    if size == 0 or size > MAX_FRAME_SIZE:
        raise ProtocolError(f"invalid frame size: {size}")

    payload = await reader.readexactly(size)
    try:
        packet_data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("frame does not contain valid UTF-8 JSON") from exc

    if not isinstance(packet_data, dict):
        raise ProtocolError("packet must be a JSON object")
    version = packet_data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol version")
    if not isinstance(packet_data.get("type"), str):
        raise ProtocolError("packet type must be a string")
    if not isinstance(packet_data.get("body", {}), dict):
        raise ProtocolError("packet body must be a JSON object")
    return packet_data


def packet(packet_type: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a versioned protocol packet."""
    return {"version": PROTOCOL_VERSION, "type": packet_type, "body": body or {}}
