---
name: test
description: Run the integration test suite
user-invocable: true
---

Run the test suite for this Home Assistant integration.

## Behavior

- With no arguments: `pytest tests/ -v --cov=custom_components/rutos`
- With a test file name argument (e.g., `/test api`):
  `pytest tests/test_{arg}.py -v`
- With a specific test function (e.g., `/test test_api.py::test_login_success`):
  `pytest tests/{arg} -v`

Report a concise pass/fail summary when done.
