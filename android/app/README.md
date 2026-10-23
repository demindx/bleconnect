# BLEConnect Android App

Production Android service and Kivy UI for BLEConnect. The service owns the BLE
peripheral, clipboard writes, find-phone playback, and a local JSON control
server. Protocol framing and application behavior live in the shared
`bleconnect` package through the `bleconnect` symlink.

## Current slice

- BLE peripheral with info/control/clipboard characteristics and encrypted GATT
  permissions.
- PC-to-phone clipboard writes.
- Phone-to-PC clipboard sending from the UI button.
- Find-phone playback with volume restore.
- Kivy status, pause/resume, send-clipboard, find-phone test, and log view.
- Unix-socket control server in the app's private files directory for the
  UI/service split (`daemon.sock`).

File transfer (RFCOMM) is not wired in this slice yet; the service replies with
`not_implemented` for `file_incoming`. The Linux RFCOMM receive path is ready.

## Build

Prerequisites are the same as `android/spike`: JDK 17, Android SDK 34,
NDK 25b, `autoconf`, `automake`, `libtool`, and `tcl`.

```sh
cd android/app
export ANDROID_HOME="$HOME/android-sdk"
export ANDROID_NDK_HOME="$HOME/android-sdk/ndk/25.2.9519653"
export JAVA_HOME="$HOME/.sdkman/candidates/java/17.0.20-amzn"
buildozer -v android debug
```

The local `../p4a-recipes/sqlite3` recipe is used automatically via
`p4a.local_recipes`; it fixes host toolchain/Tcl issues without patching
`.buildozer` by hand.

## Install and run

```sh
adb install -r bin/app-0.1-arm64-v8a-debug.apk
adb shell am start -n org.bleconnect.app/org.kivy.android.PythonActivity
```

In the app:

1. Tap **Request permissions** and grant Bluetooth and notifications.
2. Tap **Start service**.
3. Pair/bond the Linux host if required by the encrypted GATT characteristics.
4. Use `uv run bleconnect ble-scan` from the repository root to verify discovery.

The service log is at
`/sdcard/Android/data/org.bleconnect.app/files/service.log`.

## Notes

- The GATT characteristics use encrypted permissions. Linux must bond with the
  phone before reading or writing; the production design keeps the OS pairing
  agent as the trust boundary.
- The control socket is app-private and accessible only to the app's own
  processes (UI, service, and future IME).
- Clipboard reads from the service are best-effort because Android restricts
  background clipboard access; the UI sends the clipboard while focused.
- The full 30-minute screen-off soak is still pending and tracked in #3.
