package org.bleconnect.spike;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattServer;
import android.bluetooth.BluetoothGattServerCallback;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.le.AdvertiseCallback;
import android.bluetooth.le.AdvertiseData;
import android.bluetooth.le.AdvertiseSettings;
import android.bluetooth.le.BluetoothLeAdvertiser;
import android.content.Context;
import android.os.ParcelUuid;
import android.util.Log;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.UUID;

/**
 * Minimal Android BLE peripheral used by the M0 background-service spike.
 *
 * This class is intentionally thin: it owns the Android GATT/advertising
 * primitives and forwards payloads to a Python listener. Protocol decisions and
 * clipboard writes stay in Python.
 */
public final class BleSpikeBridge {
    private static final String TAG = "BleSpike";

    public static final UUID SERVICE_UUID = UUID.fromString("d37b4a31-8e74-4f36-9a01-7d3a8f7c2b10");
    public static final UUID INFO_UUID = UUID.fromString("d37b4a32-8e74-4f36-9a01-7d3a8f7c2b10");
    public static final UUID CONTROL_UUID = UUID.fromString("d37b4a33-8e74-4f36-9a01-7d3a8f7c2b10");
    public static final UUID CLIPBOARD_UUID = UUID.fromString("d37b4a34-8e74-4f36-9a01-7d3a8f7c2b10");
    private static final UUID CCCD_UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");

    public interface Listener {
        void onLog(String message);
        void onClipboardText(String text);
        void onControlMessage(String text);
    }

    private final Context context;
    private final Listener listener;
    private BluetoothGattServer server;
    private BluetoothLeAdvertiser advertiser;
    private AdvertiseCallback advertiseCallback;
    private BluetoothDevice connectedDevice;
    private BluetoothGattCharacteristic controlCharacteristic;
    private BluetoothGattCharacteristic clipboardCharacteristic;

    public BleSpikeBridge(Context context, Listener listener) {
        this.context = context;
        this.listener = listener;
    }

