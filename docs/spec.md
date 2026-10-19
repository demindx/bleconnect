# BLEConnect Specification

Status: draft for MVP
Last updated: 2026-10-19

This document is the canonical product and protocol specification for BLEConnect.
It describes the intended behavior, transports, wire formats, platform rules, and
testing strategy. Code must follow this document; when behavior changes, update
this file in the same change.

## 1. Purpose and Scope

BLEConnect connects a Linux computer and an Android phone over Bluetooth and
provides:

- seamless clipboard text sharing;
- file transfer in both directions without a shared folder;
- a "find my phone" action.

The Linux application is Python with PySide6/Qt. The Android application is
Python with Kivy and a thin native bridge. Application logic is independent of
both GUIs and of platform APIs.

### 1.1 Goals

- Clipboard synchronization without pressing a sync button on the Linux side.
- Predictable file transfer with progress, cancellation, and integrity checks.
- One code base for clipboard, file, and connection logic on both platforms.
- A small, replaceable UI layer: Qt and Kivy reuse the same view models.
- Hardware-free unit and integration tests for everything except Bluetooth.
- Only bonded/trusted devices can exchange data.

### 1.2 Non-Goals for MVP

- iOS support.
- Multi-device fan-out; one active peer at a time.
- Clipboard images, HTML, or file lists. Text only.
- Shared-folder browsing. A rooted-files adapter can be added later for that
  feature; it is not part of MVP.
- Resume of interrupted file transfers. MVP restarts a transfer from zero.
- Cloud relay, internet transport, or Wi-Fi transport.
- App-level end-to-end encryption beyond Bluetooth bonding.
- Localization. English UI strings first; strings must be centralized so
  translation can be added without touching logic.

## 2. Terminology

| Term | Meaning |
| --- | --- |
| Peer | The other device: Linux or Android. |
| Central | BLE GATT client. Linux in MVP. |
| Peripheral | BLE GATT server and advertiser. Android in MVP. |
| Link | A bidirectional message channel used by application services. |
| Session | One authenticated connection between the two applications. |
| Transfer | One file moving in one direction. |
| Sensitive text | Clipboard text marked as secret by the platform or a detector. |
| Trusted device | A device that is bonded in the OS and approved in BLEConnect. |

## 3. User Stories

1. As a user, I copy text on Linux and it appears on Android without any action.
2. As a user, I copy text on Android while the app is open and press "Send
   clipboard" to push it to Linux.
3. As a user with the BLEConnect IME installed and selected, my Android clipboard
   is sent automatically in the background.
4. As a user, I select a file on Linux and send it to Android; it is saved in
   `Downloads/bleconnect`.
5. As a user, I select a file on Android and send it to Linux; it is saved in
   `~/Downloads/bleconnect`.
6. As a user, I press "Find phone" on Linux and my phone rings loudly.
7. As a user, I can pause clipboard synchronization and see the connection state
   from the Linux tray.
8. As a user, I can trust or forget a device and only trusted devices connect.

## 4. Functional Requirements

### 4.1 Pairing and Trust

- First-time pairing is performed by the OS (Blueprint/BlueZ agent on Linux,
  Android Bluetooth settings), not by the app.
- The application never accepts a passkey on its own.
- Both sides persist the peer address and display name.
- Linux rejects RFCOMM connections from addresses not in the trusted-device
  repository.
- Android accepts BLE connections only from bonded devices.
- The user can forget a trusted device from the Linux settings window and from
  the Android settings screen.
- Exactly one active peer is supported in MVP. Additional paired devices may be
  listed but not connected simultaneously.

### 4.2 Connection Lifecycle

- Android runs a foreground service that advertises over BLE and hosts the GATT
  server while enabled.
- Linux scans for the BLE service when disconnected, connects as GATT central,
  and keeps the connection while both applications are running.
- If the BLE link drops, both sides retry with exponential backoff.
- RFCOMM is opened on demand for file transfer and closed after an idle timeout.
- The UI shows one of: offline, scanning, connecting, connected, paused, error.

### 4.3 Clipboard

- Linux to Android is automatic when synchronization is enabled.
- Android to Linux is manual via the in-app button in MVP.
- Android to Linux becomes automatic when the BLEConnect IME is installed and
  selected as the default keyboard (post-MVP).
- Only text is synchronized.
- Text marked sensitive is never sent.
- Empty text is ignored.
- Text larger than 64 KiB UTF-8 is ignored and reported in the UI.
- The service suppresses echo loops with last-sent/last-received values.
- Clipboard synchronization can be paused from the Linux tray and Android UI.

### 4.4 File Transfer

- Both directions are supported.
- The sender explicitly selects one file.
- The receiver saves to `Downloads/bleconnect` (Android) or
  `~/Downloads/bleconnect` (Linux); the Linux directory is configurable.
- Maximum file size is 100 MiB by default; the limit is configurable and
  enforced on both sides.
- Transfer shows progress, supports cancellation, and verifies SHA-256.
- Partial files are never left with the final name.
- Existing files are never overwritten; a numeric suffix is added.
- Only one transfer runs at a time per peer.

