"""Linux composition root."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ..adapters.filesystem.file_sink import LocalFileSinkFactory
from ..adapters.linux.ble_central import BleCentralLink, connect_ble_service
from ..adapters.linux.bluez_pairing import BluezPairingAdapter
from ..adapters.linux.clipboard import (
    WaylandClipboardProvider,
    XclipClipboardProvider,
    resolve_linux_clipboard,
    resolve_linux_clipboard_watcher,
)
from ..adapters.linux.trusted_devices import JsonTrustedDevicesRepository
from ..application.file_transfer_service import FileTransferService
from ..application.pairing_service import PairingService
from ..application.ports import ClipboardPort, ClipboardWatcher, PacketLink
from ..presentation.app_controller import AppController
from .common import build_app


def build_linux_clipboard(
    env: Mapping[str, str] | None = None,
) -> ClipboardPort:
    """Create the first clipboard backend available in this session."""
    return resolve_linux_clipboard(
        [WaylandClipboardProvider(), XclipClipboardProvider()], env
    )


def build_linux_clipboard_watcher(
    clipboard: ClipboardPort, env: Mapping[str, str] | None = None
) -> ClipboardWatcher:
    """Use wl-paste events on Wayland and polling elsewhere."""
    return resolve_linux_clipboard_watcher(clipboard, env)


def build_linux_trusted_devices(
    path: str | Path | None = None,
) -> JsonTrustedDevicesRepository:
    return JsonTrustedDevicesRepository(path)


def build_linux_pairing_service(
    trusted_devices: JsonTrustedDevicesRepository | None = None,
) -> PairingService:
    repository = trusted_devices or build_linux_trusted_devices()
    return PairingService(BluezPairingAdapter(), repository)


def build_linux_file_sink_factory(
    root: str | Path | None = None,
) -> LocalFileSinkFactory:
    destination = Path(root) if root is not None else Path.home() / "Downloads" / "bleconnect"
    return LocalFileSinkFactory(destination)


async def connect_linux_ble(
    *,
    address: str | None = None,
    timeout: float = 10.0,
    pair: bool = False,
    connect_timeout: float = 30.0,
    attempts: int = 2,
) -> BleCentralLink:
    """Scan for and connect to the Android BLE peripheral."""
    return await connect_ble_service(
        address=address,
        timeout=timeout,
        pair=pair,
        connect_timeout=connect_timeout,
        attempts=attempts,
    )


def build_linux_app(
    *,
    control_link: PacketLink,
    clipboard: ClipboardPort,
    files: FileTransferService | None = None,
    pairing: PairingService | None = None,
    watcher: ClipboardWatcher | None = None,
) -> AppController:
    """Build the Linux application with concrete Bluetooth and clipboard adapters."""
    return build_app(
        control_link=control_link,
        clipboard=clipboard,
        files=files,
        pairing=pairing,
        watcher=watcher,
    )
