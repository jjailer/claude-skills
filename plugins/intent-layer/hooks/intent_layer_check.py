#!/usr/bin/env python3
"""PreToolUse hook: flag intent-layer nodes whose code changed without them.

Speaks only when a commit touches code under a CLAUDE.md that the same commit
leaves untouched. A commit that updates code and its node together is silent.
"""

import json
import os
import subprocess
import sys

NODE = "CLAUDE.md"


def git(cwd, *args):
    """Run git, returning its stdout lines. Any failure yields no lines."""
    try:
        result = subprocess.run(
            ("git", *args), cwd=cwd, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return result.stdout.splitlines() if result.returncode == 0 else []


def sweeps_tracked_files(command):
    """True for `git commit -a` / `-am` / `--all`, which stage at commit time."""
    for token in command.split():
        if token.startswith("--"):
            if token == "--all":
                return True
        elif token.startswith("-") and "a" in token[1:]:
            return True
    return False


def nearest_node(path, nodes):
    """Nearest ancestor node, resolved from the path string.

    Deliberately textual rather than filesystem-based so that deleted and
    renamed paths still resolve — a `git rm` under a node is exactly when that
    node most likely has a tombstone to prune.

    The root node is reachable only from top-level files. It nominally sits
    above everything, so letting deep paths fall back to it would implicate it
    on nearly every commit in nearly every repo, and a reminder that always
    fires is one you learn to ignore. A directory whose changes deserve
    intent-layer attention deserves its own node.
    """
    directory = os.path.dirname(path)
    if not directory:
        return NODE if NODE in nodes else None
    while directory:
        candidate = os.path.join(directory, NODE)
        if candidate in nodes:
            return candidate
        directory = os.path.dirname(directory)
    return None


def implicated_nodes(changed, nodes, changed_nodes):
    """Map each unaccompanied node to the changed files that implicate it."""
    found = {}
    for path in sorted(changed):
        if os.path.basename(path) == NODE:
            continue
        node = nearest_node(path, nodes)
        # A node updated in this same commit is struck: the work is already done.
        if node and node not in changed_nodes:
            found.setdefault(node, []).append(path)
    return found


def render(found):
    count = len(found)
    noun = "node" if count == 1 else "nodes"
    lines = [f"This commit changes code under {count} intent-layer {noun} it does not update:"]
    for node, files in sorted(found.items()):
        more = f" (+{len(files) - 1} more)" if len(files) > 1 else ""
        lines.append(f"  {node}  <- {files[0]}{more}")
    lines.append(
        "Did contracts, invariants, patterns, pitfalls, or dependencies change? Update or prune "
        "the node in this same commit — or state why it needs no change. Rules: intent-layer skill."
    )
    return "\n".join(lines)


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0

    if event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command") or ""
    if "git commit" not in command:
        return 0

    cwd = event.get("cwd") or os.getcwd()
    if not git(cwd, "rev-parse", "--is-inside-work-tree"):
        return 0

    changed = set(git(cwd, "diff", "--cached", "--name-only"))
    if sweeps_tracked_files(command):
        changed |= set(git(cwd, "diff", "--name-only"))
    if not changed:
        return 0

    changed_nodes = {p for p in changed if os.path.basename(p) == NODE}
    # Union with staged nodes: a node created by this commit isn't tracked yet.
    nodes = {
        p for p in git(cwd, "ls-files", "--", f"*{NODE}") if os.path.basename(p) == NODE
    } | changed_nodes

    found = implicated_nodes(changed, nodes, changed_nodes)
    if not found:
        return 0

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": render(found),
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
