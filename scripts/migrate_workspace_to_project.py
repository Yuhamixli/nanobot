#!/usr/bin/env python3
"""
Migrate workspace from ~/.nanobot/workspace to project workspace.

Usage: python scripts/migrate_workspace_to_project.py

Copies knowledge/, knowledge_db/, memory/, skills/, chat_history/, and
bootstrap files (AGENTS.md, USER.md, etc.) from user workspace to project.
Preserves project's knowledge/README.md.
"""

import shutil
from pathlib import Path

SRC = Path.home() / ".nanobot" / "workspace"
DST = Path(__file__).resolve().parent.parent / "workspace"

# Files/dirs to preserve in project (don't overwrite with user's)
PRESERVE_IN_PROJECT = {"knowledge/README.md"}


def copy_tree(src: Path, dst: Path, exclude: set[str] | None = None) -> None:
    """Copy directory tree, optionally excluding paths relative to src."""
    exclude = exclude or set()
    for item in src.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(src)
        rel_str = str(rel).replace("\\", "/")
        if any(rel_str.startswith(ex) or ex in rel_str for ex in exclude):
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        print(f"  Copied: {rel_str}")


def main() -> None:
    if not SRC.exists():
        print(f"Source not found: {SRC}")
        return
    DST.mkdir(parents=True, exist_ok=True)

    print(f"Migrating {SRC} -> {DST}")

    # 1. knowledge/ - merge, preserve README
    src_k = SRC / "knowledge"
    if src_k.exists():
        for item in src_k.rglob("*"):
            if not item.is_file():
                continue
            rel = item.relative_to(src_k)
            rel_str = str(rel).replace("\\", "/")
            if rel_str == "README.md":
                continue  # keep project's
            target = DST / "knowledge" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            print(f"  knowledge/{rel_str}")

    # 2. knowledge_db/ - full copy
    src_db = SRC / "knowledge_db"
    if src_db.exists():
        dst_db = DST / "knowledge_db"
        if dst_db.exists():
            shutil.rmtree(dst_db)
        shutil.copytree(src_db, dst_db)
        print("  knowledge_db/ (ChromaDB)")

    # 3. memory/
    src_m = SRC / "memory"
    if src_m.exists():
        copy_tree(src_m, DST / "memory")

    # 4. skills/
    src_s = SRC / "skills"
    if src_s.exists():
        copy_tree(src_s, DST / "skills")

    # 5. chat_history/
    src_ch = SRC / "chat_history"
    if src_ch.exists():
        copy_tree(src_ch, DST / "chat_history")

    # 6. Bootstrap files (user's may have customizations)
    for name in ["AGENTS.md", "USER.md", "SOUL.md", "TOOLS.md", "HEARTBEAT.md"]:
        src_f = SRC / name
        if src_f.exists():
            shutil.copy2(src_f, DST / name)
            print(f"  {name}")

    print("\nMigration done. Run: nanobot knowledge ingest")


if __name__ == "__main__":
    main()
