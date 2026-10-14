"""Bluetooth sharing between Android and Linux."""

__version__ = "0.1.0"


def main() -> None:
    """Run the Linux companion command."""
    from .__main__ import main as run_cli

    run_cli()
