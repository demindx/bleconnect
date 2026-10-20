[app]
title = BLEConnect M0 Spike
package.name = spike
package.domain = org.bleconnect
source.dir = .
source.include_exts = py,java,txt,md
source.exclude_dirs = .buildozer,bin,__pycache__,.git
version = 0.1

requirements = python3,kivy,pyjnius,android
orientation = portrait
fullscreen = 0

services = bleconnect:service.py:foreground:sticky:foregroundServiceType=connectedDevice

android.permissions = BLUETOOTH, BLUETOOTH_ADMIN, BLUETOOTH_CONNECT, BLUETOOTH_ADVERTISE, FOREGROUND_SERVICE, FOREGROUND_SERVICE_CONNECTED_DEVICE, POST_NOTIFICATIONS
android.api = 34
android.minapi = 31
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
android.add_src = java
android.logcat_filters = *:S python:D BleSpike:D
p4a.local_recipes = ../p4a-recipes

[buildozer]
log_level = 2
warn_on_root = 1