### 4.5 Find Phone

- Linux can request the Android phone to play a built-in sound for 30 seconds at
  maximum media volume.
- The user can stop the sound early.
- The action requires the Android foreground service to be alive.
- If the phone is offline, Linux shows a status message instead of queueing the
  action indefinitely.

### 4.6 Linux UI

- Runs as a tray application with a settings window.
- Tray menu: status/device, pause/resume clipboard, send file, find phone,
  settings, quit.
- Closing the settings window hides it to the tray; only Quit stops the service.
- Settings: trusted devices, download directory, maximum file size, clipboard
  pause state, start-at-login toggle.
- Notifications for received files and errors.

### 4.7 Android UI

- Kivy screens: status, send clipboard, send file, current transfer, settings.
- Shows connection state and the active peer.
- Explains the Android clipboard restriction and, later, how to enable the IME.
- Shows permission status for Bluetooth, notifications, and battery
  optimization.
- A persistent foreground notification shows the service state.

## 5. Non-Functional Requirements

### 5.1 Security and Privacy

- Bluetooth bonding is the trust boundary.
- BLE characteristics require an encrypted/authenticated link.
- Linux filters RFCOMM and BLE peers against the trusted list.
- Clipboard text and file contents are never logged.
- File names are sanitized; path traversal is rejected.
- The BLE advertisement contains no clipboard or file data.
- Advertising stops when the Android service is disabled.
- If the user pauses synchronization, no clipboard data is sent or applied.

### 5.2 Performance

- Clipboard text up to 64 KiB must be delivered reliably.
- File throughput is expected to be roughly 100-250 KiB/s over RFCOMM; a 100 MiB
  file may take 7-15 minutes. The UI must communicate this expectation.
- Clipboard changes should reach the peer within 1 second while connected.
- No UI thread may block on Bluetooth, disk, or clipboard operations.

### 5.3 Compatibility

- Linux: Python 3.11+, BlueZ, PySide6, qasync, dbus-next, bleak.
- Android: minSdk to be decided by the Kivy/buildozer toolchain; target API 34.
- Android 10+ scoped storage rules apply.
- Android 12+ Bluetooth runtime permissions apply.
- Android 14+ foreground-service type requirements apply.

## 6. System Architecture

### 6.1 Layers

```text
Qt view (PySide6) ─┐
                   ├─> ViewModels / AppController ─> services ─> ports
Kivy view ─────────┘                                        ▲
                                          platform adapters ─┘
```

- Views collect input and render state.
- View models are pure Python and shared by Qt and Kivy.
- `AppController` is the facade used by both UIs.
- Application services depend on ports and protocol code only.
- Adapters implement ports and may import OS libraries.
- Composition roots (`platform/linux.py`, `platform/android.py`) construct
  concrete adapters.

### 6.2 Planned Module Layout

```text
src/bleconnect/
  protocol.py                 # shared framing and validation (v2)
  messages.py                 # shared message type names and payload helpers
  ble_protocol.py             # BLE chunk framing and reassembly
  application/
    ports.py                  # PacketLink, ClipboardPort, PresencePort, ...
    clipboard_service.py
    file_transfer_service.py
    pairing_service.py
    session.py                # packet dispatch and lifecycle
  presentation/
    app_controller.py         # facade
    view_models.py            # UI-agnostic state and commands
  adapters/
    linux/
      bluez_pairing.py
      bluez_rfcomm_server.py
      bluetooth_rfcomm.py
      ble_central.py           # bleak-based GATT client/scanner
      clipboard.py
      trusted_devices.py
      settings.py
    android/                   # thin native bridge wrappers (post-spike)
    filesystem/
      rooted_files.py          # future feature
      file_source.py
      file_sink.py
    ui/
      qt/
      kivy/
  platform/
    linux.py
    android.py
```

Do not create empty packages. Add a module when its first behavior exists.

### 6.3 Core Ports

```python
class PacketLink(Protocol):
    async def send(self, packet: Packet) -> None: ...
    async def receive(self) -> Packet: ...
    async def close(self) -> None: ...

class ClipboardPort(Protocol):
    async def read_text(self) -> ClipboardSnapshot | None: ...
    async def write_text(self, text: str) -> None: ...

class ClipboardWatcher(Protocol):
    def changes(self) -> AsyncIterator[ClipboardSnapshot]: ...

class PresencePort(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def wait_for_peer(self, timeout: float) -> PeerInfo | None: ...

class FileSource(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def size(self) -> int: ...
    def read_chunks(self, chunk_size: int) -> AsyncIterator[bytes]: ...

class FileSink(Protocol):
    async def write(self, data: bytes) -> None: ...
    async def finish(self, sha256: str) -> None: ...
    async def abort(self) -> None: ...

class FileSinkFactory(Protocol):
    async def create(self, name: str, size: int) -> FileSink: ...

class SoundPlayer(Protocol):
    async def play_find_phone(self, duration_s: float, volume: float) -> None: ...
    async def stop(self) -> None: ...
```

