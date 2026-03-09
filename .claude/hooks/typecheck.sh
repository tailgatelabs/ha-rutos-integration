#!/bin/bash
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path')

# Only type-check Python files
echo "$FILE_PATH" | grep -qE '\.py$' || exit 0

/opt/homebrew/bin/pyright "$FILE_PATH" 2>/dev/null
exit 0
