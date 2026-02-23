"""
Shared database utilities for LinkedIn Engagement Agent scripts.

Uses DataGen MCP tools for SQL execution (e.g., mcp_Neon_run_sql,
mcp_Supabase_run_sql). Auto-detects which database MCP is connected.

Pattern: client.execute_tool(db_tool, {"sql": "..."})
"""

import json
import os

from datagen_sdk import DatagenClient

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_DIR = os.path.join(AGENT_DIR, "tmp")
os.makedirs(TMP_DIR, exist_ok=True)

# Cache the detected database tool name
_db_tool = None
_client = None

# Known database MCP tool patterns (provider -> tool alias)
DB_TOOL_CANDIDATES = [
    "mcp_Neon_run_sql",
    "mcp_Supabase_run_sql",
    "mcp_Postgres_run_sql",
]


def get_client():
    """Get or create a shared DatagenClient instance."""
    global _client
    if _client is None:
        _client = DatagenClient()
    return _client


def detect_db_tool():
    """Auto-detect which database MCP tool is available in DataGen."""
    global _db_tool
    if _db_tool is not None:
        return _db_tool

    # Allow explicit override via env var
    override = os.environ.get("DATAGEN_DB_TOOL")
    if override:
        _db_tool = override
        return _db_tool

    client = get_client()

    # Search for SQL-related tools
    try:
        result = client.execute_tool("searchTools", {"query": "run sql database"})
        if result and isinstance(result, list):
            for tool in result:
                tool_name = tool.get("name", "") or tool.get("alias", "")
                for candidate in DB_TOOL_CANDIDATES:
                    if candidate.lower() in tool_name.lower() or tool_name == candidate:
                        _db_tool = tool_name
                        print(f"  Detected database MCP: {_db_tool}")
                        return _db_tool
    except Exception:
        pass

    # Try each candidate directly
    for candidate in DB_TOOL_CANDIDATES:
        try:
            client.execute_tool(
                "getToolDetails", {"tool_name": candidate}
            )
            _db_tool = candidate
            print(f"  Detected database MCP: {_db_tool}")
            return _db_tool
        except Exception:
            continue

    raise RuntimeError(
        "No database MCP tool found. Connect Neon, Supabase, or another "
        "Postgres MCP server at https://app.datagen.dev/tools, or set "
        "DATAGEN_DB_TOOL=mcp_YourProvider_run_sql"
    )


def _run_sql(sql):
    """Execute a SQL statement via the detected database MCP tool."""
    client = get_client()
    tool = detect_db_tool()
    result = client.execute_tool(tool, {"sql": sql})
    return result


def query(sql, params=None, as_dict=True):
    """Run a SELECT and return rows as dicts (or tuples if as_dict=False).

    Note: params are interpolated Python-side since MCP tools accept raw SQL.
    Only use for trusted internal data -- not raw user input.
    """
    formatted = _format_sql(sql, params)
    result = _run_sql(formatted)

    # MCP SQL tools typically return results as a list of rows
    if result is None:
        return []

    # Handle various MCP response formats
    rows = _extract_rows(result)

    if as_dict:
        return rows
    else:
        # Convert dicts to tuples
        return [tuple(row.values()) for row in rows]


def execute(sql, params=None):
    """Run a single INSERT/UPDATE/DELETE."""
    formatted = _format_sql(sql, params)
    _run_sql(formatted)


def execute_many(sql, params_list):
    """Run a parameterized statement for many rows.

    Batches multiple statements into a single SQL call for efficiency.
    """
    if not params_list:
        return

    statements = []
    for params in params_list:
        statements.append(_format_sql(sql, params))

    # Join into one batch call
    batch_sql = ";\n".join(statements)
    _run_sql(batch_sql)


def save_json(path, data):
    """Write data to a JSON file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


# --- Internal helpers ---


def _format_sql(sql, params):
    """Format SQL with parameters.

    Handles both positional (%s) and named (%(name)s) placeholders.
    Escapes string values with single quotes.
    """
    if params is None:
        return sql.strip()

    if isinstance(params, dict):
        escaped = {k: _escape(v) for k, v in params.items()}
        return (sql % escaped).strip()
    elif isinstance(params, (list, tuple)):
        escaped = tuple(_escape(v) for v in params)
        return (sql % escaped).strip()
    else:
        return sql.strip()


def _escape(value):
    """Escape a Python value for SQL interpolation."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return value
    # String: escape single quotes
    s = str(value).replace("'", "''")
    return f"'{s}'"


def _extract_rows(result):
    """Extract rows from various MCP SQL response formats."""
    if isinstance(result, list):
        # Already a list of dicts
        if result and isinstance(result[0], dict):
            return result
        return []

    if isinstance(result, dict):
        # Some tools return {"rows": [...], "columns": [...]}
        if "rows" in result:
            rows = result["rows"]
            columns = result.get("columns", [])
            if rows and isinstance(rows[0], dict):
                return rows
            if rows and isinstance(rows[0], (list, tuple)) and columns:
                return [dict(zip(columns, row)) for row in rows]
            return rows if rows else []
        # Some tools return {"result": [...]}
        if "result" in result:
            return _extract_rows(result["result"])

    # Try parsing as JSON string
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
            return _extract_rows(parsed)
        except (json.JSONDecodeError, TypeError):
            return []

    return []