`PacketLink` is the transport-neutral link port (formerly `DeviceLink`).
Implementations own connection setup and teardown; services exchange validated
`Packet` objects. The RFCOMM and BLE adapters own their wire formats.

### 6.4 Pattern Notes

```text
Pattern: Ports and Adapters
Where: application/ports.py; adapters/
Why: Bluetooth, clipboard, storage, and sound differ per platform and must be
     replaceable and testable without hardware.
Rejected alternative: direct platform imports inside services, which would leak
     BlueZ/Android APIs into core logic.
```

```text
Pattern: Facade
Where: presentation/app_controller.py
Why: Qt and Kivy need one entry point for connection, clipboard, files, and
     settings; duplicating orchestration in two UIs would diverge.
Rejected alternative: each UI calling services and adapters directly.
```

```text
Pattern: State
Where: session connection state, file transfer state
Why: BLE presence, GATT connection, RFCOMM transfer, and errors produce many
     combinations that are easier to reason about as explicit states.
Rejected alternative: independent booleans such as connected/scanning/sending,
     which allow invalid combinations.
```

```text
Pattern: Observer
Where: view models notify Qt signals and Kivy properties
Why: UI updates without polling and without coupling views to services.
Rejected alternative: UI timers polling controller state.
```

## 7. Transport Architecture

### 7.1 Split

| Transport | Role | Data |
| --- | --- | --- |
| BLE GATT | Presence, control, clipboard | `hello`, heartbeat, find phone, clipboard text |
| RFCOMM | On-demand byte stream | File offers, chunks, completion |

Rationale:

- BLE is well suited for small, infrequent control messages and low idle power.
- RFCOMM provides a reliable stream with better throughput for files.
- Android limits background BLE scanning, so Android is the peripheral and
  advertiser; Linux is the central and scanner. Linux is normally powered and
  can scan without Android's background restrictions.
- Keeping the BLE link alive makes Linux-to-Android clipboard delivery immediate.
- RFCOMM is opened only when a file transfer starts and closed after 60 seconds
  of inactivity.

### 7.2 BLE Roles and Connection

- Android: `BluetoothLeAdvertiser` + `BluetoothGattServer`.
- Linux: BLE scan + GATT client using `bleak`.
- Android advertises while the foreground service is enabled and no central is
  connected.
- Linux scans when disconnected, connects to the advertised service, and keeps
  the GATT connection while the session is active.
- Linux stops scanning after a connection is established.
- On disconnect, Android resumes advertising; Linux resumes scanning with
  backoff.
- Backoff: 1, 2, 5, 10, 30 seconds, capped at 30 seconds.
- If the user disables synchronization or the Android service stops, the peer is
  considered offline.

### 7.3 Heartbeat

- Linux sends `ping` on the BLE control characteristic every 15 seconds.
- Android replies with `pong`.
- If no `pong` arrives for 45 seconds, Linux treats the link as lost and
  reconnects.
- GATT link-loss callbacks are also handled immediately.

### 7.4 Identifier Allocation

- BLE `message_id`: sender-local `uint32`, incremented per message, wrapping.
- RFCOMM `transfer_id`: UUIDv4 string generated by the sender.
- IDs are unique within a session; receivers deduplicate BLE messages for 60
  seconds and reject unknown RFCOMM transfer IDs.

## 8. BLE Protocol

### 8.1 UUIDs

| Item | UUID |
| --- | --- |
| BLE service | `d37b4a31-8e74-4f36-9a01-7d3a8f7c2b10` |
| Info characteristic | `d37b4a32-8e74-4f36-9a01-7d3a8f7c2b10` |
| Control characteristic | `d37b4a33-8e74-4f36-9a01-7d3a8f7c2b10` |
| Clipboard characteristic | `d37b4a34-8e74-4f36-9a01-7d3a8f7c2b10` |
| RFCOMM file service | `d37b4a30-8e74-4f36-9a01-7d3a8f7c2b10` |

RFCOMM keeps the existing default channel 24.

### 8.2 GATT Characteristics

| Characteristic | Properties | Permissions | Purpose |
| --- | --- | --- | --- |
| Info | Read | Encrypted read | JSON device/protocol info |
| Control | Write, Indicate | Encrypted write, encrypted indicate | Control messages |
| Clipboard | Write, Indicate | Encrypted write, encrypted indicate | Clipboard chunks |

- Linux-to-Android uses GATT writes with response.
- Android-to-Linux uses indications (confirmed notifications).
- Subscriptions are enabled by Linux on connect for control and clipboard.
- Android stops advertising when a central connects.

`Info` value is UTF-8 JSON:

```json
{
  "protocol": 1,
  "app_version": "0.1.0",
  "device_name": "Pixel",
  "capabilities": ["clipboard", "file", "find_phone", "ime"]
}
```

### 8.3 Advertising

- Connectable undirected advertising.
- Includes the 128-bit BLE service UUID.
- Includes the shortened local name `BLEConnect` when the advertisement fits.
- No clipboard, file, or user data in the advertisement.
- Advertising stops when a central connects or synchronization is disabled.