    public void start() {
        BluetoothManager manager = (BluetoothManager) context.getSystemService(Context.BLUETOOTH_SERVICE);
        BluetoothAdapter adapter = manager == null ? null : manager.getAdapter();
        if (adapter == null || !adapter.isEnabled()) {
            log("Bluetooth adapter is unavailable or disabled");
            return;
        }

        advertiser = adapter.getBluetoothLeAdvertiser();
        if (advertiser == null) {
            log("BLE advertising is unavailable on this device");
            return;
        }

        BluetoothGattService service = new BluetoothGattService(
                SERVICE_UUID, BluetoothGattService.SERVICE_TYPE_PRIMARY);
        BluetoothGattCharacteristic info = new BluetoothGattCharacteristic(
                INFO_UUID,
                BluetoothGattCharacteristic.PROPERTY_READ,
                BluetoothGattCharacteristic.PERMISSION_READ);
        info.setValue(
                "{\"protocol\":1,\"device_name\":\"Android spike\",\"capabilities\":[\"clipboard\"]}"
                        .getBytes(StandardCharsets.UTF_8));

        controlCharacteristic = new BluetoothGattCharacteristic(
                CONTROL_UUID,
                BluetoothGattCharacteristic.PROPERTY_WRITE
                        | BluetoothGattCharacteristic.PROPERTY_INDICATE,
                BluetoothGattCharacteristic.PERMISSION_WRITE);
        clipboardCharacteristic = new BluetoothGattCharacteristic(
                CLIPBOARD_UUID,
                BluetoothGattCharacteristic.PROPERTY_WRITE
                        | BluetoothGattCharacteristic.PROPERTY_INDICATE,
                BluetoothGattCharacteristic.PERMISSION_WRITE);
        controlCharacteristic.addDescriptor(cccd());
        clipboardCharacteristic.addDescriptor(cccd());

        service.addCharacteristic(info);
        service.addCharacteristic(controlCharacteristic);
        service.addCharacteristic(clipboardCharacteristic);

        server = manager.openGattServer(context, serverCallback);
        if (server == null) {
            log("Could not open the GATT server");
            return;
        }
        if (!server.addService(service)) {
            log("Could not add the GATT service");
            return;
        }
        log("GATT service added");

        AdvertiseSettings settings = new AdvertiseSettings.Builder()
                .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_BALANCED)
                .setConnectable(true)
                .setTimeout(0)
                .build();
        AdvertiseData data = new AdvertiseData.Builder()
                .addServiceUuid(new ParcelUuid(SERVICE_UUID))
                .build();
        advertiseCallback = new AdvertiseCallback() {
            @Override
            public void onStartSuccess(AdvertiseSettings settingsInEffect) {
                log("Advertising started");
            }

            @Override
            public void onStartFailure(int errorCode) {
                log("Advertising failed: " + errorCode);
            }
        };
        advertiser.startAdvertising(settings, data, advertiseCallback);
    }

    private BluetoothGattDescriptor cccd() {
        BluetoothGattDescriptor descriptor = new BluetoothGattDescriptor(
                CCCD_UUID,
                BluetoothGattDescriptor.PERMISSION_READ
                        | BluetoothGattDescriptor.PERMISSION_WRITE);
        descriptor.setValue(BluetoothGattDescriptor.ENABLE_INDICATION_VALUE);
        return descriptor;
    }

    private final BluetoothGattServerCallback serverCallback = new BluetoothGattServerCallback() {
        @Override
        public void onConnectionStateChange(BluetoothDevice device, int status, int newState) {
            connectedDevice = newState == BluetoothGatt.STATE_CONNECTED ? device : null;
            log("Connection state=" + newState + " device="
                    + (device == null ? "null" : device.getAddress()));
        }

        @Override
        public void onMtuChanged(BluetoothDevice device, int mtu) {
            log("MTU changed: " + mtu);
        }

        @Override
        public void onCharacteristicReadRequest(
                BluetoothDevice device,
                int requestId,
                int offset,
                BluetoothGattCharacteristic characteristic) {
            byte[] value = characteristic.getValue();
            if (value == null) {
                value = new byte[0];
            }
            byte[] response = offset >= value.length
                    ? new byte[0]
                    : Arrays.copyOfRange(value, offset, value.length);
            server.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, response);
            log("Read " + characteristic.getUuid());
        }

        @Override
        public void onCharacteristicWriteRequest(
                BluetoothDevice device,
                int requestId,
                BluetoothGattCharacteristic characteristic,
                boolean preparedWrite,
                boolean responseNeeded,
                int offset,
                byte[] value) {
            String text = value == null ? "" : new String(value, StandardCharsets.UTF_8);
            log("Write " + characteristic.getUuid() + " offset=" + offset + " value=" + text);
            if (responseNeeded) {
                server.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, value);
            }
            if (CONTROL_UUID.equals(characteristic.getUuid())) {
                safeControl(text);
            } else if (CLIPBOARD_UUID.equals(characteristic.getUuid())) {
                safeClipboard(text);
            }
        }

        @Override
        public void onDescriptorWriteRequest(
                BluetoothDevice device,
                int requestId,
                BluetoothGattDescriptor descriptor,
                boolean preparedWrite,
                boolean responseNeeded,
                int offset,
                byte[] value) {
            log("Descriptor write " + descriptor.getUuid());
            if (responseNeeded) {
                server.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, value);
            }
        }

        @Override
        public void onDescriptorReadRequest(
                BluetoothDevice device,
                int requestId,
                int offset,
                BluetoothGattDescriptor descriptor) {
            byte[] value = descriptor.getValue();
            if (value == null) {
                value = new byte[0];
            }
            byte[] response = offset >= value.length
                    ? new byte[0]
                    : Arrays.copyOfRange(value, offset, value.length);
            server.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, response);
        }
    };

    public void sendControl(String text) {
        sendIndication(controlCharacteristic, text);
    }

    public void sendClipboard(String text) {
        sendIndication(clipboardCharacteristic, text);
    }

    private void sendIndication(BluetoothGattCharacteristic characteristic, String text) {
        if (server == null || connectedDevice == null || characteristic == null) {
            log("Cannot notify: no active GATT connection");
            return;
        }
        characteristic.setValue(text.getBytes(StandardCharsets.UTF_8));
        boolean queued = server.notifyCharacteristicChanged(
                connectedDevice, characteristic, true);
        log("Indication queued=" + queued + " value=" + text);
    }

    public void stop() {
        try {
            if (advertiser != null && advertiseCallback != null) {
                advertiser.stopAdvertising(advertiseCallback);
            }
        } catch (Exception exception) {
            log("stopAdvertising failed: " + exception);
        }
        try {
            if (server != null) {
                server.close();
            }
        } catch (Exception exception) {
            log("GATT close failed: " + exception);
        }
        server = null;
        advertiser = null;
        advertiseCallback = null;
        connectedDevice = null;
        log("Stopped");
    }

    private void safeControl(String text) {
        try {
            listener.onControlMessage(text);
        } catch (Exception exception) {
            Log.e(TAG, "control listener failed", exception);
        }
    }

    private void safeClipboard(String text) {
        try {
            listener.onClipboardText(text);
        } catch (Exception exception) {
            Log.e(TAG, "clipboard listener failed", exception);
        }
    }

    private void log(String message) {
        Log.i(TAG, message);
        try {
            listener.onLog(message);
        } catch (Exception exception) {
            Log.e(TAG, "log listener failed", exception);
        }
    }
}
