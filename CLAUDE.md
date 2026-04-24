# Claude Instructions

@AGENTS.md

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