### 8.4 Frame Format

Every characteristic value carries exactly one frame:

```text
offset  size  field
0       1     frame version (currently 1)
1       1     frame type (1 = control JSON, 2 = clipboard text)
2       4     message_id (uint32, big-endian)
6       2     chunk_index (uint16, big-endian)
8       2     chunk_count (uint16, big-endian)
10      N     payload
```

- Header size: 10 bytes.
- Chunk index is zero-based.
- `chunk_count` is at least 1.
- Payload is UTF-8 JSON for control frames and UTF-8 text for clipboard frames.
- All multi-byte integers are big-endian.
- Unknown frame versions or types are rejected with an error and the frame is
  dropped.

### 8.5 MTU and Chunking

- The connection targets an ATT MTU of 517. The Linux BLE backend requests it
  when supported; otherwise BlueZ negotiation applies.
- Android reports the negotiated MTU through its GATT server callback.
- Maximum chunk payload is `min(512, mtu - 3 - 10)`.
- If the MTU is unknown, the payload size is 10 bytes (MTU 23 minus 3 ATT bytes
  minus 10 header bytes).
- Control messages larger than one chunk are split; total control JSON must not
  exceed 4 KiB.
- Clipboard text must not exceed 64 KiB UTF-8.
- Reassembly timeout: 10 seconds from the first chunk.
- Maximum concurrent reassemblies: 4. Older incomplete messages are dropped.
- A completed message with a duplicate `message_id` is ignored.

Example: clipboard text of 400 bytes with a 100-byte chunk payload uses
`chunk_count = 4`.

### 8.6 Control Messages

All control payloads are JSON objects with `type` and `body`:

```json
{"type": "ping", "body": {"ts": 1234567890}}
```

| Type | Direction | Body | Meaning |
| --- | --- | --- | --- |
| `hello` | both | `protocol`, `app_version`, `device_name`, `capabilities` | Session greeting |
| `hello_ack` | both | same as `hello` | Greeting confirmation |
| `ping` | Linux to Android | `ts` | Heartbeat |
| `pong` | Android to Linux | `ts` | Heartbeat reply |
| `find_phone` | Linux to Android | `duration_s`, `volume` | Play the find-phone sound |
| `find_phone_stop` | Linux to Android | none | Stop the sound |
| `file_incoming` | Linux to Android | `transfer_id` | Ask Android to open RFCOMM |
| `file_abort` | both | `transfer_id`, `reason` | Abort a pending RFCOMM transfer |
| `error` | both | `code`, `message` | Protocol or operation error |

- `hello` is sent by both sides after the GATT connection is established.
- If `protocol` differs from the supported version, the receiver sends `error`
  with `unsupported_version` and disconnects.
- `find_phone` defaults: `duration_s = 30`, `volume = 1.0`.
- `file_incoming` is only a wake hint. The authoritative file offer happens over
  RFCOMM.

### 8.7 Reliability Rules

- GATT writes use write-with-response; indications are confirmed by the central.
- The sender treats a failed write/indication as a lost link.
- Multi-chunk messages are assembled in memory; no partial clipboard is applied.
- If a chunk sequence is incomplete after 10 seconds, it is discarded.
- The receiver never applies clipboard text before all chunks arrive.

## 9. RFCOMM File Protocol

### 9.1 Connection

- Linux runs the RFCOMM server registered with BlueZ.
- Android connects as the RFCOMM client using the file service UUID.
- `RequireAuthentication` remains enabled.
- Linux accepts the connection only if the peer address is trusted.
- One RFCOMM connection can carry multiple sequential transfers.
- The link closes after 60 seconds without an active transfer.

### 9.2 Frame Format (Protocol Version 2)

The BLE session protocol version and the RFCOMM frame version are independent.
The RFCOMM version below replaces the v1 length-prefixed JSON framing; the
existing Android test client is updated when the v2 protocol lands.

```text
offset  size  field
0       4     header length (uint32, big-endian)
4       H     header (UTF-8 JSON)
4+H     4     payload length (uint32, big-endian)
8+H     P     payload (raw bytes)
```

- Maximum header length: 64 KiB.
- Maximum payload length: 1 MiB.
- File chunks use a payload of 64 KiB.
- Control frames have payload length 0.
- All integers are big-endian.
- A frame larger than the limits is a protocol error and closes the link.

Header shape:

```json
{
  "version": 2,
  "type": "file_offer",
  "body": {"transfer_id": "5f0c...", "name": "photo.jpg", "size": 1234567}
}
```

`id` may be present for request correlation; `transfer_id` is always inside the
body for file messages.

### 9.3 Messages

