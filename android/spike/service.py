"""M0 spike: Python foreground service with a BLE GATT server.

The service keeps a Python process alive with the screen off, receives BLE GATT
writes through a thin Java bridge, writes clipboard text, and logs every event to
an external file for verification.
"""

from __future__ import annotations

import asyncio
import json
import time
import traceback
from pathlib import Path

from jnius import PythonJavaClass, autoclass, java_method

PythonService = autoclass("org.kivy.android.PythonService")
Context = autoclass("android.content.Context")
BuildVersion = autoclass("android.os.Build$VERSION")
Notification = autoclass("android.app.Notification")
NotificationChannel = autoclass("android.app.NotificationChannel")
NotificationManager = autoclass("android.app.NotificationManager")
ClipData = autoclass("android.content.ClipData")
BleSpikeBridge = autoclass("org.bleconnect.spike.BleSpikeBridge")

SERVICE = PythonService.mService
CHANNEL_ID = "bleconnect_spike"
_notification_id = 1
_bridge = None


def _log_path() -> Path:
    directory = SERVICE.getExternalFilesDir(None)
    if directory is None:
        directory = SERVICE.getFilesDir()
    return Path(directory.getAbsolutePath()) / "spike.log"


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
            CHANNEL_ID, "BLEConnect spike", NotificationManager.IMPORTANCE_LOW
        )
        manager.createNotificationChannel(channel)
        builder = Notification.Builder(SERVICE, CHANNEL_ID)
    else:
        builder = Notification.Builder(SERVICE)

    builder.setContentTitle("BLEConnect spike")
    builder.setContentText("BLE GATT server is running")
    builder.setSmallIcon(SERVICE.getApplicationInfo().icon)
    builder.setOngoing(True)
    SERVICE.startForeground(_notification_id, builder.build())


class BridgeListener(PythonJavaClass):
    __javainterfaces__ = ["org/bleconnect/spike/BleSpikeBridge$Listener"]
    __javacontext__ = "app"

    @java_method("(Ljava/lang/String;)V")
    def onLog(self, message: str) -> None:
        log(f"bridge: {message}")

    @java_method("(Ljava/lang/String;)V")
    def onClipboardText(self, text: str) -> None:
        try:
            clipboard = SERVICE.getSystemService(Context.CLIPBOARD_SERVICE)
            clip = ClipData.newPlainText("BLEConnect", text)
            clipboard.setPrimaryClip(clip)
            log(f"clipboard set: {text!r}")
        except Exception:
            log("clipboard write failed:\n" + traceback.format_exc())

    @java_method("(Ljava/lang/String;)V")
    def onControlMessage(self, text: str) -> None:
        log(f"control: {text}")
        try:
            message = json.loads(text)
        except Exception:
            log("control message is not JSON")
            return
        if message.get("type") == "ping" and _bridge is not None:
            _bridge.sendControl(
                json.dumps({"type": "pong", "body": {"from": "android-spike"}})
            )


async def _heartbeat() -> None:
    while True:
        await asyncio.sleep(30)
        log("heartbeat")


def main() -> None:
    global _bridge

    try:
        PythonService.mService.setAutoRestartService(True)
    except Exception:
        pass

    start_foreground()
    log(f"service started; log={_log_path()}")
    log("waiting for BLE writes")

    listener = BridgeListener()
    _bridge = BleSpikeBridge(SERVICE, listener)
    try:
        _bridge.start()
    except Exception:
        log("bridge start failed:\n" + traceback.format_exc())

    asyncio.run(_heartbeat())


if __name__ == "__main__":
    main()
