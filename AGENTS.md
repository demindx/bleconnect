# Repository Guidelines

## Project Structure & Module Organization

This is a Python project for sharing clipboard text and browsing an approved Linux folder from Android over Bluetooth. Reusable logic and the Linux companion live in `src/bleconnect/`; Android UI and packaging belong in `android/`; architecture decisions are recorded in `docs/architecture.md`. Keep use cases independent from Kivy, BlueZ, Android APIs, and filesystem/clipboard adapters.

## Build, Test, and Development Commands

Use `uv sync` to create or update the project environment and `uv run bleconnect` to run the CLI. The Bluetooth service is still under development, so the CLI currently reports that it is not implemented. Android packaging will use Kivy with Buildozer/python-for-android and needs the Android SDK/NDK. Document new commands in `README.md` when adding executable features.

## Coding Style & Naming Conventions

Use Python 3.11+, four spaces for indentation, `snake_case` for modules and functions, and type annotations for shared protocol and service interfaces. Application services depend on ports; platform adapters implement those ports. Keep packet definitions shared without importing OS-specific code. See `docs/architecture.md` before adding a layer or adapter.

## Testing Guidelines

No test framework or coverage requirement is configured yet. Add tests under `tests/` as protocol and file-access behavior becomes available; name them `test_<behavior>.py`. Bluetooth integration checks require a paired Android device and a Linux machine with BlueZ. State which checks were actually run when reporting changes.

## Commit & Pull Request Guidelines

Git history is unavailable in this directory, so no existing commit convention can be inferred. Use concise, imperative commit subjects (for example, `Add connection settings`) and keep unrelated changes separate. Pull requests should explain the purpose and implementation, list checks run, link any related issue, and include screenshots or sample output when the change affects a user-facing interface.

## Configuration & Secrets

Keep credentials and machine-specific settings out of version control. Provide safe example configuration with placeholders, and document required environment variables without including live tokens or keys.
