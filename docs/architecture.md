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

## Transport split

The canonical transport and protocol details live in `docs/spec.md`. Bluetooth
has two distinct roles:

- **BLE GATT** — presence, control messages, find-phone, and clipboard text.
  Android is the peripheral/advertiser; Linux is the central/GATT client.
- **RFCOMM** — on-demand file transfer only. Linux is the server; Android
  connects when a transfer starts.

Clipboard and file transfer use separate ports even though both ultimately cross
Bluetooth. This keeps platform permissions, reconnection rules, and test fakes
independent.

## Dependency rules

Application services may call ports and protocol code. Platform adapters implement ports and may depend on OS libraries. UI calls application services. Keep dependencies pointing inward: application logic must not import Kivy, BlueZ, Android classes, or desktop clipboard tools.

Use a rooted filesystem adapter for directory browsing. It must reject paths that resolve outside the directory explicitly shared by the user. Clipboard and file operations should be separate ports because their permissions and platform behavior differ.

## Initial module plan

```text
src/bleconnect/
  protocol.py
  ble_protocol.py
  application/
    pairing_service.py
    clipboard_service.py
    file_transfer_service.py
    file_browser_service.py   # future shared-folder feature
    session.py
    ports.py
  presentation/
    app_controller.py
    view_models.py
  adapters/
    linux/bluez_pairing.py
    linux/ble_central.py
    linux/rfcomm.py
    linux/clipboard.py
    linux/trusted_devices.py
    android/bluetooth.py        # planned
    android/clipboard.py        # planned
    filesystem/file_source.py
    filesystem/file_sink.py
    filesystem/rooted_files.py  # future shared-folder feature
  platform/
    linux.py
    android.py
```

Implemented today: shared RFCOMM v2 framing, BLE frame chunking and
reassembly, message helpers, application ports, clipboard, file-transfer, and
pairing services, a packet dispatcher and session loop, `AppController`, shared
view models, Linux/Android composition roots, and the Linux adapters (BlueZ
pairing, BLE central, RFCOMM server, clipboard providers/watcher, trusted
devices, local file source/sink). The core and adapters are covered by
hardware-free tests using in-memory links and fakes.

Not implemented yet: the Android bridge/service and Kivy UI, Qt views,
reconnect/backoff, the clipboard IME, and PC-to-phone file sending
orchestration. These must implement the ports in
`application/ports.py`; application services do not perform platform work.

Add modules when their first behavior is implemented; avoid empty abstractions and one-class-per-file layering without a use case.
