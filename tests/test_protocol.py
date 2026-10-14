import asyncio
import json

import pytest

from bleconnect.protocol import (
    MAX_FRAME_SIZE,
    PROTOCOL_VERSION,
    ProtocolError,
    encode_packet,
    packet,
    read_packet,
)


def _read(data: bytes) -> dict[str, object]:
    loop = asyncio.new_event_loop()
    try:
        reader = asyncio.StreamReader(loop=loop)
        reader.feed_data(data)
        reader.feed_eof()
        return loop.run_until_complete(read_packet(reader))
    finally:
        loop.close()


def test_packet_round_trips_unicode_body() -> None:
    original = packet("clipboard", {"text": "Привет 🌍"})
    assert _read(encode_packet(original)) == original


@pytest.mark.parametrize("size", [0, MAX_FRAME_SIZE + 1])
def test_read_rejects_invalid_frame_size(size: int) -> None:
    with pytest.raises(ProtocolError, match="invalid frame size"):
        _read(size.to_bytes(4, "big"))


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"not json", "valid UTF-8 JSON"),
        (json.dumps({"version": 999, "type": "ping"}).encode(), "unsupported protocol version"),
        (json.dumps({"version": True, "type": "ping"}).encode(), "unsupported protocol version"),
        (json.dumps({"version": PROTOCOL_VERSION, "type": 1}).encode(), "packet type"),
        (json.dumps({"version": PROTOCOL_VERSION, "type": "ping", "body": []}).encode(), "packet body"),
        (json.dumps(["not", "an object"]).encode(), "JSON object"),
    ],
)
def test_read_rejects_invalid_packet(data: bytes, message: str) -> None:
    with pytest.raises(ProtocolError, match=message):
        _read(len(data).to_bytes(4, "big") + data)


def test_encode_rejects_non_json_packet() -> None:
    with pytest.raises(ProtocolError, match="not JSON serializable"):
        encode_packet({"value": object()})


def test_encode_rejects_packet_over_limit() -> None:
    with pytest.raises(ProtocolError, match="outside the allowed range"):
        encode_packet({"value": "x" * MAX_FRAME_SIZE})