| Type | Direction | Body | Meaning |
| --- | --- | --- | --- |
| `file_offer` | sender to receiver | `transfer_id`, `name`, `size`, `mime` | Propose a file |
| `file_accept` | receiver to sender | `transfer_id`, `offset` | Accept; `offset` is 0 in MVP |
| `file_reject` | receiver to sender | `transfer_id`, `reason` | Reject the offer |
| `file_chunk` | sender to receiver | `transfer_id`, `offset` | Payload contains bytes |
| `file_complete` | sender to receiver | `transfer_id`, `sha256` | All bytes sent |
| `file_result` | receiver to sender | `transfer_id`, `ok`, `error` | Verification result |
| `file_cancel` | both | `transfer_id`, `reason` | Cancel the transfer |
| `error` | both | `code`, `message` | Protocol error |

Rules:

- `offset` must equal the number of bytes already received; otherwise the
  receiver cancels with `invalid_offset`.
- Chunks are written in order. Concurrent transfers are not supported in MVP.
- The sender hashes the file while streaming and sends the hex SHA-256 in
  `file_complete`.
- The receiver verifies size and hash, then sends `file_result`.
- On any failure, the receiver deletes the partial file and sends
  `file_result` or `file_cancel`.
- No resume in MVP. `file_accept.offset` is always 0.

### 9.4 Transfer Sequences

PC to phone:

1. Linux selects a file and assigns a `transfer_id`.
2. Linux sends BLE `file_incoming` with `transfer_id`.
3. Android opens RFCOMM to Linux, or reuses an already open RFCOMM link.
4. Linux sends `file_offer`.
5. Android validates size/name/space, then sends `file_accept` or `file_reject`.
6. Linux sends `file_chunk` frames and awaits stream backpressure.
7. Linux sends `file_complete` with the SHA-256.
8. Android verifies, finalizes the file, and sends `file_result`.

Phone to PC:

1. Android selects a file and opens RFCOMM to Linux.
2. Android sends `file_offer`.
3. Linux validates and sends `file_accept` or `file_reject`.
4. Android streams chunks and sends `file_complete`.
5. Linux verifies and sends `file_result`.

### 9.5 Limits and Timeouts

| Item | Value |
| --- | --- |
| Default maximum file size | 100 MiB |
| Configurable range | 1-1024 MiB |
| Chunk payload | 64 KiB |
| Offer response timeout | 30 seconds |
| Chunk inactivity timeout | 60 seconds |
| Verification timeout | 30 seconds |

### 9.6 File Name Rules

- Use only the final path component supplied by the sender.
- Reject empty names, `.`, `..`, path separators, NUL, and control characters.
- Trim leading/trailing whitespace and trailing dots.
- Limit the name to 255 UTF-8 bytes, preserving the extension where possible.
- If the name exists, append ` (1)`, ` (2)`, and so on before the extension.
- Write to a temporary name (`.part` on Linux, `IS_PENDING = 1` on Android) and
  only publish the final name after successful verification.

## 10. Clipboard Behavior

### 10.1 Data

`ClipboardSnapshot` contains:

- `text`: string;
- `sensitive`: boolean.

Rules:

- Only non-empty text is eligible.
- Maximum size is 64 KiB UTF-8.
- Sensitive text is never sent and never applied.
- The service remembers `last_sent` and `last_received` to suppress echo.
- Normalize nothing except invalid NUL characters; preserve line endings.
- Clipboard changes while the peer is offline are not queued in MVP. The UI
  shows the offline state, and only changes made after reconnection are sent.

### 10.2 Linux Clipboard Watching

Wayland (primary):

- Use `wl-clipboard` (`wl-paste --watch`).
- Detect the `x-kde-passwordManagerHint` MIME type and mark the snapshot
  sensitive.
- If `wl-paste --watch` is unavailable, fall back to polling every 0.5 seconds.

X11 (fallback):

- Poll `xclip -selection clipboard -o -target UTF8_STRING` every 0.5 seconds.
- Read `TARGETS` when needed to detect the KDE password-manager marker.
- If neither provider is available, report `clipboard_unavailable` and keep the
  connection alive.

The watcher emits changes; it does not decide whether text should be sent.

### 10.3 Android Reading

- In-app button: reading is allowed while the Activity is focused.
- The button reads the current clipboard, applies sensitivity/size checks, and
  sends a clipboard frame through the service.
- If reading is unavailable, show a message explaining the Android restriction.

### 10.4 Android Writing

- Incoming text is written with `ClipboardManager.setPrimaryClip`.
- Android 13+ may show a system clipboard preview; this is expected.
- Writing must work while the foreground service is alive, even if the Activity
  is not visible.

### 10.5 IME (Post-MVP)

- `InputMethodService` separate from the main Activity.
- Must be selected as the default keyboard for background clipboard reads.
- Reads the clipboard, skips password fields (`TYPE_TEXT_VARIATION_PASSWORD`,
  `TYPE_TEXT_VARIATION_VISIBLE_PASSWORD`, `TYPE_NUMBER_VARIATION_PASSWORD`).
- Skips clips marked sensitive by Android 13+ metadata.
- Forwards text to the foreground service over a local Binder; the IME does not
  own Bluetooth.
- The service applies the same size/sensitivity/echo rules.
- The app provides a setup screen that opens the system IME settings and
  explains the privacy trade-off.
