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

The repository has been rebuilt from scratch as an application skeleton:

- RFCOMM v2 framing (`protocol.py`) and BLE chunk framing/reassembly
  (`ble_protocol.py`).
- Shared message names (`messages.py`).
- Ports and use cases for clipboard, file transfer, pairing, and session
  dispatch (`application/`).
- `AppController` and UI-agnostic view models shared by Qt and Kivy
  (`presentation/`).
- Linux and Android composition roots (`platform/`).
- Unit and integration tests using in-memory fakes (`tests/`).

Not implemented yet:

- BLE and RFCOMM platform adapters (BlueZ, `bleak`, Android bridge).
- Qt and Kivy interfaces.
- Android foreground service and clipboard IME.
- Reconnect/backoff and real-device flows.

## Repository layout

- `src/bleconnect/protocol.py` — shared RFCOMM v2 framing and validation.
- `src/bleconnect/ble_protocol.py` — BLE frame format, chunking, reassembly.
- `src/bleconnect/messages.py` — shared message type names and packet helpers.
- `src/bleconnect/application/` — ports, clipboard, file transfer, pairing,
  and session dispatch.
- `src/bleconnect/presentation/` — `AppController` and shared view models.
- `src/bleconnect/platform/` — Linux and Android composition roots.
- `src/bleconnect/adapters/` — platform adapters (planned).
- `android/` — Kivy packaging and native bridge (planned).
- `tests/` — unit and integration tests with in-memory fakes.
- `docs/spec.md` — canonical specification.
- `docs/architecture.md` — architectural boundaries and dependency direction.

## Development

Use Python 3.11 or newer. Create the environment with `uv sync` and run project
commands with `uv run`.

```sh
uv sync --extra dev
uv run pytest
uv run bleconnect --version
```

Optional extras:

- `uv sync --extra linux` — `dbus-next` and `bleak` for the future Linux
  adapters.
- `uv sync --extra gui` — PySide6 and qasync for the future Qt interface.
- `uv sync --extra android` — Kivy and pyjnius for the future Android package.

The next milestone is the Android background spike described in
`docs/spec.md`: prove that a foreground Python service can host a GATT server
and write the clipboard with the screen off. The spike project and its
build/run instructions live in `android/spike/`; the Linux test client is
`tools/ble_spike_client.py`. Platform adapters and GUIs follow after that.
