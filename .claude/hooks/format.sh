#!/bin/bash
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path')

prettier --write "$FILE_PATH" 2>/dev/null
exit 0