- The IME must not build a history or log clipboard text.

## 11. Connection and Transfer State Machines

### 11.1 Linux BLE Central

```text
stopped -> scanning -> connecting -> connected
                ^          |            |
                |          v            v
                +------- backoff <-- disconnected
```

- `stopped`: user disabled sync or app quitting.
- `scanning`: looking for the service UUID.
- `connecting`: GATT connect plus service/characteristic discovery.
- `connected`: hello exchanged, heartbeat running.
- `backoff`: waiting before the next scan.
- Errors move to `backoff` and surface a user-visible status.

### 11.2 Android BLE Peripheral

```text
stopped -> advertising -> connected
                ^             |
                +-------------+
```

- `advertising`: service enabled, no central connected.
- `connected`: at least one central; advertising stopped.
- On disconnect, return to `advertising`.
- Only bonded peers are accepted.

### 11.3 File Transfer

```text
idle -> offering -> awaiting_accept -> sending/receiving -> verifying -> completed
  |         |              |                |                  |
  +---------+--------------+----------------+------------------+--> failed/cancelled
```

- `failed` and `cancelled` are terminal for a transfer and clean up partial data.
- The UI observes progress events derived from bytes transferred and total size.
- Cancellation is user-initiated from either side.

### 11.4 Error Handling

- Adapters raise typed exceptions.
- `AppController` converts exceptions to a user-facing state plus an error code.
- The UI never displays raw platform exceptions.
- Link errors trigger reconnect; file errors abort only the current transfer.

## 12. Platform Details

### 12.1 Linux

Dependencies:

- `PySide6` and `qasync` for the GUI and a shared asyncio/Qt event loop.
- `dbus-next` for BlueZ pairing and profile registration.
- `bleak` for BLE scanning and the GATT client.
- `wl-clipboard` or `xclip` for clipboard access.

Behavior:

- The tray application is the long-running process. It owns the BLE central,
  clipboard watcher, RFCOMM server, and settings.
- Closing the settings window does not stop synchronization.
- Quit stops the RFCOMM server, disconnects BLE, and exits.
- A single instance is expected. A second launch should focus the existing tray
  icon rather than start a second transport session.
- Start-at-login uses an XDG autostart `.desktop` file. The toggle is optional in
  MVP but the path is documented.

Configuration:

- Settings: `$XDG_CONFIG_HOME/bleconnect/settings.json` (default
  `~/.config/bleconnect/settings.json`).
- Trusted devices: `$XDG_CONFIG_HOME/bleconnect/trusted_devices.json`.
- Default download directory: `~/Downloads/bleconnect`.

The BLE adapter must select the local adapter explicitly when several adapters
exist (configurable, default first powered adapter).

### 12.2 Android

Native bridge responsibilities (thin platform primitives only):

- BLE advertising and GATT server.
- RFCOMM client socket.
- Clipboard read/write.
- MediaStore Downloads insert/update/delete.
- MediaPlayer find-phone sound and volume control.
- Foreground service lifecycle and notification.
- SAF file picker result handling.

No protocol logic belongs in the native bridge. The bridge exposes callbacks to
Python; protocol parsing, reassembly, transfer state, and validation stay in
Python so both platforms share behavior.

Kivy UI to service:

- The Activity binds to the foreground service through a small Binder interface
  exposed via pyjnius.
- Commands: start/stop synchronization, send clipboard, send a selected file,
  cancel a transfer, find phone, and update settings.
- The service emits state and progress callbacks; Kivy marshals them to the UI
  thread with `Clock.schedule_once`.

Event-loop integration:

- Asyncio runs in a background thread or service loop.
- Kivy updates are scheduled on the Kivy main thread with `Clock.schedule_once`.
- Java callbacks are marshalled to asyncio with `call_soon_threadsafe`.

Permissions and manifest:

- `BLUETOOTH_CONNECT` (Android 12+).
- `BLUETOOTH_ADVERTISE` (Android 12+).
- `BLUETOOTH_SCAN` only if scanning is added later; if declared, use
  `neverForLocation` where applicable.
- `POST_NOTIFICATIONS` (Android 13+).
- `FOREGROUND_SERVICE` and `FOREGROUND_SERVICE_CONNECTED_DEVICE` (Android 14+).
- Service declaration with `android:foregroundServiceType="connectedDevice"`.
- `ACCESS_NOTIFICATION_POLICY` is optional and only for bypassing Do Not Disturb
  when the user grants it.
- Battery optimization: guide the user to exempt BLEConnect; do not silently
  assume background reliability.

Foreground service:

- `START_STICKY`.
- Persistent notification with connection status.
- Holds the BLE peripheral and RFCOMM client.
- Keeps the clipboard and sound adapters alive.
- Stops when the user disables synchronization or explicitly stops the service.

Storage:

- Android 10+: MediaStore Downloads with
  `RELATIVE_PATH = Environment.DIRECTORY_DOWNLOADS + "/bleconnect"`.
