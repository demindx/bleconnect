# BLEConnect

An Android and Linux app for sharing text and browsing a user-approved folder over Bluetooth.

## Direction

The app logic and user interface will be Python. The Android build will use Kivy and Python for Android; Bluetooth access on Android may need a small bridge to Android's Bluetooth APIs. The Linux companion will use Python with BlueZ. The first transport target is Bluetooth Classic RFCOMM because it provides a bidirectional byte stream suitable for clipboard messages and file transfers.

The repository now contains shared packet framing, application-level ports and clipboard/file/pairing services, a read-only Linux rooted-files adapter, BlueZ discovery/pairing and trusted-device persistence, Linux clipboard providers, a BlueZ RFCOMM server, and a minimal Android RFCOMM test client. The full Kivy UI, production reconnect behavior, and clipboard IME are not implemented yet. Recent Android versions restrict background clipboard reads, so background synchronization needs an Android-specific clipboard strategy.

Clipboard access is injected through `ClipboardPort`; the sync service does not select or import a desktop utility. The Linux composition root chooses an ordered provider list at startup, so another backend can be added or injected without changing application services:

```python
clipboard = resolve_linux_clipboard(
    [WaylandClipboardProvider(), XclipClipboardProvider()]
)
service = ClipboardSyncService(clipboard, device_link)
```

On Fedora Wayland, `WaylandClipboardProvider` uses `wl-copy` and `wl-paste`; install Fedora's `wl-clipboard` package and start BLEConnect from the graphical session so it inherits `WAYLAND_DISPLAY`. `XclipClipboardProvider` supports X11 and acts as a fallback when both display variables are present. Providers can be replaced or reordered at startup. The command adapter skips clipboard offers marked with KDE's `x-kde-passwordManagerHint` MIME type and accepts an application supplied sensitivity detector. Wayland has no universal sensitivity marker, so unmarked secret text cannot be identified automatically. Clipboard commands require access to the active desktop session. [Fedora wl-clipboard package](https://packages.fedoraproject.org/pkgs/wl-clipboard/wl-clipboard/) · [Wayland clipboard limitations](https://manpages.ubuntu.com/manpages/questing/man1/wl-paste.1.html) · [KDE password manager marker](https://github.com/bugaevc/wl-clipboard/issues/177)

## Repository layout

- `src/bleconnect/protocol.py` — shared, versioned message framing and validation.
- `src/bleconnect/application/` — transport, clipboard, and shared-file ports and use cases.
- `src/bleconnect/adapters/filesystem/rooted_files.py` — read-only access within an explicitly selected Linux directory.
- `src/bleconnect/adapters/linux/bluetooth_rfcomm.py` — RFCOMM packet link for an already paired peer and known channel.
- `src/bleconnect/adapters/linux/bluez_pairing.py` — BlueZ discovery and pairing through system D-Bus.
- `src/bleconnect/adapters/linux/bluez_rfcomm_server.py` — register an RFCOMM service with BlueZ and accept links.
- `src/bleconnect/adapters/linux/trusted_devices.py` — atomic JSON persistence for trusted device metadata.
- `src/bleconnect/adapters/linux/clipboard.py` — injectable clipboard port, command adapter, and Wayland/X11 providers.
- `android/test-client/` — debug app that connects to a paired Linux peer by UUID and sends a protocol ping.
- `tests/` — protocol framing, application behavior, filesystem boundaries, and link tests.
- `android/` — Kivy Android UI and packaging (to be added).
- `docs/architecture.md` — architecture boundaries and dependency direction.

## Development

Use Python 3.11 or newer for Linux development. Create the environment with `uv sync` and run project commands with `uv run`.

For the Linux BlueZ pairing adapter, install the optional D-Bus dependency with `uv sync --extra linux`. Pairing confirmation is handled by the active desktop BlueZ agent.

### Real-device RFCOMM smoke test

Build the test APK with Android SDK platform 34 and Java 17 or newer:

```sh
cd android/test-client
ANDROID_HOME=/path/to/android-sdk ./gradlew assembleDebug
```

Pair the phone and Fedora computer in Android Bluetooth settings, then run the Linux server from the graphical session:

```sh
cd /path/to/bleconnect
uv sync --extra linux
uv run bleconnect rfcomm-server
```

Install `app/build/outputs/apk/debug/app-debug.apk` with ADB, open **BLEConnect RFCOMM Test**, refresh paired devices, select Fedora, and tap **Connect and send ping**. A successful test displays the Linux `pong` response. Keep the Linux server running during the test. This checks the Bluetooth RFCOMM service and packet framing; it does not yet test app-driven pairing or reconnect.

The Android test app is a small native debug harness; production APK packaging will use Kivy and python-for-android with the planned Kotlin Bluetooth bridge.

Run the unit tests with `uv sync --extra dev` followed by `uv run pytest`.
