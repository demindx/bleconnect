"""BLEConnect Android foreground service.

The service owns the BLE peripheral, clipboard writes, find-phone playback, and
the local control server used by the Kivy UI. Protocol framing and application
behavior stay in the shared ``bleconnect`` package.
"""

from __future__ import annotations

import asyncio
import time
import traceback
from pathlib import Path

from jnius import autoclass

from bleconnect.adapters.android.ble_peripheral import (
    BlePeripheralLink,
    create_pyjnius_transport,
)
from bleconnect.adapters.android.clipboard import AndroidClipboard
from bleconnect.adapters.android.control import ControlServer
from bleconnect.adapters.android.sound import AndroidSoundPlayer
from bleconnect.application.clipboard_service import ClipboardService
from bleconnect.application.ports import ClipboardSnapshot
from bleconnect.application.session import PacketDispatcher
from bleconnect.messages import (
    CLIPBOARD,
    ERROR,
    FILE_INCOMING,
    FIND_PHONE,
    FIND_PHONE_STOP,
    PING,
    PONG,
    control_packet,
)

PythonService = autoclass("org.kivy.android.PythonService")
Context = autoclass("android.content.Context")
BuildVersion = autoclass("android.os.Build$VERSION")
NotificationBuilder = autoclass("android.app.Notification$Builder")
NotificationChannel = autoclass("android.app.NotificationChannel")
NotificationManager = autoclass("android.app.NotificationManager")

SERVICE = PythonService.mService
CHANNEL_ID = "bleconnect_service"


def _log_path() -> Path:
    directory = SERVICE.getExternalFilesDir(None)
    if directory is None:
        directory = SERVICE.getFilesDir()
    return Path(directory.getAbsolutePath()) / "service.log"


def log(message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n"
    try:
        with open(_log_path(), "a", encoding="utf-8") as target:
            target.write(line)
    except Exception:
        pass
    print(line, end="", flush=True)


def start_foreground() -> None:
    if BuildVersion.SDK_INT >= 26:
        manager = SERVICE.getSystemService(Context.NOTIFICATION_SERVICE)
        channel = NotificationChannel(
            CHANNEL_ID, "BLEConnect", NotificationManager.IMPORTANCE_LOW
        )
        manager.createNotificationChannel(channel)
        builder = NotificationBuilder(SERVICE, CHANNEL_ID)
    else:
        builder = NotificationBuilder(SERVICE)

    builder.setContentTitle("BLEConnect")
    builder.setContentText("Clipboard and file sharing is running")
    builder.setSmallIcon(SERVICE.getApplicationInfo().icon)
    builder.setOngoing(True)
    SERVICE.startForeground(1, builder.build())


async def _run() -> None:
    clipboard = AndroidClipboard(SERVICE)
    sound = AndroidSoundPlayer(SERVICE)
    transport = create_pyjnius_transport(SERVICE, log=log)
    link = BlePeripheralLink(transport)
    clipboard_service = ClipboardService(clipboard, link)
    dispatcher = PacketDispatcher()
    find_task: asyncio.Task[None] | None = None

    async def handle_clipboard(packet) -> None:
        try:
            applied = await clipboard_service.handle_packet(packet)
        except Exception:
            log("clipboard handler failed:\n" + traceback.format_exc())
            return
        log(f"clipboard applied={applied}")

    async def handle_ping(packet) -> None:
        try:
            await link.send(control_packet(PONG, {"ts": int(time.time() * 1000)}))
        except Exception as exc:
            log(f"could not send pong: {exc}")

    def start_find_phone(duration: float, volume: float) -> None:
        nonlocal find_task
        if find_task is not None and not find_task.done():
            find_task.cancel()

        async def runner() -> None:
            try:
                await sound.play_find_phone(duration, volume)
            except asyncio.CancelledError:
                raise
            except Exception:
                log("find-phone playback failed:\n" + traceback.format_exc())

        find_task = asyncio.create_task(runner())

    def handle_find_phone(packet) -> None:
        try:
            duration = float(packet.body.get("duration_s", 30))
            volume = float(packet.body.get("volume", 1.0))
        except (TypeError, ValueError):
            log("ignored find_phone with invalid duration or volume")
            return
        start_find_phone(duration, volume)
        log(f"find phone for {duration}s at volume {volume}")

    async def handle_find_phone_stop(packet) -> None:
        nonlocal find_task
        if find_task is not None and not find_task.done():
            find_task.cancel()
        find_task = None
        await sound.stop()
        log("find phone stopped")

    async def handle_file_incoming(packet) -> None:
        log("file transfer is not implemented in this build")
        await link.send(
            control_packet(
                ERROR,
                {
                    "code": "not_implemented",
                    "message": "file transfer is pending",
                },
            )
        )

    dispatcher.register(CLIPBOARD, handle_clipboard)
    dispatcher.register(PING, handle_ping)
    dispatcher.register(FIND_PHONE, handle_find_phone)
    dispatcher.register(FIND_PHONE_STOP, handle_find_phone_stop)
    dispatcher.register(FILE_INCOMING, handle_file_incoming)

    await link.connect()
    log(f"BLE peripheral started; mtu={link.mtu_size}")

    async def handle_command(command: dict) -> dict:
        nonlocal find_task
        name = command.get("command")
        if name == "state":
            return {
                "ok": True,
                "state": {
                    "connected": link.connected,
                    "paused": clipboard_service.paused,
                    "mtu": link.mtu_size,
                    "log": str(_log_path()),
                },
            }
        if name == "send_clipboard":
            text = command.get("text")
            if not isinstance(text, str) or not text:
                return {"ok": False, "error": "text is required"}
            try:
                sent = await clipboard_service.publish_snapshot(
                    ClipboardSnapshot(text)
                )
            except Exception as exc:
                log(f"clipboard send failed: {exc}")
                return {"ok": False, "error": str(exc)}
            return {"ok": True, "sent": sent}
        if name == "pause":
            clipboard_service.pause()
            return {"ok": True, "paused": True}
        if name == "resume":
            clipboard_service.resume()
            return {"ok": True, "paused": False}
        if name == "ring":
            try:
                duration = float(command.get("duration_s", 10))
                volume = float(command.get("volume", 1.0))
            except (TypeError, ValueError):
                return {"ok": False, "error": "invalid duration or volume"}
            start_find_phone(duration, volume)
            return {"ok": True}
        return {"ok": False, "error": f"unknown command: {name}"}

    control = ControlServer(handle_command)
    await control.start()
    log(f"control server on 127.0.0.1:{control.port}")

    try:
        while True:
            packet = await link.receive()
            try:
                await dispatcher.dispatch(packet)
            except Exception:
                log("packet dispatch failed:\n" + traceback.format_exc())
    finally:
        await control.close()
        await link.close()
        await sound.stop()


def main() -> None:
    try:
        PythonService.mService.setAutoRestartService(True)
    except Exception:
        pass

    start_foreground()
    log(f"service started; log={_log_path()}")
    try:
        asyncio.run(_run())
    except Exception:
        log("service crashed:\n" + traceback.format_exc())


if __name__ == "__main__":
    main()