- Insert with `IS_PENDING = 1`; set `IS_PENDING = 0` only after verification.
- Delete the pending item on failure.
- Android 9 and below, if supported, use the legacy downloads path with the
  appropriate storage permission.

Find phone sound:

- Bundled asset, played by `MediaPlayer`.
- Default duration 30 seconds; maximum 120 seconds.
- Volume target 1.0 on `STREAM_MUSIC`.
- Save the current stream volume and restore it when playback stops.
- `setStreamVolume` may fail under Do Not Disturb; fall back to the current
  volume and show a notification.
- `find_phone_stop` stops playback immediately and restores the saved volume.

### 12.3 Android Background Spike (M0)

The concrete spike lives in `android/spike/`; `tools/ble_spike_client.py`
writes test data from Linux. Before implementing the MVP, prove that:

- A foreground service can be started from the Kivy app.
- The Python asyncio loop survives with the screen off for at least 30 minutes.
- BLE advertising and a GATT server work through a thin pyjnius bridge.
- A test write is received and written to the clipboard while no Activity is
  visible.
- The service stops cleanly from the UI.

If the spike fails, fall back to a Kotlin foreground service. In that case the
protocol and transfer logic move to Kotlin or are exposed as a small native relay;
record the decision in `docs/architecture.md`.

## 13. Settings and Data Model

### 13.1 Settings

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `clipboard_enabled` | bool | true | Pause/resume clipboard sync |
| `download_dir` | string | `~/Downloads/bleconnect` | Linux only |
| `max_file_size_mib` | int | 100 | 1-1024 |
| `find_phone_duration_s` | float | 30 | 1-120 |
| `find_phone_volume` | float | 1.0 | 0.0-1.0 |
| `start_at_login` | bool | false | Linux autostart |
| `peer_address` | string | empty | Last trusted peer |
| `ble_adapter` | string | empty | Optional Linux adapter path/name |

Settings are stored as JSON and written atomically (temporary file, fsync,
rename, mode 0600 on Linux).

### 13.2 Trusted Devices

- Address is canonicalized to uppercase colon-separated form on Linux.
- Name is a display hint only; the address is authoritative.
- Linux stores trusted devices in JSON.
- Android uses the OS bonded-device list plus a stored last-peer address.

## 14. Error Codes

| Code | Meaning | User action |
| --- | --- | --- |
| `unsupported_version` | Protocol version mismatch | Update the app |
| `not_trusted` | Peer is not bonded/trusted | Pair the device |
| `busy` | Another transfer is active | Wait or cancel |
| `file_too_large` | Exceeds the configured limit | Raise the limit or choose another file |
| `no_space` | Not enough disk space | Free space |
| `invalid_name` | File name rejected | Rename the file |
| `invalid_offset` | Chunk offset mismatch | Retry the transfer |
| `hash_mismatch` | SHA-256 verification failed | Retry the transfer |
| `cancelled` | User cancelled | None |
| `timeout` | Peer stopped responding | Reconnect |
| `clipboard_unavailable` | Clipboard provider/read failed | Check permissions/session |
| `ble_unavailable` | No BLE adapter or advertising failure | Check Bluetooth |
| `rfcomm_failed` | RFCOMM connect/register failed | Check pairing |

Errors are mapped to localized UI strings in one place per UI.

## 15. Security and Privacy

### 15.1 Trust Model

- OS-level bonding is the authentication mechanism.
- BLE characteristics require encryption; Linux and Android must pair before
  data exchange.
- Linux verifies the RFCOMM peer address against the trusted list.
- Android verifies `BOND_BONDED` before accepting GATT operations.
- Unknown peers are rejected without revealing clipboard or file data.

### 15.2 Clipboard Privacy

- Never log clipboard text, file contents, or file names at info level.
- Sensitive text is skipped:
  - KDE `x-kde-passwordManagerHint`;
  - Android `ClipDescription.EXTRA_IS_SENSITIVE`;
  - IME password input types.
- The user can pause synchronization at any time.
- Advertising contains no user data.

### 15.3 File Safety

- Sanitize names and store only inside the configured directory.
- Reject absolute paths and `..`.
- Verify size, offset, and SHA-256.
- Do not overwrite existing files.
- Delete partial files on failure.

### 15.4 Out of Scope

- Protection against a malicious paired device.
- App-level encryption beyond the Bluetooth link.
- Hiding metadata such as file size or transfer timing.

## 16. Testing Strategy

### 16.1 Unit Tests (No Hardware)

- BLE frame encode/decode, chunking, reassembly, duplicate suppression, and
  timeouts.
- RFCOMM v2 frame encode/decode and limit validation.
- Clipboard service: sensitive/empty/oversize handling, echo suppression.
- File transfer service: offer/accept/reject, offsets, hash mismatch, cancel.
- File name sanitization and collision suffixing.
- Settings/trusted-device repositories: atomic writes, malformed JSON.
- State machines: valid and invalid transitions.
- Error code mapping.

### 16.2 Integration Tests (No Bluetooth)

