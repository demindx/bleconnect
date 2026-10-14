package org.bleconnect.testclient;

import android.Manifest;
import android.app.Activity;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothSocket;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.Spinner;
import android.widget.TextView;

import org.json.JSONObject;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int REQUEST_BLUETOOTH_CONNECT = 40;
    private static final UUID SERVICE_UUID = UUID.fromString(
            "d37b4a30-8e74-4f36-9a01-7d3a8f7c2b10");

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final List<BluetoothDevice> devices = new ArrayList<>();
    private Spinner devicePicker;
    private TextView status;
    private ArrayAdapter<String> deviceNames;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        buildUi();
        if (hasConnectPermission()) {
            loadBondedDevices();
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            requestPermissions(
                    new String[]{Manifest.permission.BLUETOOTH_CONNECT},
                    REQUEST_BLUETOOTH_CONNECT);
        }
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(32, 40, 32, 32);

        TextView title = new TextView(this);
        title.setText("BLEConnect Bluetooth test");
        title.setTextSize(22);
        root.addView(title);

        devicePicker = new Spinner(this);
        root.addView(devicePicker, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        Button refresh = new Button(this);
        refresh.setText("Refresh paired devices");
        refresh.setOnClickListener(view -> loadBondedDevices());
        root.addView(refresh);

        Button connect = new Button(this);
        connect.setText("Connect and send ping");
        connect.setOnClickListener(view -> connectAndPing());
        root.addView(connect);

        status = new TextView(this);
        status.setText("Pair this phone with the Fedora computer, then refresh.");
        status.setTextSize(16);
        root.addView(status);
        setContentView(root);
    }

    private boolean hasConnectPermission() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.S
                || checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)
                == PackageManager.PERMISSION_GRANTED;
    }

    private void loadBondedDevices() {
        if (!hasConnectPermission()) {
            status.setText("Bluetooth permission is required.");
            return;
        }
        BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
        if (adapter == null) {
            status.setText("This device has no Bluetooth adapter.");
            return;
        }
        devices.clear();
        devices.addAll(adapter.getBondedDevices());
        List<String> labels = new ArrayList<>();
        for (BluetoothDevice device : devices) {
            String name = device.getName();
            labels.add((name == null ? "Bluetooth device" : name) + "  (" + device.getAddress() + ")");
        }
        if (labels.isEmpty()) {
            labels.add("No paired devices; pair in Android Bluetooth settings first");
        }
        deviceNames = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, labels);
        deviceNames.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        devicePicker.setAdapter(deviceNames);
        status.setText("Found " + devices.size() + " paired device(s).");
    }

    private void connectAndPing() {
        if (!hasConnectPermission()) {
            status.setText("Bluetooth permission is required.");
            return;
        }
        int selected = devicePicker.getSelectedItemPosition();
        if (selected < 0 || selected >= devices.size()) {
            status.setText("Pair the Fedora computer in Android Bluetooth settings first.");
            return;
        }
        BluetoothDevice device = devices.get(selected);
        status.setText("Connecting to " + device.getAddress() + "…");
        executor.execute(() -> runPing(device));
    }

    private void runPing(BluetoothDevice device) {
        try (BluetoothSocket socket = device.createRfcommSocketToServiceRecord(SERVICE_UUID)) {
            socket.connect();
            DataOutputStream output = new DataOutputStream(socket.getOutputStream());
            DataInputStream input = new DataInputStream(socket.getInputStream());

            byte[] request = new JSONObject()
                    .put("version", 1)
                    .put("type", "ping")
                    .put("body", new JSONObject())
                    .toString()
                    .getBytes(StandardCharsets.UTF_8);
            output.writeInt(request.length);
            output.write(request);
            output.flush();

            int size = input.readInt();
            if (size <= 0 || size > 1024 * 1024) {
                throw new IllegalStateException("Invalid response frame size: " + size);
            }
            byte[] responseBytes = new byte[size];
            input.readFully(responseBytes);
            JSONObject response = new JSONObject(new String(responseBytes, StandardCharsets.UTF_8));
            runOnUiThread(() -> status.setText("Connected. Fedora replied: " + response));
        } catch (Exception exception) {
            runOnUiThread(() -> status.setText(
                    "Connection failed: " + exception.getClass().getSimpleName()
                            + ": " + exception.getMessage()));
        }
    }

    @Override
    public void onRequestPermissionsResult(
            int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_BLUETOOTH_CONNECT) {
            if (hasConnectPermission()) {
                loadBondedDevices();
            } else {
                status.setText("Bluetooth Connect permission was denied.");
            }
        }
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }
}
