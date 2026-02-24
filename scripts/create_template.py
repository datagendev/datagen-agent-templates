#!/usr/bin/env python3
"""
Template Scaffolding Script -- creates directory structure for a new agent/skill template.

This script handles file layout, copying, and path rewriting. It does NOT detect
dependencies (secrets, tools, MCPs) -- the Claude agent does that by reading the files.

Usage:
    python3 scripts/create_template.py \
      --type agent \
      --id my-agent \
      --name "My Agent" \
      --description "Does the thing" \
      --category ops \
      [--from /path/to/agent.md]
"""
import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "templates"
AGENTS_JSON = REPO_ROOT / "agents.json"


def find_supporting_files(source_path: Path) -> list[Path]:
    """Find supporting files referenced by or associated with a source agent/skill.

    Looks for:
    - .datagen/{name}/ directory (sibling pattern)
    - .claude/skills/{name}/ directory
    - Path references in the source file content
    """
    source_dir = source_path.parent
    content = source_path.read_text()
    found_dirs: list[Path] = []

    # Try to find the project root (look for .claude/ or .git/)
    project_root = source_dir
    for _ in range(10):
        if (project_root / ".git").exists() or (project_root / ".claude").exists():
            break
        parent = project_root.parent
        if parent == project_root:
            break
        project_root = parent

    # Extract potential directory names from the source filename
    source_name = source_path.stem  # e.g. "my-agent" from "my-agent.md"
    if source_name in ("agent", "SKILL"):
        # Try parent dir name instead
        source_name = source_path.parent.name

    # Check common locations
    candidates = [
        project_root / ".datagen" / source_name,
        project_root / ".claude" / "skills" / source_name,
    ]

    # Also scan content for .datagen/X/ or .claude/skills/X/ references
    path_refs = re.findall(r"\.datagen/([a-z0-9-]+)/", content)
    path_refs += re.findall(r"\.claude/skills/([a-z0-9-]+)/", content)
    for ref in set(path_refs):
        candidates.append(project_root / ".datagen" / ref)
        candidates.append(project_root / ".claude" / "skills" / ref)

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir() and candidate not in found_dirs:
            found_dirs.append(candidate)

    return found_dirs


def rewrite_paths(content: str, old_prefixes: list[str], new_prefix: str) -> str:
    """Rewrite file path references in content."""
    for old in old_prefixes:
        content = content.replace(old, new_prefix)
    return content


def copy_supporting_dir(src_dir: Path, dest_dir: Path):
    """Copy contents of a supporting directory, preserving structure."""
    for item in src_dir.rglob("*"):
        if item.is_dir():
            continue
        # Skip __pycache__, .pyc, etc
        if "__pycache__" in str(item) or item.suffix == ".pyc":
            continue
        rel = item.relative_to(src_dir)
        dst = dest_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, dst)


