import pytest

from bleconnect.ble_protocol import (
    FRAME_TYPE_CONTROL,
    MAX_CLIPBOARD_BYTES,
    BleFrame,
    MessageAssembler,
    chunk_size_for_mtu,
    decode_frame,
    encode_frame,
    encode_packet_chunks,
)
from bleconnect.protocol import Packet, ProtocolError


def test_frame_round_trip() -> None:
    frame = BleFrame(FRAME_TYPE_CONTROL, 7, 0, 1, b"{}")
    assert decode_frame(encode_frame(frame)) == frame


def test_chunk_size_for_mtu() -> None:
    assert chunk_size_for_mtu(23) == 10
    assert chunk_size_for_mtu(517) == 504
    assert chunk_size_for_mtu(1000) == 512


def test_clipboard_chunking_and_reassembly() -> None:
    assembler = MessageAssembler()
    packet = Packet("clipboard", {"text": "hello" * 20})
    frames = encode_packet_chunks(packet, 1, 23)

    results = [assembler.add(frame) for frame in frames]
    assert results[-1] == packet
    assert all(result is None for result in results[:-1])


def test_control_chunking_and_reassembly() -> None:
    assembler = MessageAssembler()
    packet = Packet("find_phone", {"duration_s": 30, "volume": 1.0})
    frames = encode_packet_chunks(packet, 2, 23)

    results = [assembler.add(frame) for frame in frames]
    assert results[-1] == packet


def test_duplicate_completed_message_is_ignored() -> None:
    assembler = MessageAssembler()
    packet = Packet("clipboard", {"text": "abcdefghijklmno"})
    frames = encode_packet_chunks(packet, 3, 23)
    assert len(frames) == 2

    assert assembler.add(frames[0]) is None
    assert assembler.add(frames[1]) == packet
    assert assembler.add(frames[0]) is None


def test_expire_incomplete_message() -> None:
    now = [0.0]
    assembler = MessageAssembler(timeout=10.0, clock=lambda: now[0])
    frame = BleFrame(FRAME_TYPE_CONTROL, 4, 0, 2, b"{}")

    assert assembler.add(frame) is None
    assert assembler.pending_count == 1
    now[0] = 11.0
    assert assembler.expire() == 1
    assert assembler.pending_count == 0


def test_rejects_oversized_clipboard() -> None:
    packet = Packet("clipboard", {"text": "x" * (MAX_CLIPBOARD_BYTES + 1)})
    with pytest.raises(ProtocolError):
        encode_packet_chunks(packet, 1, 517)


def test_rejects_binary_payload() -> None:
    packet = Packet("clipboard", {"text": "x"}, b"binary")
    with pytest.raises(ProtocolError):
        encode_packet_chunks(packet, 1, 517)
