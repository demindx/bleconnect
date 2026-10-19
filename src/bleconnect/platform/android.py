"""Android composition root."""

from __future__ import annotations

from ..application.file_transfer_service import FileTransferService
from ..application.pairing_service import PairingService
from ..application.ports import ClipboardPort, ClipboardWatcher, PacketLink
from ..presentation.app_controller import AppController
from .common import build_app


def build_android_app(
    *,
    control_link: PacketLink,
    clipboard: ClipboardPort,
    files: FileTransferService | None = None,
    pairing: PairingService | None = None,
    watcher: ClipboardWatcher | None = None,
) -> AppController:
    """Build the Android application with bridge-backed adapters."""
    return build_app(
        control_link=control_link,
        clipboard=clipboard,
        files=files,
        pairing=pairing,
        watcher=watcher,
    )
