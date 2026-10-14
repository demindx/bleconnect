"""Injectable Linux clipboard backends for Wayland and X11 sessions."""

from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Protocol

from ...application.ports import ClipboardPort, ClipboardSnapshot


class ClipboardUnavailableError(RuntimeError):
    """Raised when no configured clipboard provider is available."""


async def _run_command(
    command: Sequence[str], input_bytes: bytes | None = None
) -> tuple[int, bytes, bytes]:
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if input_bytes is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise ClipboardUnavailableError(f"could not run {command[0]}: {exc}") from exc
    stdout, stderr = await process.communicate(input_bytes)
    return process.returncode or 0, stdout, stderr


CommandRunner = Callable[
    [Sequence[str], bytes | None], Awaitable[tuple[int, bytes, bytes]]
]
SensitiveDetector = Callable[[str], bool]


class ClipboardProvider(Protocol):
    """Create a clipboard port when this backend is available in the session."""

    def create(self, env: Mapping[str, str]) -> ClipboardPort | None:
        """Return an adapter for this session, or None when unsupported."""


class CommandClipboard:
    """ClipboardPort driven by commands supplied by a backend provider."""

    def __init__(
        self,
        read_command: Sequence[str],
        write_command: Sequence[str],
        types_command: Sequence[str] = (),
        command_runner: CommandRunner = _run_command,
        sensitive_detector: SensitiveDetector | None = None,
    ) -> None:
        self._read_command = tuple(read_command)
        self._write_command = tuple(write_command)
        self._types_command = tuple(types_command)
        self._command_runner = command_runner
        self._sensitive_detector = sensitive_detector or (lambda _text: False)

    async def read_text(self) -> ClipboardSnapshot | None:
        if self._types_command:
            status, types, _ = await self._command_runner(self._types_command, None)
            if status == 0 and b"x-kde-passwordManagerHint" in types:
                return ClipboardSnapshot("", sensitive=True)
        status, stdout, _ = await self._command_runner(self._read_command, None)
        if status:
            return None
        try:
            text = stdout.decode("utf-8")
            return ClipboardSnapshot(text, sensitive=self._sensitive_detector(text))
        except UnicodeDecodeError as exc:
            raise ClipboardUnavailableError(
                "clipboard contains text that is not valid UTF-8"
            ) from exc

    async def write_text(self, text: str) -> None:
        status, _, stderr = await self._command_runner(
            self._write_command, text.encode("utf-8")
        )
        if status:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise ClipboardUnavailableError(
                f"clipboard write failed{': ' + detail if detail else ''}"
            )


class WaylandClipboardProvider:
    """Build a command adapter when wl-clipboard and a Wayland session exist."""

    def __init__(
        self,
        command_runner: CommandRunner = _run_command,
        sensitive_detector: SensitiveDetector | None = None,
    ) -> None:
        self._command_runner = command_runner
        self._sensitive_detector = sensitive_detector

    def create(self, env: Mapping[str, str]) -> ClipboardPort | None:
        if not env.get("WAYLAND_DISPLAY"):
            return None
        copy = shutil.which("wl-copy")
        paste = shutil.which("wl-paste")
        if not copy or not paste:
            return None
        return CommandClipboard(
            read_command=(paste, "--no-newline", "--type", "text/plain"),
            write_command=(copy, "--type", "text/plain;charset=utf-8"),
            types_command=(paste, "--list-types"),
            command_runner=self._command_runner,
            sensitive_detector=self._sensitive_detector,
        )


class XclipClipboardProvider:
    """Build a command adapter when xclip and an X11 session exist."""

    def __init__(
        self,
        command_runner: CommandRunner = _run_command,
        sensitive_detector: SensitiveDetector | None = None,
    ) -> None:
        self._command_runner = command_runner
        self._sensitive_detector = sensitive_detector

    def create(self, env: Mapping[str, str]) -> ClipboardPort | None:
        if not env.get("DISPLAY"):
            return None
        xclip = shutil.which("xclip")
        if not xclip:
            return None
        return CommandClipboard(
            read_command=(xclip, "-selection", "clipboard", "-o", "-target", "UTF8_STRING"),
            write_command=(xclip, "-selection", "clipboard", "-i", "-target", "UTF8_STRING"),
            types_command=(xclip, "-selection", "clipboard", "-o", "-target", "TARGETS"),
            command_runner=self._command_runner,
            sensitive_detector=self._sensitive_detector,
        )


def resolve_linux_clipboard(
    providers: Sequence[ClipboardProvider],
    env: Mapping[str, str] | None = None,
) -> ClipboardPort:
    """Select and create the first available injected clipboard provider.

    The caller controls provider order and can supply its own implementations.
    The usual Linux composition passes Wayland before X11 for XWayland sessions.
    """
    environment = os.environ if env is None else env
    for provider in providers:
        clipboard = provider.create(environment)
        if clipboard is not None:
            return clipboard
    if environment.get("WAYLAND_DISPLAY") or environment.get("DISPLAY"):
        raise ClipboardUnavailableError(
            "no configured clipboard provider is available for this graphical session"
        )
    raise ClipboardUnavailableError(
        "no graphical session detected (WAYLAND_DISPLAY or DISPLAY is unset)"
    )
