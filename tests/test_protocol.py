import asyncio
import json

import pytest

from bleconnect.protocol import (
    MAX_PAYLOAD_SIZE,
    Packet,
    ProtocolError,
    decode_packet,
    encode_packet,
    read_packet,
)


def test_round_trip_with_payload() -> None:
    packet = Packet("file_chunk", {"transfer_id": "abc", "offset": 0}, b"data")
    assert decode_packet(encode_packet(packet)) == packet


def test_round_trip_with_id() -> None:
    packet = Packet("ping", {"ts": 1}, id="request-1")
    assert decode_packet(encode_packet(packet)) == packet


def test_read_packet_from_stream() -> None:
    async def scenario() -> None:
        reader = asyncio.StreamReader()
        reader.feed_data(encode_packet(Packet("ping", {})))
        reader.feed_eof()
        assert await read_packet(reader) == Packet("ping", {})

    asyncio.run(scenario())


def test_rejects_oversized_payload() -> None:
    with pytest.raises(ProtocolError):
        encode_packet(Packet("file_chunk", {}, b"x" * (MAX_PAYLOAD_SIZE + 1)))


def test_rejects_unsupported_version() -> None:
    header = json.dumps({"version": 99, "type": "ping", "body": {}}).encode()
    frame = len(header).to_bytes(4, "big") + header + (0).to_bytes(4, "big")
    with pytest.raises(ProtocolError):
        decode_packet(frame)


def test_rejects_trailing_bytes() -> None:
    with pytest.raises(ProtocolError):
        decode_packet(encode_packet(Packet("ping", {})) + b"x")


def test_rejects_empty_type() -> None:
    with pytest.raises(ProtocolError):
        Packet("")


def test_rejects_short_frame() -> None:
    with pytest.raises(ProtocolError):
        decode_packet(b"\x00")
