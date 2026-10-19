"""Shared composition logic used by platform builders."""

from __future__ import annotations

from ..application.clipboard_service import ClipboardService
from ..application.file_transfer_service import FileTransferService
from ..application.pairing_service import PairingService
from ..application.ports import ClipboardPort, ClipboardWatcher, PacketLink
from ..presentation.app_controller import AppController


def build_app(
    *,
    control_link: PacketLink,
    clipboard: ClipboardPort,
    files: FileTransferService | None = None,
    pairing: PairingService | None = None,
    watcher: ClipboardWatcher | None = None,
) -> AppController:
    """Assemble the core application from injected platform adapters."""
    clipboard_service = ClipboardService(clipboard, control_link)
    return AppController(
        control_link,
        clipboard_service,
        files=files,
        pairing=pairing,
        watcher=watcher,
    )
