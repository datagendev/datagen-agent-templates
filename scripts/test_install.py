#!/usr/bin/env python3
"""
Install Simulation Test -- verifies the fetch-agent install flow produces
the correct file layout without hitting GitHub.

Simulates what the datagen-plugin fetch-agent SKILL.md does:
  1. Read agents.json to find the template
  2. Read manifest.json to get the file list
  3. Copy files into a temp dir mimicking the install layout:
     - agent.md -> .claude/agents/{template_id}.md
     - everything else -> .datagen/{template_id}/{path}
  4. Verify the installed layout is correct

Usage:
    python scripts/test_install.py                              # test all stable templates
    python scripts/test_install.py instantly-health-report       # test one template
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "templates"
AGENTS_JSON = REPO_ROOT / "agents.json"


class TestResult:
    def __init__(self):
        self.passed = []
        self.failed = []

    def ok(self, msg):
        self.passed.append(msg)

    def fail(self, msg):
        self.failed.append(msg)

    @property
    def success(self):
        return len(self.failed) == 0


def load_json(path):
    with open(path) as f:
        return json.load(f)


def simulate_install(template_id, install_dir):
    """
    Simulate what fetch-agent SKILL.md does:
    - Copy agent.md to .claude/agents/{id}.md
    - Copy everything else to .datagen/{id}/{path}
    - Copy manifest.json to .datagen/{id}/manifest.json
    - Create .datagen/{id}/tmp/.gitkeep
    """
    template_dir = TEMPLATES_DIR / template_id
    manifest = load_json(template_dir / "manifest.json")

    agents_dir = install_dir / ".claude" / "agents"
    datagen_dir = install_dir / ".datagen" / template_id
    agents_dir.mkdir(parents=True, exist_ok=True)
    (datagen_dir / "tmp").mkdir(parents=True, exist_ok=True)

    installed_files = []

    for filepath in manifest.get("files", []):
        src = template_dir / filepath

        if filepath == "agent.md":
            dst = agents_dir / f"{template_id}.md"
        else:
            dst = datagen_dir / filepath

        dst.parent.mkdir(parents=True, exist_ok=True)

        if src.exists():
            shutil.copy2(src, dst)
            installed_files.append(str(dst.relative_to(install_dir)))

    # Copy manifest itself
    shutil.copy2(template_dir / "manifest.json", datagen_dir / "manifest.json")
    installed_files.append(str((datagen_dir / "manifest.json").relative_to(install_dir)))

    # Create tmp/.gitkeep
    (datagen_dir / "tmp" / ".gitkeep").touch()
    installed_files.append(str((datagen_dir / "tmp" / ".gitkeep").relative_to(install_dir)))

    return manifest, installed_files


def verify_install(template_id, install_dir, manifest):
    """Run verification checks on the simulated install."""
    result = TestResult()
    datagen_dir = install_dir / ".datagen" / template_id
    agent_file = install_dir / ".claude" / "agents" / f"{template_id}.md"

    # 1. agent.md installed to .claude/agents/
    if agent_file.exists():
        result.ok("agent.md installed to .claude/agents/")
    else:
        result.fail(f"agent.md not found at {agent_file.relative_to(install_dir)}")

    # 2. All non-agent files in .datagen/{id}/
    for filepath in manifest.get("files", []):
        if filepath == "agent.md":
            continue
        expected = datagen_dir / filepath
        if expected.exists():
            result.ok(f".datagen/{template_id}/{filepath} exists")
        else:
            result.fail(f"missing: .datagen/{template_id}/{filepath}")

    # 3. manifest.json copied to .datagen/{id}/
    if (datagen_dir / "manifest.json").exists():
        result.ok("manifest.json in .datagen/")
    else:
        result.fail("manifest.json not copied to .datagen/")

    # 4. tmp/.gitkeep exists
    if (datagen_dir / "tmp" / ".gitkeep").exists():
        result.ok("tmp/.gitkeep created")
    else:
        result.fail("tmp/.gitkeep missing")

    # 5. agent.md paths resolve correctly from install root
    #    All .datagen/{id}/... paths in agent.md should point to files that exist
    if agent_file.exists():
        content = agent_file.read_text()
        datagen_refs = re.findall(
            rf"\.datagen/{re.escape(template_id)}/(\S+)",
            content
        )
        for ref in datagen_refs:
            # Strip trailing punctuation that's not part of the path
            ref = ref.rstrip("`,;)'\"")
            target = install_dir / ".datagen" / template_id / ref
            if target.exists():
                result.ok(f"agent.md ref resolves: .datagen/{template_id}/{ref}")
            else:
                # It might be a path pattern or runtime-generated file -- only fail for known types
                _, ext = os.path.splitext(ref)
                if ext in (".py", ".md", ".html", ".json", ".txt", ".csv"):
                    result.fail(f"agent.md references .datagen/{template_id}/{ref} but file does not exist after install")

    # 6. No .claude/skills/ in any installed file
    for fpath in datagen_dir.rglob("*"):
        if fpath.is_dir() or fpath.suffix in (".pyc",):
            continue
        try:
            text = fpath.read_text(errors="ignore")
        except Exception:
            continue
        if ".claude/skills/" in text:
            rel = fpath.relative_to(install_dir)
            result.fail(f"{rel} contains stale .claude/skills/ reference")

    if agent_file.exists():
        text = agent_file.read_text()
        if ".claude/skills/" in text:
            result.fail("agent.md contains stale .claude/skills/ reference")

    # 7. No files leaked outside .claude/ and .datagen/
    for item in install_dir.iterdir():
        if item.name not in (".claude", ".datagen"):
            result.fail(f"unexpected top-level item after install: {item.name}")

    return result


def test_template(template_id):
    """Run the full install simulation + verification for one template."""
    print(f"\n{'=' * 50}")
    print(f"Testing install: {template_id}")
    print(f"{'=' * 50}")

    # Verify template exists in agents.json as stable
    index = load_json(AGENTS_JSON)
    entry = next((a for a in index["agents"] if a["id"] == template_id), None)
    if not entry:
        print(f"  SKIP: {template_id} not in agents.json")
        return True
    if entry["status"] != "stable":
        print(f"  SKIP: {template_id} status is '{entry['status']}', not stable")
        return True

    template_dir = TEMPLATES_DIR / template_id
    if not (template_dir / "manifest.json").exists():
        print(f"  FAIL: no manifest.json in {template_dir}")
        return False

    # Simulate install into a temp directory
    with tempfile.TemporaryDirectory(prefix=f"datagen-install-{template_id}-") as tmpdir:
        install_dir = Path(tmpdir)
        manifest, installed_files = simulate_install(template_id, install_dir)

        print(f"\nInstalled {len(installed_files)} files:")
        for f in sorted(installed_files):
            print(f"  {f}")

        result = verify_install(template_id, install_dir, manifest)

        print(f"\nResults:")
        for msg in result.passed:
            print(f"  PASS  {msg}")
        for msg in result.failed:
            print(f"  FAIL  {msg}")

        total = len(result.passed) + len(result.failed)
        print(f"\n  {len(result.passed)}/{total} checks passed")

        return result.success


def discover_stable_templates():
    """Find all templates marked stable in agents.json."""
    index = load_json(AGENTS_JSON)
    return [
        a["id"] for a in index.get("agents", [])
        if a["status"] == "stable" and a.get("path")
    ]


def main():
    parser = argparse.ArgumentParser(description="Test agent template install simulation")
    parser.add_argument("template_id", nargs="?", help="Test a specific template (default: all stable)")
    args = parser.parse_args()

    if args.template_id:
        template_ids = [args.template_id]
    else:
        template_ids = discover_stable_templates()
        if not template_ids:
            print("No stable templates found.")
            sys.exit(0)

    all_passed = True
    for tid in template_ids:
        if not test_template(tid):
            all_passed = False

    print(f"\n{'=' * 50}")
    if all_passed:
        print(f"ALL PASSED: {len(template_ids)} template(s)")
        sys.exit(0)
    else:
        print(f"SOME FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
