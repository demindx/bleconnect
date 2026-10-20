# BLEConnect

An Android and Linux app for seamless clipboard sharing, explicit file transfer,
and finding your phone over Bluetooth.

## Direction

The application logic and both interfaces are Python. Linux uses PySide6/Qt;
Android uses Kivy with a thin native bridge. Bluetooth has two roles:

- **BLE GATT** carries presence, control messages, find-phone, and clipboard
  text. Android is the peripheral/advertiser; Linux is the central/GATT client.
- **Bluetooth Classic RFCOMM** carries on-demand file transfers.

`docs/spec.md` is the canonical product, protocol, UI, and platform
specification. `docs/architecture.md` records the dependency boundaries.

## Current state

- RFCOMM v2 framing (`protocol.py`) and BLE chunk framing/reassembly
  (`ble_protocol.py`).
- Shared message names (`messages.py`).
- Ports and use cases for clipboard, file transfer, pairing, and session
  dispatch (`application/`).
- `AppController` and UI-agnostic view models shared by Qt and Kivy
  (`presentation/`).
- Linux adapters:
  - BlueZ discovery/pairing and trusted-device persistence.
  - BLE central over `bleak` with chunking and reassembly.
  - RFCOMM profile server and packet link.
  - Wayland/X11 clipboard providers and a change watcher.
  - Local file source and atomic `Downloads/bleconnect` sink.
- Linux/Android composition helpers and a small CLI.
- Unit and integration tests with in-memory fakes.

Not implemented yet:

- Production Android foreground service and Kivy UI.
- Qt interface.
- Clipboard IME for background Android-to-Linux sync.
- Automatic reconnect/backoff and the full GUI orchestration.
- PC-to-phone file sending orchestration (the RFCOMM receive path is ready).

## Repository layout

- `src/bleconnect/protocol.py` — shared RFCOMM v2 framing and validation.
- `src/bleconnect/ble_protocol.py` — BLE frame format, chunking, reassembly.
- `src/bleconnect/messages.py` — shared message type names and packet helpers.
- `src/bleconnect/application/` — ports, clipboard, file transfer, pairing,
  and session dispatch.
- `src/bleconnect/presentation/` — `AppController` and shared view models.
- `src/bleconnect/adapters/linux/` — BlueZ pairing, BLE central, RFCOMM,
  clipboard, trusted devices.
- `src/bleconnect/adapters/filesystem/` — local file source and sink.
- `src/bleconnect/platform/` — Linux and Android composition roots.
- `android/spike/` — M0 foreground-service/BLE spike.
- `tests/` — unit and integration tests with in-memory fakes.
- `docs/spec.md` — canonical specification.
- `docs/architecture.md` — architectural boundaries and dependency direction.

## Development

Use Python 3.11 or newer. Create the environment with `uv sync` and run project
commands with `uv run`.

```sh
uv sync --extra dev --extra linux
uv run pytest
uv run bleconnect --version
```

Extras:

- `linux` — `dbus-next` and `bleak` for BlueZ, BLE, and RFCOMM.
- `gui` — PySide6 and qasync for the future Qt interface.
- `android` — Kivy and pyjnius for the Android package.

Clipboard commands use `wl-copy`/`wl-paste` on Wayland or `xclip` on X11; install
the matching desktop package.

## Linux adapter commands

These commands exercise the Linux adapters without a GUI. Run them from the
graphical session so clipboard and BlueZ agents are available.

```sh
# Find the Android BLE peripheral
uv run bleconnect ble-scan

# Send one control ping and wait for pong (production framed BLE service)
uv run bleconnect ble-ping --address AA:BB:CC:DD:EE:FF

# Discover and pair through the desktop BlueZ agent
uv run bleconnect discover
uv run bleconnect pair --address AA:BB:CC:DD:EE:FF
uv run bleconnect forget --address AA:BB:CC:DD:EE:FF

# Accept RFCOMM file transfers and save them under ~/Downloads/bleconnect
uv run bleconnect rfcomm-server
```

`rfcomm-server` accepts only trusted devices. The current M0 spike uses raw BLE
writes, so `ble-ping` targets the production framed BLE service, not the spike.

The next milestone is the production Android service and Kivy UI (issue #3),
including the full 30-minute screen-off soak.
