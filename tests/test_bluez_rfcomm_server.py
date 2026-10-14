from bleconnect.adapters.linux.bluez_rfcomm_server import _make_profile


def test_profile_exports_bluez_rfcomm_callbacks_with_expected_signatures() -> None:
    class DummyServer:
        def _released(self):
            pass

        def _accept_fd(self, _device, _fd):
            pass

        def _drop_link(self, _device):
            pass

    profile = _make_profile(DummyServer())
    methods = {
        method.name: (
            method.in_signature_tree.signature,
            method.out_signature_tree.signature,
        )
        for method in profile._get_methods(profile)
    }
    assert methods == {
        "Release": ("", ""),
        "NewConnection": ("oha{sv}", ""),
        "RequestDisconnection": ("o", ""),
    }
