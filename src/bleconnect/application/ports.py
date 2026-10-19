"""Interfaces shared by application services and platform adapters."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from ..protocol import Packet


class PacketLink(Protocol):
    """Bidirectional packet link owned by a transport adapter."""

    async def send(self, packet: Packet) -> None:
        """Send one packet to the peer."""

    async def receive(self) -> Packet:
        """Receive the next packet from the peer."""

    async def close(self) -> None:
        """Close the link and release transport resources."""


@dataclass(frozen=True)
class ClipboardSnapshot:
    """Text read from a clipboard with an optional sensitivity flag."""

    text: str
    sensitive: bool = False


class ClipboardPort(Protocol):
    async def read_text(self) -> ClipboardSnapshot | None:
        """Read current clipboard text, or return None when unavailable."""

    async def write_text(self, text: str) -> None:
        """Replace clipboard contents with text from a peer."""


class ClipboardWatcher(Protocol):
    def changes(self) -> AsyncIterator[ClipboardSnapshot]:
        """Yield clipboard snapshots as they change."""


@dataclass(frozen=True)
class PeerInfo:
    """A peer discovered over BLE."""

    address: str
    name: str


class PresencePort(Protocol):
    async def start(self) -> None:
        """Start advertising or scanning for the peer."""

    async def stop(self) -> None:
        """Stop presence work and release resources."""

    async def wait_for_peer(self, timeout: float) -> PeerInfo | None:
        """Wait for a trusted peer to become available."""


class FileSource(Protocol):
    @property
    def name(self) -> str:
        """File name shown to the peer."""

    @property
    def size(self) -> int:
        """File size in bytes."""

    def read_chunks(self, chunk_size: int) -> AsyncIterator[bytes]:
        """Yield the file contents in bounded chunks."""


class FileSink(Protocol):
    async def write(self, data: bytes) -> None:
        """Append bytes to the destination."""

    async def finish(self, sha256: str) -> None:
        """Publish the received file after verification."""

    async def abort(self) -> None:
        """Remove the partial destination."""


class FileSinkFactory(Protocol):
    async def create(self, name: str, size: int) -> FileSink:
        """Create a sink for an incoming file."""


class SoundPlayer(Protocol):
    async def play_find_phone(self, duration_s: float, volume: float) -> None:
        """Play the find-phone sound."""

    async def stop(self) -> None:
        """Stop the find-phone sound."""


@dataclass(frozen=True)
class BluetoothDevice:
    """A Bluetooth peer discovered by the platform adapter."""

    address: str
    name: str
    paired: bool = False


@dataclass(frozen=True)
class TrustedDevice:
    """A peer that the user paired and approved in the operating system."""

    address: str
    name: str


class BluetoothPairingPort(Protocol):
    async def discover(self, timeout: float = 10.0) -> Sequence[BluetoothDevice]:
        """Find nearby peers without pairing them."""

    async def pair(self, address: str) -> BluetoothDevice:
        """Ask the platform to pair; the OS may show its own confirmation UI."""


class TrustedDevicesRepository(Protocol):
    async def list_trusted(self) -> Sequence[TrustedDevice]:
        """Return devices approved by the user."""

    async def save_trusted(self, device: TrustedDevice) -> None:
        """Persist a successfully paired device."""

    async def remove_trusted(self, address: str) -> None:
        """Forget a trusted device."""