def scaffold_from_existing(args):
    """Create template from an existing agent/skill file."""
    source = Path(args.source).resolve()
    if not source.exists():
        print(f"Error: source file not found: {source}")
        sys.exit(1)

    template_dir = TEMPLATES_DIR / args.id
    template_dir.mkdir(parents=True, exist_ok=True)

    # Copy source as agent.md
    dest_agent = template_dir / "agent.md"
    shutil.copy2(source, dest_agent)

    # Find and copy supporting files
    supporting_dirs = find_supporting_files(source)
    old_prefixes = []

    for sup_dir in supporting_dirs:
        # Determine the relative prefix used in the source
        # e.g. ".datagen/instantly-health-report/" or ".claude/skills/my-skill/"
        try:
            project_root = source.parent
            for _ in range(10):
                if (project_root / ".git").exists() or (project_root / ".claude").exists():
                    break
                project_root = project_root.parent

            rel_prefix = str(sup_dir.relative_to(project_root))
            old_prefixes.append(rel_prefix + "/")
            old_prefixes.append("./" + rel_prefix + "/")
        except ValueError:
            pass

        # Copy each subdirectory preserving structure
        for item in sup_dir.iterdir():
            if item.is_dir():
                copy_supporting_dir(item, template_dir / item.name)
            elif item.is_file():
                if "__pycache__" not in str(item) and item.suffix != ".pyc":
                    dest = template_dir / item.name
                    shutil.copy2(item, dest)

    # Rewrite paths in agent.md
    new_prefix = f".datagen/{args.id}/"
    content = dest_agent.read_text()
    content = rewrite_paths(content, old_prefixes, new_prefix)
    dest_agent.write_text(content)

    # Also rewrite paths in any copied .md files
    for md_file in template_dir.rglob("*.md"):
        if md_file == dest_agent:
            continue
        text = md_file.read_text()
        updated = rewrite_paths(text, old_prefixes, new_prefix)
        if updated != text:
            md_file.write_text(updated)

    # Ensure standard directories exist
    for subdir in ["scripts", "context", "learnings", "tmp"]:
        (template_dir / subdir).mkdir(exist_ok=True)

    # Create tmp/.gitkeep
    (template_dir / "tmp" / ".gitkeep").touch()

    # Create learnings file if not copied
    learnings = template_dir / "learnings" / "common_failures_and_fix.md"
    if not learnings.exists():
        learnings.write_text("# Common Failures and Fixes\n\n(Document issues and solutions here as you encounter them.)\n")

    return template_dir


def scaffold_from_scratch(args):
    """Create a blank template with placeholder content."""
    template_dir = TEMPLATES_DIR / args.id
    template_dir.mkdir(parents=True, exist_ok=True)

    # Create agent.md with placeholder
    install_target = ".claude/agents" if args.type == "agent" else ".claude/skills"
    agent_md = template_dir / "agent.md"
    agent_md.write_text(f"""---
name: {args.id}
description: "{args.description}"
---

You are a {args.name} agent.

## Workflow

### Step 1: Setup

Check that all required tools and secrets are available.

### Step 2: Execute

(Describe the main workflow here.)

### Step 3: Output

(Describe the expected output format.)

## Error Handling

- If a step fails, log the error and continue with available data.
- Inform the user of any issues encountered.
""")

    # Create standard directories
    for subdir in ["scripts", "context", "learnings", "tmp"]:
        (template_dir / subdir).mkdir(exist_ok=True)

    # Create placeholder files
    (template_dir / "tmp" / ".gitkeep").touch()
    (template_dir / "learnings" / "common_failures_and_fix.md").write_text(
        "# Common Failures and Fixes\n\n(Document issues and solutions here as you encounter them.)\n"
    )
    (template_dir / "context" / ".gitkeep").touch()
    (template_dir / "scripts" / ".gitkeep").touch()

    return template_dir


def build_file_list(template_dir: Path) -> list[str]:
    """Walk the template dir and return all files relative to it."""
    files = []
    for fpath in sorted(template_dir.rglob("*")):
        if fpath.is_dir():
            continue
        if "__pycache__" in str(fpath) or fpath.suffix == ".pyc":
            continue
        rel = str(fpath.relative_to(template_dir))
        # Skip manifest.json itself and .gitkeep files
        if rel == "manifest.json":
            continue
        if fpath.name == ".gitkeep":
            continue
        files.append(rel)
    return files


def generate_manifest(args, template_dir: Path):
    """Generate manifest.json with basic metadata. Dependencies are filled by the agent."""
    install_target = f".claude/agents/{args.id}" if args.type == "agent" else f".claude/skills/{args.id}"
    files = build_file_list(template_dir)

    manifest = {
        "id": args.id,
        "name": args.name,
        "description": args.description,
        "version": "1.0.0",
        "category": args.category,
        "tags": [],
        "author": "datagen",
        "requirements": {
            "datagen_tools": [],
            "datagen_mcps": [],
            "env_vars": [],
            "python_packages": [],
        },
        "files": files,
        "shared_skills": ["datagen-setup"],
        "install_target": install_target,
    }

    manifest_path = template_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    print(f"  Created: {manifest_path.relative_to(REPO_ROOT)}")
    return manifest


