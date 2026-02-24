#!/usr/bin/env python3
"""
Template Linter -- validates agent templates for consistency and correctness.

Checks per template:
  1. manifest.json exists and matches JSON schema
  2. Every file listed in manifest.files exists on disk
  3. manifest.id matches the directory name
  4. agent.md uses .datagen/{id}/ paths (not .claude/skills/ or bare relative)
  5. Python scripts are valid syntax
  6. agents.json entry exists and is consistent with manifest (id, secrets, status)
  7. No stale .claude/skills/ references in any file

Usage:
    python scripts/lint_templates.py                     # lint all templates
    python scripts/lint_templates.py instantly-health-report  # lint one template
"""
import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "templates"
AGENTS_JSON = REPO_ROOT / "agents.json"
SCHEMA_PATH = REPO_ROOT / "schema" / "manifest.schema.json"

# Paths that agent.md should NOT contain
STALE_PATH_PATTERNS = [
    re.compile(r"\.claude/skills/"),
]

# Paths in agent.md should use .datagen/{id}/ for scripts, context, templates, learnings
EXPECTED_PATH_PREFIX = ".datagen/"


class LintError:
    def __init__(self, template_id, check, message):
        self.template_id = template_id
        self.check = check
        self.message = message

    def __str__(self):
        return f"  FAIL [{self.check}] {self.message}"


def load_json(path):
    with open(path) as f:
        return json.load(f)


def validate_manifest_schema(manifest, template_id):
    """Validate manifest against known required fields (no jsonschema dependency)."""
    errors = []
    required_top = ["id", "name", "description", "version", "category", "requirements", "install_target"]
    for field in required_top:
        if field not in manifest:
            errors.append(LintError(template_id, "schema", f"manifest.json missing required field: {field}"))

    if "id" in manifest and not re.match(r"^[a-z0-9-]+$", manifest["id"]):
        errors.append(LintError(template_id, "schema", f"manifest.id contains invalid characters: {manifest['id']}"))

    if "version" in manifest and not re.match(r"^\d+\.\d+\.\d+$", manifest["version"]):
        errors.append(LintError(template_id, "schema", f"manifest.version not semver: {manifest['version']}"))

    valid_categories = ["sales", "marketing", "ops", "engineering", "research", "support", "email-ops", "growth", "strategy"]
    if "category" in manifest and manifest["category"] not in valid_categories:
        errors.append(LintError(template_id, "schema", f"manifest.category '{manifest['category']}' not in allowed list"))

    reqs = manifest.get("requirements", {})
    if "env_vars" not in reqs:
        errors.append(LintError(template_id, "schema", "manifest.requirements missing env_vars"))

    if "files" not in manifest:
        errors.append(LintError(template_id, "schema", "manifest.json missing files array"))

    return errors


def check_files_exist(manifest, template_dir, template_id):
    """Every file in manifest.files must exist on disk."""
    errors = []
    for filepath in manifest.get("files", []):
        full_path = template_dir / filepath
        if not full_path.exists():
            errors.append(LintError(template_id, "files", f"listed in manifest but missing: {filepath}"))
    return errors


def check_manifest_id(manifest, template_id):
    """manifest.id must match the directory name."""
    errors = []
    if manifest.get("id") != template_id:
        errors.append(LintError(
            template_id, "id-match",
            f"manifest.id '{manifest.get('id')}' does not match directory name '{template_id}'"
        ))
    return errors


def check_agent_md_paths(template_dir, template_id):
    """agent.md should use .datagen/{id}/ paths, not stale paths or bare relative."""
    errors = []
    agent_md = template_dir / "agent.md"
    if not agent_md.exists():
        errors.append(LintError(template_id, "agent-paths", "agent.md not found"))
        return errors

    content = agent_md.read_text()

    # Check for stale paths
    for pattern in STALE_PATH_PATTERNS:
        matches = pattern.findall(content)
        if matches:
            errors.append(LintError(
                template_id, "stale-paths",
                f"agent.md contains stale path pattern: {matches[0]}"
            ))

    # Check that script/context/template references use .datagen/{id}/
    # Look for python3 commands or Read references to scripts/, context/, templates/, learnings/
    bare_refs = re.findall(
        r'(?<![.\w/])(?:scripts|context|templates|learnings)/\S+',
        content
    )
    seen = set()
    for ref in bare_refs:
        # Strip trailing markdown/punctuation artifacts
        ref_clean = ref.rstrip("`',;)\"")
        if not ref_clean or ref_clean in seen:
            continue
        seen.add(ref_clean)
        # Skip if it's inside a .datagen/ path or a URL or a manifest reference
        # Check surrounding context - find where this ref appears
        idx = content.find(ref)
        prefix_start = max(0, idx - 60)
        preceding = content[prefix_start:idx]
        if ".datagen/" not in preceding and "manifest" not in preceding.lower():
            errors.append(LintError(
                template_id, "bare-paths",
                f"agent.md has bare relative path '{ref_clean}' -- should use .datagen/{template_id}/{ref_clean}"
            ))

    return errors


