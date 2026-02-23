"""
Shared database utilities for LinkedIn Engagement Agent scripts.
"""

import json
import os

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_DIR = os.path.join(AGENT_DIR, "tmp")
os.makedirs(TMP_DIR, exist_ok=True)


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL not set. Export it: export DATABASE_URL=postgresql://..."
        )
    return psycopg2.connect(DATABASE_URL)


def query(sql, params=None, as_dict=True):
    """Run a SELECT and return rows as dicts (or tuples if as_dict=False)."""
    with get_conn() as conn:
        if as_dict:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]
        else:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()


def execute(sql, params=None):
    """Run a single INSERT/UPDATE/DELETE and commit."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()


def execute_many(sql, params_list):
    """Run a parameterized statement for many rows and commit."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, params_list)
        conn.commit()


def save_json(path, data):
    """Write data to a JSON file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
