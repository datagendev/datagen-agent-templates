#!/usr/bin/env bash
# Template validation hook + standalone script.
#
# Two modes:
#   1. Hook mode (PostToolUse): reads JSON from stdin to get file_path
#   2. CLI mode: pass file path as argument -- `scripts/validate_template.sh <file>`
#
# Exit codes:
#   0 = pass (or not a template file)
#   2 = validation failed (stderr has the error message)

set -euo pipefail

# Determine file path: CLI arg takes priority, then stdin JSON
if [[ $# -ge 1 ]]; then
  FILE_PATH="$1"
elif ! [ -t 0 ]; then
  # Hook mode: read JSON from stdin
  INPUT=$(cat)
  FILE_PATH=$(echo "$INPUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null || echo "")
else
  FILE_PATH=""
fi

# Nothing to check
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Only check files inside templates/
case "$FILE_PATH" in
  */templates/*)
    ;;
  *)
    exit 0
    ;;
esac

# Check manifest.json files
if [[ "$(basename "$FILE_PATH")" == "manifest.json" ]]; then
  if ! python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$FILE_PATH" 2>/dev/null; then
    echo "manifest.json is not valid JSON" >&2
    exit 2
  fi

  MISSING=$(python3 -c "
import json, sys
manifest = json.load(open(sys.argv[1]))
required = ['id', 'name', 'description', 'version', 'category', 'requirements', 'install_target']
missing = [f for f in required if f not in manifest]
if missing:
    print(', '.join(missing))
" "$FILE_PATH" 2>/dev/null)

  if [[ -n "$MISSING" ]]; then
    echo "manifest.json missing required fields: $MISSING" >&2
    exit 2
  fi
fi

# Check agent.md files
if [[ "$(basename "$FILE_PATH")" == "agent.md" ]]; then
  if grep -q '\.claude/skills/' "$FILE_PATH" 2>/dev/null; then
    echo "agent.md contains .claude/skills/ path -- use .datagen/{id}/ instead" >&2
    exit 2
  fi

  HAS_FRONTMATTER=$(python3 -c "
import sys
content = open(sys.argv[1]).read()
if not content.startswith('---'):
    print('no-frontmatter')
    sys.exit()
end = content.find('---', 3)
if end == -1:
    print('no-frontmatter')
    sys.exit()
fm = content[3:end]
has_name = 'name:' in fm
has_desc = 'description:' in fm
if not has_name or not has_desc:
    missing = []
    if not has_name: missing.append('name')
    if not has_desc: missing.append('description')
    print(','.join(missing))
" "$FILE_PATH" 2>/dev/null)

  if [[ "$HAS_FRONTMATTER" == "no-frontmatter" ]]; then
    echo "agent.md missing YAML frontmatter (must start with ---)" >&2
    exit 2
  fi

  if [[ -n "$HAS_FRONTMATTER" ]]; then
    echo "agent.md frontmatter missing: $HAS_FRONTMATTER" >&2
    exit 2
  fi
fi

exit 0
