# BLEConnect M0 Spike

This is the M0 proof-of-concept from `docs/spec.md`: a Python foreground service
on Android that survives with the screen off, hosts a BLE GATT server, receives
writes, and updates the Android clipboard. A thin Java class owns only the
Android Bluetooth primitives; Python owns the service lifecycle, logging, and
clipboard behavior.

## What the spike proves

- A p4a foreground service can keep Python alive while the Activity is hidden.
- Python can receive Java GATT callbacks through pyjnius.
- Python can write the Android clipboard from a service.
- The Linux side can discover, connect, and write to the phone over BLE.

The spike intentionally uses unencrypted GATT characteristics to reduce failure
modes. Production will require bonded/encrypted characteristics per the spec.

## Prerequisites

- JDK 17 (`JAVA_HOME`).
- Android SDK with platform 34 and build-tools 34.
- Android NDK 25b (`25.2.9519653`).
- Buildozer running under Python 3.11 or 3.12.
- An Android 12+ device with USB debugging.

Example setup on Fedora:

```sh
# JDK 17 via sdkman
source ~/.sdkman/bin/sdkman-init.sh
sdk install java 17.0.20-amzn

# Android NDK
yes | "$HOME/android-sdk/cmdline-tools/latest/bin/sdkmanager" "ndk;25.2.9519653"

# Buildozer in its own Python 3.11 environment
uv tool install --python 3.11 buildozer==1.5.0
```

## Build

```sh
cd android/spike
export ANDROID_HOME="$HOME/android-sdk"
export ANDROID_NDK_HOME="$HOME/android-sdk/ndk/25.2.9519653"
export JAVA_HOME="$HOME/.sdkman/candidates/java/17.0.20-amzn"
buildozer -v android debug
```

The APK is written under `bin/`.

## Install and run

```sh
adb install -r bin/spike-0.1-arm64-v8a-debug.apk
adb shell am start -n org.bleconnect.spike/org.kivy.android.PythonActivity
```

In the app:

1. Tap **Request permissions** and grant Bluetooth and notification access.
2. Tap **Start service**.
3. Turn the screen off or move the app to the background.
4. Run the Linux client from the repository root:

```sh
uv sync --extra linux
uv run python tools/ble_spike_client.py "hello from linux"
```

Expected results:

- The Linux client finds the `BLEConnect` advertisement, reads the info
  characteristic, receives a `pong` indication, and writes clipboard text.
- The phone clipboard contains `hello from linux`.
- `spike.log` contains GATT, clipboard, and heartbeat entries.

## Logs

```sh
adb logcat | grep -E "BleSpike|python"
adb pull /sdcard/Android/data/org.bleconnect.spike/files/spike.log
```

The in-app **Refresh log** button shows the same file.

## Acceptance checklist

- [ ] APK installs and the service starts from the Kivy UI.
- [ ] Service logs a heartbeat after at least 30 minutes with the screen off.
- [ ] Linux client discovers the BLE service by UUID.
- [ ] A control write produces a `pong` indication.
- [ ] A clipboard write updates the Android clipboard.
- [ ] Service stops cleanly from the UI.
- [ ] `adb logcat` shows no Python crash.

## Notes and limitations

- GATT permissions are unencrypted here; do not ship this configuration.
- The service has no graceful shutdown path in the spike; stopping it kills the
  process and the GATT server.
- Clipboard writes from a foreground service are allowed on Android 10+; reading
  the clipboard in the background remains restricted and is handled by the IME
  in the production design.
- If the service is killed by a vendor battery manager, exempt the app from
  battery optimization for the 30-minute test.