- In-memory `PacketLink` with BLE-like chunking for clipboard and control.
- TCP-based `PacketLink` for RFCOMM file framing.
- Two sessions exchanging clipboard text in both directions.
- File transfer in both directions, including cancel and hash mismatch.
- Reconnect/backoff with a simulated link loss.
- Ensure no echo and no duplicate application of text.

### 16.3 Hardware Tests

- Linux ↔ Android BLE scan/connect/reconnect.
- Clipboard Linux to Android automatically.
- Clipboard Android to Linux via button and IME.
- File transfer in both directions, including a ~100 MiB file.
- Find phone, including screen off and Do Not Disturb.
- Behavior after Bluetooth toggle and airplane mode.
- Behavior after Android process kill and service restart.

Mark hardware tests as `@pytest.mark.hardware`; CI runs only unit and integration
tests. Report which hardware checks were actually run when changing behavior.

### 16.4 Manual Matrix

| Scenario | Expected |
| --- | --- |
| Fresh pair, start apps | Connected, status visible |
| Copy text on Linux | Appears on Android |
| Send clipboard from Android | Appears on Linux |
| Sensitive text | Not sent |
| Send 5 MiB file each way | Saved, hash OK |
| Cancel mid-transfer | Partial file removed |
| Kill Android service | Linux shows offline, reconnects |
| Enable DND, find phone | Sound or clear fallback message |
| Disable clipboard sync | No text exchanged |

## 17. Roadmap

| Milestone | Deliverable |
| --- | --- |
| M0 | This specification; Android background spike |
| M1 | Core protocol, ports, state machines, integration tests over fake links |
| M2 | Linux BLE central, clipboard watcher, RFCOMM file server, trusted filter |
| M3 | Linux tray app and settings window (PySide6 + qasync) |
| M4 | Android Kivy UI, foreground service, GATT server, RFCOMM client, file storage, find phone |
| M5 | IME for background Android-to-Linux clipboard |
| M6 | Hardening: reconnect, battery, error UX, hardware matrix |

The exact order of M2-M4 may overlap, but core/protocol work (M1) must land before
platform adapters.

## 18. Risks and Open Questions

### 18.1 Risks

- **Android background Python service** may be unreliable across vendors. M0
  spike must validate it; Kotlin service is the fallback.
- **BLE GATT server reliability** varies by Android device. Some devices limit
  advertising or disconnect aggressively.
- **MTU negotiation** may be poor; clipboard chunking must still work with a
  small MTU.
- **Android clipboard restriction** makes true background phone-to-Linux syncing
  impossible without an IME as the default keyboard.
- **RFCOMM throughput** makes 100 MiB transfers slow; progress and cancellation
  are essential.
- **Do Not Disturb and volume policy** may prevent maximum-volume find-phone.
- **Aggressive battery savers** may kill the service; the app must guide the user.
- **BlueZ version differences** may affect profile registration and GATT client
  behavior.

### 18.2 Open Questions

- Should the app support multiple trusted devices concurrently after MVP?
- Should start-at-login be enabled by default on Linux?
- Should Android receive files through the system share sheet in addition to the
  in-app picker?
- Which bundled find-phone sound and default duration are preferred?
- Should clipboard synchronization include a short preview in notifications?
- What is the minimum Android API level supported by the chosen Kivy toolchain?

## 19. Appendix: Protocol Examples

### 19.1 BLE Clipboard Frame

Header for a single-chunk clipboard message:

```text
01 02 00 00 00 07 00 00 00 01
```

- version `01`
- type `02` (clipboard)
- message_id `00000007`
- chunk_index `0000`
- chunk_count `0001`

The payload follows the header.

### 19.2 BLE Control Frame

```text
01 01 00 00 00 08 00 00 00 01
```

Payload:

```json
{"type":"find_phone","body":{"duration_s":30,"volume":1.0}}
```

### 19.3 RFCOMM File Offer

Header JSON (length-prefixed by the v2 frame):

```json
{
  "version": 2,
  "type": "file_offer",
  "body": {
    "transfer_id": "8e4b7c1e-6f11-4f6e-9f3a-1c2d3e4f5a6b",
    "name": "screenshot.png",
    "size": 245760,
    "mime": "image/png"
  }
}
```

### 19.4 RFCOMM Chunk Header

```json
{
  "version": 2,
  "type": "file_chunk",
  "body": {
    "transfer_id": "8e4b7c1e-6f11-4f6e-9f3a-1c2d3e4f5a6b",
    "offset": 65536
  }
}
```

The payload contains the next 64 KiB of file data.

## 20. Glossary

- **ATT**: Attribute Protocol, the BLE transport for GATT operations.
- **GATT**: Generic Attribute Profile; BLE services and characteristics.
- **RFCOMM**: Bluetooth Classic serial-port profile; provides a byte stream.
- **MTU**: Maximum transmission unit for an ATT packet.
- **SAF**: Android Storage Access Framework; used for file picking.
- **MediaStore**: Android content provider for shared media and Downloads.
- **IME**: Input Method Editor; Android keyboard service.
