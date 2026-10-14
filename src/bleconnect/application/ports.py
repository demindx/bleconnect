"""Interfaces shared by application services and transport adapters."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol


class DeviceLink(Protocol):
    """Bidirectional packet link to one paired device.

    Implementations own connection setup and teardown. Application services
    exchange versioned protocol packets without depending on Bluetooth APIs.
    """

    async def send(self, packet: dict[str, object]) -> None:
        """Send one protocol packet to the connected device."""

    async def receive(self) -> dict[str, object]:
        """Receive the next protocol packet from the connected device."""

    async def close(self) -> None:
        """Close the link and release its transport resources."""


@dataclass(frozen=True)
class ClipboardSnapshot:
    """Text read from a clipboard, with an optional platform sensitivity flag."""

    text: str
    sensitive: bool = False


class ClipboardPort(Protocol):
    async def read_text(self) -> ClipboardSnapshot | None:
        """Read current clipboard text, or return None when unavailable."""

    async def write_text(self, text: str) -> None:
        """Replace clipboard contents with text received from a peer."""


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


@dataclass(frozen=True)
class SharedFile:
    """A file entry exposed by a peer, with a root-relative POSIX path."""

    path: str
    size: int
    modified_ns: int
    is_directory: bool = False


class SharedFilesPort(Protocol):
    async def list_files(self, relative_path: str = "") -> Sequence[SharedFile]:
        """List files beneath the explicitly shared root."""

    async def read_file(self, relative_path: str) -> AsyncIterator[bytes]:
        """Stream a shared file in bounded chunks."""
