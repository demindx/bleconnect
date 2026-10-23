"""Kivy UI for the BLEConnect Android app."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from android.permissions import Permission, request_permissions
from jnius import autoclass
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from bleconnect.ipc import request_sync

PythonActivity = autoclass("org.kivy.android.PythonActivity")
ServiceBleconnect = autoclass("org.bleconnect.app.ServiceBleconnect")
Context = autoclass("android.content.Context")


def _permission(name: str) -> str:
    return getattr(Permission, name, f"android.permission.{name}")


def _socket_path() -> str:
    activity = PythonActivity.mActivity
    return str(Path(activity.getFilesDir().getAbsolutePath()) / "daemon.sock")


def read_clipboard_text() -> str | None:
    activity = PythonActivity.mActivity
    if activity is None:
        return None
    clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE)
    clip = clipboard.getPrimaryClip()
    if clip is None or clip.getItemCount() == 0:
        return None
    text = clip.getItemAt(0).getText()
    return str(text) if text is not None else None


class StatusPoller(threading.Thread):
    def __init__(self, on_state) -> None:
        super().__init__(daemon=True)
        self._on_state = on_state

    def run(self) -> None:
        while True:
            try:
                state = request_sync(_socket_path(), "state.get", timeout=1.0)
            except Exception:
                state = None
            self._on_state(state)
            time.sleep(2.0)


class BleConnectRoot(BoxLayout):
    def __init__(self, **kwargs) -> None:
        super().__init__(orientation="vertical", padding=12, spacing=8, **kwargs)
        self.status = Label(text="Start the service to enable clipboard sharing.")
        self.add_widget(self.status)

        self.add_widget(
            Button(text="Request permissions", on_release=lambda *_: self.ask_permissions())
        )
        self.add_widget(
            Button(text="Start service", on_release=lambda *_: self.start_service())
        )
        self.add_widget(
            Button(text="Stop service", on_release=lambda *_: self.stop_service())
        )
        self.add_widget(
            Button(text="Send clipboard to PC", on_release=lambda *_: self.send_clipboard())
        )
        self.add_widget(
            Button(text="Pause clipboard sync", on_release=lambda *_: self.pause())
        )
        self.add_widget(
            Button(text="Resume clipboard sync", on_release=lambda *_: self.resume())
        )
        self.add_widget(
            Button(text="Test find-phone", on_release=lambda *_: self.ring())
        )
        self.add_widget(
            Button(text="Refresh log", on_release=lambda *_: self.refresh_log())
        )

        self.log_view = TextInput(
            text="", readonly=True, font_size="11sp", size_hint_y=0.6
        )
        self.add_widget(self.log_view)

        self._poller = StatusPoller(
            lambda response: Clock.schedule_once(
                lambda _dt: self._apply_state(response), 0
            )
        )
        self._poller.start()
        Clock.schedule_interval(self.refresh_log, 3.0)
        Clock.schedule_once(self.refresh_log, 0.5)

    def ask_permissions(self) -> None:
        request_permissions(
            [
                _permission("BLUETOOTH_CONNECT"),
                _permission("BLUETOOTH_ADVERTISE"),
                _permission("POST_NOTIFICATIONS"),
            ],
            self._on_permissions,
        )

    def _on_permissions(self, permissions, grants) -> None:
        self.status.text = "Permissions: " + ", ".join(
            f"{permission}={grant}"
            for permission, grant in zip(permissions, grants)
        )

    def start_service(self) -> None:
        try:
            ServiceBleconnect.start(PythonActivity.mActivity, "")
            self.status.text = "Service start requested."
        except Exception as exc:
            self.status.text = f"Start failed: {exc}"

    def stop_service(self) -> None:
        try:
            ServiceBleconnect.stop(PythonActivity.mActivity)
            self.status.text = "Service stop requested."
        except Exception as exc:
            self.status.text = f"Stop failed: {exc}"

    def send_clipboard(self) -> None:
        text = read_clipboard_text()
        if not text:
            self.status.text = "Clipboard is empty or unreadable."
            return
        self._run_command(
            "clipboard.send", {"text": text}, "Clipboard sent."
        )

    def pause(self) -> None:
        self._run_command("sync.pause", {}, "Clipboard sync paused.")

    def resume(self) -> None:
        self._run_command("sync.resume", {}, "Clipboard sync resumed.")

    def ring(self) -> None:
        self._run_command(
            "find_phone.start",
            {"duration_s": 10, "volume": 1.0},
            "Find-phone started.",
        )

    def _run_command(
        self, method: str, params: dict, success: str
    ) -> None:
        def worker() -> None:
            try:
                result = request_sync(_socket_path(), method, params)
                error = None
            except Exception as exc:
                result = None
                error = str(exc)
            Clock.schedule_once(
                lambda _dt: self._show_result(result, error, success), 0
            )

        threading.Thread(target=worker, daemon=True).start()

    def _show_result(
        self, result: dict | None, error: str | None, success: str
    ) -> None:
        if error is not None:
            self.status.text = f"Error: {error}"
        else:
            self.status.text = success

    def _apply_state(self, state: dict | None) -> None:
        if state is None:
            self.status.text = "Service offline."
            return
        connected = "connected" if state.get("connected") else "waiting for PC"
        paused = "paused" if state.get("paused") else "active"
        self.status.text = (
            f"{connected} | clipboard {paused} | MTU {state.get('mtu', '?')}"
        )

    def refresh_log(self, *_args) -> None:
        activity = PythonActivity.mActivity
        if activity is None:
            return
        directory = activity.getExternalFilesDir(None) or activity.getFilesDir()
        path = Path(directory.getAbsolutePath()) / "service.log"
        try:
            self.log_view.text = path.read_text(encoding="utf-8")[-8000:]
        except FileNotFoundError:
            self.log_view.text = f"No log yet: {path}"
        except Exception as exc:
            self.log_view.text = f"Log read failed: {exc}"


class BleConnectApp(App):
    def build(self):
        self.title = "BLEConnect"
        return BleConnectRoot()


if __name__ == "__main__":
    BleConnectApp().run()
