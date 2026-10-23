package org.bleconnect.app;

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
 * Thin Android BLE peripheral bridge. It owns advertising and GATT primitives
 * only; framing, clipboard policy, and transfer state live in Python.
 */
public final class BlePeripheralBridge {
    private static final String TAG = "BlePeripheral";

    public static final UUID SERVICE_UUID = UUID.fromString("d37b4a31-8e74-4f36-9a01-7d3a8f7c2b10");
    public static final UUID INFO_UUID = UUID.fromString("d37b4a32-8e74-4f36-9a01-7d3a8f7c2b10");
    public static final UUID CONTROL_UUID = UUID.fromString("d37b4a33-8e74-4f36-9a01-7d3a8f7c2b10");
    public static final UUID CLIPBOARD_UUID = UUID.fromString("d37b4a34-8e74-4f36-9a01-7d3a8f7c2b10");
    private static final UUID CCCD_UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");

    public interface Listener {
        void onLog(String message);

        void onControlWrite(byte[] data);

        void onClipboardWrite(byte[] data);

        void onConnectionState(int state);

        void onMtuChanged(int mtu);
    }

    private final Context context;
    private final Listener listener;
    private BluetoothGattServer server;
    private BluetoothLeAdvertiser advertiser;
    private AdvertiseCallback advertiseCallback;
    private BluetoothDevice connectedDevice;
    private BluetoothGattCharacteristic controlCharacteristic;
    private BluetoothGattCharacteristic clipboardCharacteristic;
    private boolean advertising;

    public BlePeripheralBridge(Context context, Listener listener) {
        this.context = context;
        this.listener = listener;
    }

    public void start() {
        try {
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
                    BluetoothGattCharacteristic.PERMISSION_READ_ENCRYPTED);
            info.setValue(
                    "{\"protocol\":1,\"device_name\":\"BLEConnect Android\","
                            + "\"capabilities\":[\"clipboard\",\"file\",\"find_phone\"]}"
                            .getBytes(StandardCharsets.UTF_8));

            controlCharacteristic = new BluetoothGattCharacteristic(
                    CONTROL_UUID,
                    BluetoothGattCharacteristic.PROPERTY_WRITE
                            | BluetoothGattCharacteristic.PROPERTY_INDICATE,
                    BluetoothGattCharacteristic.PERMISSION_WRITE_ENCRYPTED);
            clipboardCharacteristic = new BluetoothGattCharacteristic(
                    CLIPBOARD_UUID,
                    BluetoothGattCharacteristic.PROPERTY_WRITE
                            | BluetoothGattCharacteristic.PROPERTY_INDICATE,
                    BluetoothGattCharacteristic.PERMISSION_WRITE_ENCRYPTED);
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
            startAdvertising();
        } catch (SecurityException exception) {
            log("Bluetooth permission is missing: " + exception.getMessage());
        } catch (Exception exception) {
            log("Could not start the BLE peripheral: " + exception);
        }
    }

    private BluetoothGattDescriptor cccd() {
        BluetoothGattDescriptor descriptor = new BluetoothGattDescriptor(
                CCCD_UUID,
                BluetoothGattDescriptor.PERMISSION_READ
                        | BluetoothGattDescriptor.PERMISSION_WRITE);
        descriptor.setValue(BluetoothGattDescriptor.ENABLE_INDICATION_VALUE);
        return descriptor;
    }

    private void startAdvertising() {
        if (advertiser == null || advertising) {
            return;
        }
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
                advertising = true;
                log("Advertising started");
            }

            @Override
            public void onStartFailure(int errorCode) {
                advertising = false;
                log("Advertising failed: " + errorCode);
            }
        };
        advertiser.startAdvertising(settings, data, advertiseCallback);
    }

    private void stopAdvertising() {
        if (advertiser == null || advertiseCallback == null) {
            return;
        }
        try {
            advertiser.stopAdvertising(advertiseCallback);
        } catch (Exception exception) {
            log("stopAdvertising failed: " + exception);
        }
        advertiseCallback = null;
        advertising = false;
    }

    private final BluetoothGattServerCallback serverCallback = new BluetoothGattServerCallback() {
        @Override
        public void onConnectionStateChange(BluetoothDevice device, int status, int newState) {
            if (newState == BluetoothGatt.STATE_CONNECTED) {
                connectedDevice = device;
                stopAdvertising();
            } else {
                connectedDevice = null;
                startAdvertising();
            }
            log("Connection state=" + newState + " device="
                    + (device == null ? "null" : device.getAddress()));
            safeConnectionState(newState);
        }

        @Override
        public void onMtuChanged(BluetoothDevice device, int mtu) {
            log("MTU changed: " + mtu);
            safeMtu(mtu);
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
            byte[] data = value == null ? new byte[0] : value;
            log("Write " + characteristic.getUuid() + " offset=" + offset
                    + " length=" + data.length);
            if (responseNeeded) {
                server.sendResponse(device, requestId, BluetoothGatt.GATT_SUCCESS, offset, data);
            }
            if (CONTROL_UUID.equals(characteristic.getUuid())) {
                safeControl(data);
            } else if (CLIPBOARD_UUID.equals(characteristic.getUuid())) {
                safeClipboard(data);
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

    public boolean sendControl(byte[] data) {
        return sendIndication(controlCharacteristic, data);
    }

    public boolean sendClipboard(byte[] data) {
        return sendIndication(clipboardCharacteristic, data);
    }

    private boolean sendIndication(BluetoothGattCharacteristic characteristic, byte[] data) {
        if (server == null || connectedDevice == null || characteristic == null) {
            log("Cannot notify: no active GATT connection");
            return false;
        }
        characteristic.setValue(data);
        boolean queued = server.notifyCharacteristicChanged(
                connectedDevice, characteristic, true);
        log("Indication queued=" + queued + " length=" + data.length);
        return queued;
    }

    public void stop() {
        stopAdvertising();
        try {
            if (server != null) {
                server.close();
            }
        } catch (Exception exception) {
            log("GATT close failed: " + exception);
        }
        server = null;
        advertiser = null;
        connectedDevice = null;
        log("Stopped");
    }

    private void safeControl(byte[] data) {
        try {
            listener.onControlWrite(data);
        } catch (Exception exception) {
            Log.e(TAG, "control listener failed", exception);
        }
    }

    private void safeClipboard(byte[] data) {
        try {
            listener.onClipboardWrite(data);
        } catch (Exception exception) {
            Log.e(TAG, "clipboard listener failed", exception);
        }
    }

    private void safeConnectionState(int state) {
        try {
            listener.onConnectionState(state);
        } catch (Exception exception) {
            Log.e(TAG, "connection listener failed", exception);
        }
    }

    private void safeMtu(int mtu) {
        try {
            listener.onMtuChanged(mtu);
        } catch (Exception exception) {
            Log.e(TAG, "MTU listener failed", exception);
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
