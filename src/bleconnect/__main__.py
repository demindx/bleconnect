"""Command-line entry point for BLEConnect."""

from __future__ import annotations

import argparse

from . import __version__


def main() -> None:
    parser = argparse.ArgumentParser(description="Bluetooth sharing companion")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args()
    print("BLEConnect is under construction. See docs/spec.md for the planned behavior.")


if __name__ == "__main__":
    main()
