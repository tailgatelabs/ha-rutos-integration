# ha-rutos-integration

Home Assistant custom integration for Teltonika RutOS routers, distributed via
HACS.

## Key Paths

- `custom_components/rutos/` - integration source
- `tests/` - pytest test suite
- `hacs.json` - HACS repository metadata
- `custom_components/rutos/manifest.json` - HA integration manifest
- `custom_components/rutos/translations/en.json` - UI strings

## Dev Commands

- **Test:** `.venv/bin/python -m pytest tests/ -v`
- **Lint:** `.venv/bin/ruff check custom_components/rutos/`
- **Format:** `.venv/bin/ruff format custom_components/rutos/`
- **Type-check:** `/opt/homebrew/bin/pyright custom_components/rutos/`
- **HACS validate:**
  `docker run --rm -v $(pwd):/github/workspace ghcr.io/hacs/action`

## Test Router

A live Teltonika router is reachable for ad-hoc API checks (e.g. comparing raw
endpoint responses against what the integration expects). Credentials live in
`.env` (gitignored) as `TELTONIKA_HOST`, `TELTONIKA_USER`, `TELTONIKA_PASSWORD`.
Read-only account; safe to query freely. Self-signed cert, so use `curl -k`.

To call an endpoint:

```bash
set -a; . ./.env; set +a
TOKEN=$(curl -sk -X POST "https://$TELTONIKA_HOST/api/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$TELTONIKA_USER\",\"password\":\"$TELTONIKA_PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['token'])")
curl -sk "https://$TELTONIKA_HOST/api/<path>" -H "Authorization: Bearer $TOKEN"
```

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

## Testing - Never Open Real Sockets

`pytest-homeassistant-custom-component` blocks all `socket.socket()` calls
during tests and records any attempt on `HASocketBlockedError.instances`. The
autouse `verify_cleanup` teardown asserts that list is empty, so **even a
blocked attempt fails the test**. The assertion fires in teardown even when the
test body passed.

Rules when writing or modifying tests:

- Any test that calls `hass.config_entries.async_setup(entry_id)` must patch
  `custom_components.rutos.RutOSAPI` with a mock (or keep the API entirely out
  of the call path). Don't rely on the real `aiohttp` session; it will try to
  reach `192.168.1.1` and get blocked.
- Keep the `patch(...)` context active for the **entire test**, not just the
  initial setup. Creating a subentry, changing options, or anything that
  triggers `async_schedule_reload`/`async_reload` will re-instantiate `RutOSAPI`
  outside a short-lived patch block. Prefer a pytest fixture that `yield`s the
  mock (see `patched_rutos_api` in `test_config_flow.py`) over a
  `with patch(...)` inside a helper that returns before the test body runs.
- When a CI failure mentions `HASocketBlockedError` / "the test opens sockets",
  look for a reload path (subentries, options updates, coordinator retries) that
  escapes the patch scope, not for a missing mock on the initial setup.
