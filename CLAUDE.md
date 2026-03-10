# ha-rutos-integration

Home Assistant custom integration for Teltonika RutOS routers, distributed via
HACS.

## Key Paths

- `custom_components/rutos/` — integration source
- `tests/` — pytest test suite
- `hacs.json` — HACS repository metadata
- `custom_components/rutos/manifest.json` — HA integration manifest
- `custom_components/rutos/translations/en.json` — UI strings

## Dev Commands

- **Test:** `.venv/bin/python -m pytest tests/ -v`
- **Lint:** `.venv/bin/ruff check custom_components/rutos/`
- **Format:** `.venv/bin/ruff format custom_components/rutos/`
- **Type-check:** `/opt/homebrew/bin/pyright custom_components/rutos/`
- **HACS validate:**
  `docker run --rm -v $(pwd):/github/workspace ghcr.io/hacs/action`

## Conventions

- All entities inherit from `RutOSEntity` base class (`entity.py`) which
  provides shared `device_info` and interface lookup logic. Do not duplicate
  this in platform files.
- Follow Home Assistant integration patterns: `async_setup_entry` /
  `async_unload_entry`, `DataUpdateCoordinator`, `ConfigFlow`.
- Use `aiohttp` for async HTTP (via `homeassistant.helpers.aiohttp_client`),
  never `requests`.
- Config flow strings must stay in sync between `config_flow.py` and
  `translations/en.json`.
- Sensor/binary_sensor/switch descriptions use `EntityDescription` dataclasses.

## Code Navigation — Prefer Serena MCP Tools

When exploring or reading code in this project, **prefer Serena MCP tools** over
Read/Grep/Glob:

- `get_symbols_overview` — get a file's classes, functions, and methods without
  reading the full file
- `find_symbol` — locate a symbol by name path (e.g. `RutOSEntity/device_info`),
  optionally with `include_body=True`
- `find_referencing_symbols` — find all callers/users of a symbol before
  modifying it
- `search_for_pattern` — fast regex search across the codebase

Only fall back to Read/Grep/Glob when working with non-code files (JSON, YAML,
markdown) or when you need raw file content that isn't organized into symbols.
