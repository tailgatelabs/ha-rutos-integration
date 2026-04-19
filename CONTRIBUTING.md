# Contributing to RutOS Home Assistant Integration

## Branch Strategy

- **`main`** — Stable, release-ready code. Every commit on `main` should be
  installable via HACS without issues.
- **`dev`** — Active development branch. All new work happens here first.

## Workflow

1. Create a feature or fix branch off `dev`:

   ```bash
   git checkout dev
   git pull
   git checkout -b my-feature
   ```

2. Make your changes and commit.
3. Open a pull request targeting `dev`.
4. Once reviewed and merged into `dev`, changes are tested there before being
   promoted.
5. When `dev` is stable and ready for release, a PR is opened from `dev` →
   `main` and tagged with a version.

## Releases

Releases are created from `main` using GitHub Releases. Each release gets a git
tag matching the version in `manifest.json` (e.g., `v0.1.0`). HACS picks up new
releases automatically.

To cut a release:

1. Merge `dev` → `main` via PR.
2. Update `version` in `custom_components/rutos/manifest.json`.
3. Create a GitHub Release with the tag (e.g., `v0.2.0`) and release notes.

## Testing Requirements

**All new code must be covered by tests.** This is a hard requirement for any PR
to be merged.

### Rules

- Every new function, method, branch, and error path must have at least one
  test.
- Bug fixes must include a regression test that would have caught the bug.
- Tests live in `tests/` and mirror the module structure of
  `custom_components/rutos/` (e.g., `api.py` → `tests/test_api.py`).
- The project enforces a minimum of **90% code coverage** (line + branch). The
  CI pipeline will fail if coverage drops below this threshold.

### Running tests locally

```bash
pip install -r requirements_dev.txt -r requirements_test.txt
pytest tests/ -v --cov=custom_components/rutos --cov-report=term-missing
```

The `--cov-report=term-missing` flag prints uncovered lines so you can see
exactly what still needs a test.

### What to test

| Area                                           | What to cover                                                                                                           |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `api.py`                                       | Every public method, every exception type raised, every branch (e.g., missing fields, non-list responses, token expiry) |
| `coordinator.py`                               | Setup, update, both error paths (`RutOSAuthError`, `RutOSAPIError`), and the `data is None` initialisation branches     |
| `config_flow.py`                               | All error cases (`invalid_auth`, `cannot_connect`, `unknown`), the duplicate-device abort, and the no-serial fallback   |
| `sensor.py` / `binary_sensor.py` / `switch.py` | Each entity property, unique ID format, and any edge case (missing interface, all-down interfaces, etc.)                |
| `__init__.py`                                  | Setup success, auth failure, unload, service registration and idempotency                                               |

### Test patterns

Use the shared fixtures in `tests/conftest.py` (`mock_coordinator`, `mock_api`,
`mock_wan_interfaces`, etc.) rather than duplicating setup logic in individual
test files. When you need HTTP-level mocking, use `aioresponses`.

## Testing a Branch on Your Home Assistant Install

You can point your HA instance at any branch or PR to test changes before
they're released.

### Option 1: HACS Custom Repository (easiest)

If you've already added this repo as a HACS custom repository, HACS installs
from the latest release on `main` by default. To test a different branch:

1. SSH into your HA instance or use the Terminal add-on.
2. Navigate to the integration directory:

   ```bash
   cd /config/custom_components/rutos
   ```

3. If the directory isn't already a git checkout, replace it with one:

   ```bash
   rm -rf /config/custom_components/rutos
   git clone https://github.com/crbn60/ha-rutos-integration.git /tmp/rutos-repo
   cp -r /tmp/rutos-repo/custom_components/rutos /config/custom_components/rutos
   rm -rf /tmp/rutos-repo
   ```

4. Switch to the branch you want to test:

   ```bash
   cd /tmp  # use a temp clone to grab the branch
   git clone -b my-feature https://github.com/crbn60/ha-rutos-integration.git rutos-repo
   rm -rf /config/custom_components/rutos
   cp -r rutos-repo/custom_components/rutos /config/custom_components/rutos
   rm -rf rutos-repo
   ```

5. Restart Home Assistant.

### Option 2: Direct Copy

1. Clone the repo on your development machine:

   ```bash
   git clone https://github.com/crbn60/ha-rutos-integration.git
   cd ha-rutos-integration
   git checkout dev  # or any branch/PR
   ```

2. Copy the integration to your HA config directory (via scp, Samba share,
   etc.):

   ```bash
   scp -r custom_components/rutos user@homeassistant:/config/custom_components/
   ```

3. Restart Home Assistant.

### Reverting to the Released Version

To go back to the stable HACS-managed version:

1. Delete the `custom_components/rutos` directory.
2. Reinstall via HACS.
3. Restart Home Assistant.
