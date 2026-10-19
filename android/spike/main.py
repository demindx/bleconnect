"""Minimal Kivy control surface for the BLEConnect M0 spike."""

from __future__ import annotations

from pathlib import Path

from android.permissions import Permission, request_permissions
from jnius import autoclass
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

PythonActivity = autoclass("org.kivy.android.PythonActivity")
ServiceBleconnect = autoclass("org.bleconnect.spike.ServiceBleconnect")


def _permission(name: str) -> str:
    return getattr(Permission, name, f"android.permission.{name}")


class SpikeRoot(BoxLayout):
    def __init__(self, **kwargs) -> None:
        super().__init__(orientation="vertical", padding=12, spacing=8, **kwargs)
        self.status = Label(text="Request permissions, then start the service.")
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
            Button(text="Refresh log", on_release=lambda *_: self.refresh_log())
        )
        self.log_view = TextInput(
            text="", readonly=True, font_size="11sp", size_hint_y=0.7
        )
        self.add_widget(self.log_view)
        Clock.schedule_interval(self.refresh_log, 2.0)
        Clock.schedule_once(self.refresh_log, 0.5)

    def ask_permissions(self) -> None:
        permissions = [
            _permission("BLUETOOTH_CONNECT"),
            _permission("BLUETOOTH_ADVERTISE"),
            _permission("POST_NOTIFICATIONS"),
        ]
        request_permissions(permissions, self._on_permissions)

    def _on_permissions(self, permissions, grants) -> None:
        self.status.text = "Permissions: " + ", ".join(
            f"{permission}={grant}" for permission, grant in zip(permissions, grants)
        )

    def start_service(self) -> None:
        try:
            ServiceBleconnect.start(PythonActivity.mActivity, "")
            self.status.text = "Service start requested. Turn the screen off and test from Linux."
        except Exception as exc:
            self.status.text = f"Start failed: {exc}"

    def stop_service(self) -> None:
        try:
            ServiceBleconnect.stop(PythonActivity.mActivity)
            self.status.text = "Service stop requested."
        except Exception as exc:
            self.status.text = f"Stop failed: {exc}"

    def refresh_log(self, *_args) -> None:
        activity = PythonActivity.mActivity
        directory = activity.getExternalFilesDir(None) or activity.getFilesDir()
        path = Path(directory.getAbsolutePath()) / "spike.log"
        try:
            self.log_view.text = path.read_text(encoding="utf-8")[-8000:]
        except FileNotFoundError:
            self.log_view.text = f"No log yet: {path}"
        except Exception as exc:
            self.log_view.text = f"Log read failed: {exc}"


class SpikeApp(App):
    def build(self):
        self.title = "BLEConnect M0 Spike"
        return SpikeRoot()


if __name__ == "__main__":
    SpikeApp().run()
