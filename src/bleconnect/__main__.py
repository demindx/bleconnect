"""Command-line entry point for the Linux companion service."""

import argparse

from . import __version__


def main() -> None:
    parser = argparse.ArgumentParser(description="Bluetooth sharing companion")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.parse_args()
    parser.error("Bluetooth service is not implemented yet")


if __name__ == "__main__":
    main()
