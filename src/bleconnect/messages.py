"""Shared message type names and packet helpers."""

from __future__ import annotations

from typing import Any

from .protocol import Packet

CLIPBOARD = "clipboard"
HELLO = "hello"
HELLO_ACK = "hello_ack"
PING = "ping"
PONG = "pong"
FIND_PHONE = "find_phone"
FIND_PHONE_STOP = "find_phone_stop"
FILE_INCOMING = "file_incoming"
FILE_ABORT = "file_abort"
ERROR = "error"

FILE_OFFER = "file_offer"
FILE_ACCEPT = "file_accept"
FILE_REJECT = "file_reject"
FILE_CHUNK = "file_chunk"
FILE_COMPLETE = "file_complete"
FILE_RESULT = "file_result"
FILE_CANCEL = "file_cancel"

CONTROL_TYPES = frozenset(
    {
        HELLO,
        HELLO_ACK,
        PING,
        PONG,
        FIND_PHONE,
        FIND_PHONE_STOP,
        FILE_INCOMING,
        FILE_ABORT,
        ERROR,
    }
)

FILE_TYPES = frozenset(
    {
        FILE_OFFER,
        FILE_ACCEPT,
        FILE_REJECT,
        FILE_CHUNK,
        FILE_COMPLETE,
        FILE_RESULT,
        FILE_CANCEL,
    }
)


def clipboard_packet(text: str) -> Packet:
    return Packet(CLIPBOARD, {"text": text})


def control_packet(packet_type: str, body: dict[str, Any] | None = None) -> Packet:
    if packet_type not in CONTROL_TYPES:
        raise ValueError(f"not a control message type: {packet_type}")
    return Packet(packet_type, body or {})


def file_packet(
    packet_type: str, body: dict[str, Any], payload: bytes = b""
) -> Packet:
    if packet_type not in FILE_TYPES:
        raise ValueError(f"not a file message type: {packet_type}")
    return Packet(packet_type, body, payload)


def is_control(packet_type: str) -> bool:
    return packet_type in CONTROL_TYPES


def is_file(packet_type: str) -> bool:
    return packet_type in FILE_TYPES
