from types import SimpleNamespace

from bleconnect.adapters.linux.bluez_pairing import _devices_from_objects
from bleconnect.application.ports import BluetoothDevice


def test_bluez_objects_are_converted_to_sorted_devices() -> None:
    objects = {
        "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF": {
            "org.bluez.Device1": {
                "Address": SimpleNamespace(value="aa:bb:cc:dd:ee:ff"),
                "Name": SimpleNamespace(value="Phone"),
                "Paired": SimpleNamespace(value=True),
            }
        },
        "/org/bluez/hci0/dev_11_22_33_44_55_66": {
            "org.bluez.Device1": {
                "Address": "11:22:33:44:55:66",
                "Alias": "Laptop",
                "Paired": False,
            }
        },
    }

    assert _devices_from_objects(objects) == [
        BluetoothDevice("11:22:33:44:55:66", "Laptop", False),
        BluetoothDevice("AA:BB:CC:DD:EE:FF", "Phone", True),
    ]