def check_python_syntax(template_dir, template_id):
    """All .py files must be valid Python syntax."""
    errors = []
    for py_file in template_dir.rglob("*.py"):
        try:
            source = py_file.read_text()
            ast.parse(source, filename=str(py_file))
        except SyntaxError as e:
            rel = py_file.relative_to(template_dir)
            errors.append(LintError(template_id, "syntax", f"{rel} line {e.lineno}: {e.msg}"))
    return errors


def check_stale_paths_all_files(template_dir, template_id):
    """No file in the template should reference .claude/skills/."""
    errors = []
    for fpath in template_dir.rglob("*"):
        if fpath.is_dir():
            continue
        if fpath.suffix in (".pyc", ".png", ".jpg", ".gif", ".ico"):
            continue
        try:
            content = fpath.read_text(errors="ignore")
        except Exception:
            continue
        for pattern in STALE_PATH_PATTERNS:
            if pattern.search(content):
                rel = fpath.relative_to(template_dir)
                errors.append(LintError(template_id, "stale-paths", f"{rel} contains .claude/skills/ reference"))
    return errors


def check_agents_json_consistency(manifest, template_id):
    """agents.json entry should be consistent with manifest."""
    errors = []
    if not AGENTS_JSON.exists():
        errors.append(LintError(template_id, "agents-json", "agents.json not found at repo root"))
        return errors

    index = load_json(AGENTS_JSON)
    entry = next((a for a in index.get("agents", []) if a["id"] == template_id), None)

    if entry is None:
        errors.append(LintError(template_id, "agents-json", f"no entry for '{template_id}' in agents.json"))
        return errors

    # Status should be stable if template has files
    if entry.get("status") != "stable":
        errors.append(LintError(template_id, "agents-json", f"status is '{entry.get('status')}' but template exists -- expected 'stable'"))

    # Path should point to this template
    expected_path = f"templates/{template_id}"
    if entry.get("path") != expected_path:
        errors.append(LintError(template_id, "agents-json", f"path is '{entry.get('path')}' -- expected '{expected_path}'"))

    # Secrets should match env_vars
    manifest_envs = {v["name"] for v in manifest.get("requirements", {}).get("env_vars", [])}
    index_secrets = {s["name"] for s in entry.get("secrets", [])}
    if manifest_envs != index_secrets:
        only_manifest = manifest_envs - index_secrets
        only_index = index_secrets - manifest_envs
        if only_manifest:
            errors.append(LintError(template_id, "agents-json", f"env_vars in manifest but not agents.json secrets: {only_manifest}"))
        if only_index:
            errors.append(LintError(template_id, "agents-json", f"secrets in agents.json but not manifest env_vars: {only_index}"))

    return errors


def lint_template(template_id):
    """Run all checks for a single template. Returns list of LintErrors."""
    template_dir = TEMPLATES_DIR / template_id
    errors = []

    # Manifest must exist
    manifest_path = template_dir / "manifest.json"
    if not manifest_path.exists():
        errors.append(LintError(template_id, "manifest", "manifest.json not found"))
        return errors

    manifest = load_json(manifest_path)

    errors.extend(validate_manifest_schema(manifest, template_id))
    errors.extend(check_manifest_id(manifest, template_id))
    errors.extend(check_files_exist(manifest, template_dir, template_id))
    errors.extend(check_agent_md_paths(template_dir, template_id))
    errors.extend(check_python_syntax(template_dir, template_id))
    errors.extend(check_stale_paths_all_files(template_dir, template_id))
    errors.extend(check_agents_json_consistency(manifest, template_id))

    return errors


def discover_templates():
    """Find all template directories that have a manifest.json."""
    templates = []
    if TEMPLATES_DIR.exists():
        for d in sorted(TEMPLATES_DIR.iterdir()):
            if d.is_dir() and (d / "manifest.json").exists():
                templates.append(d.name)
    return templates


def main():
    parser = argparse.ArgumentParser(description="Lint agent templates")
    parser.add_argument("template_id", nargs="?", help="Lint a specific template (default: all)")
    args = parser.parse_args()

    if args.template_id:
        template_ids = [args.template_id]
        template_dir = TEMPLATES_DIR / args.template_id
        if not template_dir.exists():
            print(f"Template directory not found: {template_dir}")
            sys.exit(1)
    else:
        template_ids = discover_templates()
        if not template_ids:
            print("No templates found.")
            sys.exit(0)

    total_errors = 0
    for tid in template_ids:
        errors = lint_template(tid)
        if errors:
            print(f"\n{tid}: {len(errors)} error(s)")
            for e in errors:
                print(str(e))
            total_errors += len(errors)
        else:
            print(f"{tid}: OK")

    print(f"\n{'=' * 40}")
    if total_errors:
        print(f"FAILED: {total_errors} error(s) across {len(template_ids)} template(s)")
        sys.exit(1)
    else:
        print(f"PASSED: {len(template_ids)} template(s) clean")
        sys.exit(0)


if __name__ == "__main__":
    main()