def generate_readme(args, template_dir: Path):
    """Generate a README.md for the template."""
    readme = template_dir / "README.md"
    if readme.exists():
        return

    readme.write_text(f"""# {args.name}

{args.description}

## Setup

1. Install via DataGen plugin: `/fetch-agent {args.id}`
2. Configure required secrets (see manifest.json)
3. Run the agent

## Files

See `manifest.json` for the complete file list.

## Usage

(Describe how to use this template.)
""")
    print(f"  Created: {readme.relative_to(REPO_ROOT)}")


def update_agents_json(args):
    """Add or update the entry in agents.json."""
    if not AGENTS_JSON.exists():
        print(f"  Warning: agents.json not found, skipping index update")
        return

    with open(AGENTS_JSON) as f:
        index = json.load(f)

    agents = index.get("agents", [])

    # Find existing entry or create new
    existing = next((a for a in agents if a["id"] == args.id), None)

    entry = {
        "id": args.id,
        "name": args.name,
        "description": args.description,
        "category": args.category,
        "tags": [],
        "status": "stable",
        "datagen_tools": [],
        "datagen_mcps": {"required": [], "optional": []},
        "secrets": [],
        "path": f"templates/{args.id}",
    }

    if existing:
        # Update in place
        idx = agents.index(existing)
        # Preserve fields that might have been manually set
        for key in ("tags", "datagen_tools", "datagen_mcps", "secrets"):
            if key in existing:
                entry[key] = existing[key]
        agents[idx] = entry
        print(f"  Updated: agents.json entry for '{args.id}'")
    else:
        agents.append(entry)
        print(f"  Added: agents.json entry for '{args.id}'")

    index["agents"] = agents

    with open(AGENTS_JSON, "w") as f:
        json.dump(index, f, indent=2)
        f.write("\n")


def main():
    parser = argparse.ArgumentParser(description="Scaffold a new agent/skill template")
    parser.add_argument("--type", required=True, choices=["agent", "skill"], help="Template type")
    parser.add_argument("--id", required=True, help="Template ID (kebab-case)")
    parser.add_argument("--name", required=True, help="Display name")
    parser.add_argument("--description", required=True, help="One-line description")
    parser.add_argument("--category", required=True,
                        choices=["sales", "marketing", "ops", "engineering", "research", "support"],
                        help="Template category")
    parser.add_argument("--from", dest="source", help="Path to existing agent.md or SKILL.md to package")
    args = parser.parse_args()

    # Validate ID format
    if not re.match(r"^[a-z0-9-]+$", args.id):
        print(f"Error: --id must be kebab-case (lowercase, hyphens only): {args.id}")
        sys.exit(1)

    # Check if template already exists
    template_dir = TEMPLATES_DIR / args.id
    if template_dir.exists():
        print(f"Warning: template directory already exists: {template_dir.relative_to(REPO_ROOT)}")
        print("  Continuing will overwrite generated files (manifest.json, README.md).")

    print(f"\nScaffolding template: {args.id}")
    print(f"  Type: {args.type}")
    print(f"  Name: {args.name}")
    print(f"  Category: {args.category}")

    if args.source:
        print(f"  Source: {args.source}")
        template_dir = scaffold_from_existing(args)
    else:
        print("  Mode: from scratch")
        template_dir = scaffold_from_scratch(args)

    generate_readme(args, template_dir)
    generate_manifest(args, template_dir)
    update_agents_json(args)

    print(f"\nDone. Template scaffolded at: templates/{args.id}/")
    print("Next: have the agent read the files to detect dependencies and update manifest.json + agents.json.")


if __name__ == "__main__":
    main()
