---
name: validate
description: Run all CI validations locally before pushing
user-invocable: true
---

Run the same validations that CI performs, to catch issues before pushing.

## Steps

1. **Manifest validation**: Verify `custom_components/rutos/manifest.json` is
   valid JSON and contains required keys (`domain`, `name`, `version`,
   `documentation`, `issue_tracker`, `codeowners`, `config_flow`, `iot_class`)
2. **Test suite**: Run `pytest tests/ -v --cov=custom_components/rutos`
3. **Lint check**: Run `ruff check custom_components/ tests/` (if ruff is
   available)

Report a summary of all results and whether it looks safe to push.
