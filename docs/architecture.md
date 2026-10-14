# Architecture

Use a small Clean Architecture / ports-and-adapters structure. Keep feature workflows independent of Bluetooth libraries and desktop or Android APIs.

```text
Kivy UI (Android) ─┐
                   ├─> Application services ─> ports
Linux UI/CLI ──────┘                            ▲
                                                │
                      platform adapters ───────┘
```

## Responsibilities

- **Presentation** — Kivy screens and Linux UI/CLI. Collect user choices and display status; do not implement transport or file access.
- **Application services** — coordinate actions such as pairing, clipboard synchronization, listing a shared folder, and downloading a file. Depend on interfaces, not platform packages.
- **Repositories** — load and save application data, such as trusted-device metadata and user preferences. A repository is not the Bluetooth connection itself.
- **Platform adapters** — implement ports using BlueZ/RFCOMM on Linux, Android Bluetooth APIs, OS clipboard APIs, and filesystem access.
- **Protocol** — packet types, framing, version negotiation, and payload rules shared by both peers.

## Dependency rules

Application services may call ports and protocol code. Platform adapters implement ports and may depend on OS libraries. UI calls application services. Keep dependencies pointing inward: application logic must not import Kivy, BlueZ, Android classes, or desktop clipboard tools.

Use a rooted filesystem adapter for directory browsing. It must reject paths that resolve outside the directory explicitly shared by the user. Clipboard and file operations should be separate ports because their permissions and platform behavior differ.

## Initial module plan

```text
src/bleconnect/
  protocol.py
  application/
    pairing_service.py
    clipboard_service.py
    file_browser_service.py
    ports.py
  adapters/
    linux/bluetooth_rfcomm.py
    linux/clipboard.py
    android/bluetooth.py
    android/clipboard.py
    filesystem/rooted_files.py
```

Implemented today: clipboard and file-browser use cases and their ports,
`RootedFiles` for read-only Linux access, `RfcommDeviceLink` for a paired
RFCOMM socket when its address and channel are already known, and injectable
Linux clipboard providers. The composition root chooses a provider and passes
its `ClipboardPort` to the clipboard service. `PairingService` coordinates
discovery and pairing through a port; Linux uses BlueZ D-Bus and persists
trusted metadata as JSON. RFCOMM service registration, Android integration,
and presentation remain platform work; application services do not perform
those tasks.

Add modules when their first behavior is implemented; avoid empty abstractions and one-class-per-file layering without a use case.
