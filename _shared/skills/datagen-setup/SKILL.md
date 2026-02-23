---
name: datagen-setup
description: Verify DataGen is configured and ready for agent use
user_invocable: false
---

# DataGen Setup Check

Reusable skill that verifies DataGen prerequisites are in place before running an agent.

## When to invoke

- Before any agent's first run
- When preflight checks fail
- When the user says "setup datagen" or "configure datagen"

## Steps

### 1. Check DATAGEN_API_KEY

```bash
if [ -z "$DATAGEN_API_KEY" ]; then
  echo "DATAGEN_API_KEY not set."
  echo "Get your API key from https://app.datagen.dev and run:"
  echo "  export DATAGEN_API_KEY=<your-key>"
  exit 1
fi
echo "DATAGEN_API_KEY is set."
```

### 2. Check DataGen MCP server is connected

Verify the DataGen MCP server is available in Claude Code:

```bash
claude mcp list 2>/dev/null | grep -q datagen
if [ $? -ne 0 ]; then
  echo "DataGen MCP server not connected. Run:"
  echo '  claude mcp add datagen --transport http https://mcp.datagen.dev/mcp -e DATAGEN_API_KEY'
  exit 1
fi
echo "DataGen MCP server is connected."
```

### 3. Check Python SDK

```bash
python3 -c "import datagen_sdk; print(f'datagen-python-sdk {datagen_sdk.__version__}')" 2>/dev/null
if [ $? -ne 0 ]; then
  echo "DataGen Python SDK not installed. Run:"
  echo "  pip install datagen-python-sdk"
  exit 1
fi
```

### 4. Test API connectivity

```bash
python3 -c "
from datagen_sdk import DatagenClient
client = DatagenClient()
result = client.execute_tool('searchTools', {'query': 'test'})
print('API connection successful.')
"
```

### 5. Report status

Print a summary of what is configured and what is missing. If everything passes, confirm the user is ready to run agents.
