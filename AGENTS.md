# Repository Guidelines

## Project Overview

BLEConnect shares clipboard text, transfers explicitly selected files, and
finds the phone over Bluetooth. The Linux companion is Python with a PySide6/Qt
GUI and BlueZ; the Android app is Python with Kivy and a small native Bluetooth
bridge. BLE GATT carries presence, control, find-phone, and clipboard text;
Bluetooth Classic RFCOMM carries on-demand file transfers. Application logic
stays independent of both GUIs and of platform APIs.

`docs/spec.md` is the canonical product and protocol specification.
`docs/architecture.md` records architectural boundaries and dependency rules.

## Project Structure & Module Organization

- `src/bleconnect/protocol.py` - shared RFCOMM v2 framing and validation.
- `src/bleconnect/ble_protocol.py` - BLE chunk framing and reassembly.
- `src/bleconnect/messages.py` - shared message type names and helpers.
- `src/bleconnect/application/` - use cases and ports (no platform imports).
- `src/bleconnect/presentation/` - UI-agnostic view models and the application
  facade shared by Qt and Kivy.
- `src/bleconnect/adapters/linux/` - BlueZ pairing, BLE central, RFCOMM,
  clipboard, trusted devices.
- `src/bleconnect/adapters/filesystem/` - local file source/sink for explicit
  transfers and a future rooted-file adapter for shared folders.
- `src/bleconnect/adapters/ui/qt/` - thin PySide6 views (planned).
- `src/bleconnect/adapters/ui/kivy/` - thin Kivy screens (planned).
- `src/bleconnect/platform/` - per-platform composition roots.
- `android/` - Android packaging, permissions, and the native Bluetooth bridge
  (planned).
- `tests/` - unit and integration tests named `test_<behavior>.py`.
- `docs/` - specification, architecture, and operational notes.

Do not create empty packages or placeholder abstractions. Add a module when its
first behavior exists.

## Build, Test, and Development Commands

Use `uv sync` to create or update the environment and `uv run` for project
commands. The CLI currently exposes `uv run bleconnect --version`; further
commands are documented in `README.md` as they are added.

- Linux extras: `uv sync --extra linux` (BlueZ via `dbus-next`, BLE via
  `bleak`).
- GUI extras: `uv sync --extra gui` (PySide6, qasync).
- Android extras: `uv sync --extra android` (Kivy, pyjnius).
- Development tools: `uv sync --extra dev`; run tests with `uv run pytest`.

Android packaging uses Kivy with Buildozer/python-for-android and requires the
Android SDK/NDK. Document new executable commands in `README.md`.

## Coding Style & Naming Conventions

- Python 3.11+, four spaces, `snake_case` modules/functions, `PascalCase` types.
- Type annotations on public interfaces, services, ports, and protocol data.
- Prefer small functions and `dataclass` value objects over ad-hoc dictionaries.
- Use constructor injection and pass dependencies explicitly.
- Avoid hidden global state and mutable module-level singletons; the composition
  root owns wiring.
- Code identifiers and repository documentation are English. Explaining changes
  to the maintainer in Russian is welcome.

## Design Principles

- Simplicity by default. Prefer the smallest solution that satisfies the current
  requirement, then refactor when pressure appears.
- KISS: avoid indirection that earns nothing.
- DRY: remove real duplication, not incidental similarity. Apply the rule of
  three before extracting an abstraction.
- YAGNI: do not build speculative features or extension points. YAGNI applies
  to features, not to justified mechanisms such as async I/O or a state machine.
- Composition over inheritance; shallow hierarchies.
- Adapters raise clear exceptions; the facade converts them into user-facing
  state instead of leaking platform errors into the UI.

## Pragmatic Complexity

Complexity is allowed when it is justified. A construct is reasonable when all
of the following hold:

- It solves a concrete current requirement, not a hypothetical one.
- It removes duplication, a class of bugs, or a platform leak.
- It stays isolated and testable without hardware.
- It can be explained in one short note and removed without touching many files.

Do not add complexity "for the future", for symmetry, or because a pattern
exists. Metaclasses, generic frameworks, dependency-injection containers, and
event buses are not forbidden, but require a written justification.

For every non-trivial design decision, state a short note:

```text
Pattern: <name>
Where: <module or file:line>
Why: <problem solved and why a simpler option is insufficient>
Rejected alternative: <option and reason>
```

## Design Patterns Policy

Use a pattern only when it names an existing problem. Typical choices:

| Pattern | Typical location | Purpose |
| --- | --- | --- |
| Ports and Adapters | `application/ports.py`, `adapters/` | Keep use cases free of platform APIs |
| Strategy | clipboard providers, link factories | Choose a backend at runtime |
| Adapter | BlueZ, pyjnius, Qt, Kivy | Isolate foreign APIs |
| Repository | trusted devices, settings | Separate persistence from use cases |
| Observer | view models to Qt signals / Kivy properties | Update views without coupling |
| State | connection lifecycle | Explicit, testable transitions |
| Facade | `AppController` | One entry point for both GUIs |
| Factory / Composition Root | `platform/linux.py`, `platform/android.py` | Assemble concrete adapters once |

Prefer plain methods over Command objects unless queueing or undo is required.
Do not introduce a pattern without a concrete problem it reduces.

## Architecture & Dependency Rules

```text
Qt view (PySide6) ─┐
                   ├─> ViewModels / AppController ─> services ─> ports
Kivy view ─────────┘                                        ▲
                                          platform adapters ─┘
```

- UI depends on view models and the facade, never on adapters directly.
- Services depend on ports and protocol code.
- Adapters implement ports and may import OS libraries.
- Only composition roots construct concrete adapters.
- `application/`, `presentation/`, and `protocol.py` must not import PySide6,
  Kivy, `dbus_next`, Android classes, or desktop clipboard tools.
- Keep packet definitions shared; do not fork protocol logic per platform.

## Presentation Layer

- Write view models in pure Python with no Qt or Kivy imports. Both GUIs reuse
  the same view models and facade to keep behavior identical (DRY).
- Linux uses PySide6 with `qasync` so asyncio and Qt share one event loop.
- Android uses Kivy with asyncio on a background thread; schedule UI updates
  with `Clock.schedule_once` or an equivalent thin adapter.
- Views collect input and render state only. Connection, clipboard, and file
  behavior belongs in the facade or services.
- Do not block a UI thread. Long operations are async and report progress.

## Documentation

- `docs/spec.md` is the canonical specification: goals, use cases, functional
  requirements, UI flows, protocol, data model, platform constraints, testing,
  and roadmap. Update it when behavior or requirements change.
- `docs/architecture.md` explains boundaries and dependency direction.
- `README.md` documents user-facing commands and setup steps.
- Keep examples runnable; do not document commands or extras that do not exist.

## Testing Guidelines

- Use pytest; name files `test_<behavior>.py` under `tests/`.
- Current tests use plain `asyncio.run` inside test functions. Add
  `pytest-asyncio` only if its value is clear.
- Prefer fakes and injected ports over hardware. Test transport-agnostic
  behavior with TCP or `socketpair`, not RFCOMM.
- Planned markers: `unit`, `integration`, and `hardware`. CI must run without
  Bluetooth and exclude `hardware` tests.
- Real-device checks require a paired Android device and a Linux machine with
  BlueZ. State which checks were actually run when reporting changes.
- Cover boundaries explicitly: malformed frames, paths outside the shared root,
  missing permissions, disconnects, and reconnect behavior.

## Definition of Done

- Behavior is covered by unit or integration tests that do not need Bluetooth.
- `uv run pytest` passes for the changed area.
- Documentation (`docs/spec.md`, `README.md`, or both) is updated when behavior
  or user-facing commands change.
- Core code has no GUI or platform imports.
- Non-trivial design decisions include a short pattern note.
- User-facing changes have a manual check or screenshot when practical.

## Commit & Pull Request Guidelines

Commit and push completed work unless the user explicitly says not to. Use
small, logical commits with concise imperative subjects (for example, `Add Qt
connection window`) and keep unrelated changes separate. Before committing,
inspect `git status`, `git diff`, and `git log --oneline -10`; stage only the
intended files and never commit secrets, credentials, build outputs, or local
tool state.

Workflow:

- `main` is merge-only. Never commit or push directly to `main`; open a pull
  request instead. If work was started on `main` by mistake, move the commits
  to a branch before continuing.
- Create one branch per issue:
  `issue-<number>-<short-slug>` (for example, `issue-1-m0-spike`). Use
  `chore/<slug>` or `docs/<slug>` for work without an issue.
- Track non-trivial work with a GitHub issue when a remote is available:
  `gh issue create --title "..." --body "..."`. Reference the issue in commit
  messages and in the pull request.
- Push the branch (`git push -u origin <branch>`) and open a pull request with
  `gh pr create --base main --head <branch>`. Pull requests should explain the
  purpose and implementation, list checks run, link related issues, and include
  screenshots or sample output for UI changes.
- Merge through the pull request after checks pass. Do not force-push `main`,
  rewrite published history, or amend a pushed commit unless the user
  explicitly asks.
- If the remote or `gh` authentication is unavailable, report that instead of
  silently leaving work local.

## Configuration & Secrets

Keep credentials and machine-specific settings out of version control. Provide
safe example configuration with placeholders, and document required environment
variables without including live tokens or keys.
