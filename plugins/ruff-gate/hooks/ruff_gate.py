#!/usr/bin/env python3
"""Two ruff gates: one per edit, one per turn.

`lint` (PostToolUse) checks the Python file just written. `gate` (Stop) checks
what the turn touched and holds the turn open until it is clean.

Both stay silent in a repo that has no ruff config, so enabling this globally
costs nothing in the repos that don't want it. Nothing can switch off a single
plugin hook from a project, so the opt-out lives in the script instead:
`.claude/ruff-gate.off`, `RUFF_GATE=off`, or `"enabled": false` in the config.

Ruff resolves configuration per file, walking up from the file itself, and rule
selection resolves with it rather than merging into the parent's. So passing
explicit paths to one invocation at the project root still holds each file to
the config that owns it — measured, not assumed. Excludes are the exception:
they govern directory traversal and nothing else, which is why `scope: "tree"`
is the only mode that needs a directory list.

Nothing here rewrites a file. Every report names the command that would.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time

CONFIG = os.path.join(".claude", "ruff-gate.json")
OFF = os.path.join(".claude", "ruff-gate.off")
PYPROJECT = "pyproject.toml"
RUFF_SECTION = re.compile(r"^\[tool\.ruff", re.MULTILINE)
SKIP_DIRS = frozenset({".venv", "venv", "node_modules", "build", "dist"})
STATE_TTL = 7 * 24 * 3600
TIMEOUT = 90

DEFAULTS = {
    "enabled": True,
    # "session" = the files this turn touched · "tree" = whole directories
    "scope": "session",
    "format": True,
    "dirs": None,  # None = discover; consulted only for scope "tree"
    "command": None,  # None = probe; e.g. ["uv", "run", "ruff"] pins a version
}


# --- repo shape -------------------------------------------------------------


def has_ruff_config(directory):
    for name in ("ruff.toml", ".ruff.toml"):
        if os.path.isfile(os.path.join(directory, name)):
            return True
    try:
        with open(os.path.join(directory, PYPROJECT), errors="replace") as fh:
            return bool(RUFF_SECTION.search(fh.read()))
    except OSError:
        return False


def governing_config(path, root):
    """The directory whose ruff config would govern `path`, or None.

    Mirrors ruff's own resolution. None means ruff has no opinion about this
    file, which is the whole answer to "some repos won't need this".
    """
    directory = os.path.dirname(os.path.abspath(path))
    root = os.path.abspath(root)
    while True:
        if has_ruff_config(directory):
            return directory
        if directory == root or os.path.dirname(directory) == directory:
            return None
        directory = os.path.dirname(directory)


def discover_dirs(root):
    """Directories to traverse under `scope: "tree"`.

    Depth one only. Ruff already applies a deeper config when it walks into the
    file; such a directory needs its own entry only when something above it
    excludes the path, and an exclude that deep is worth declaring in `dirs`
    rather than guessing at.
    """
    dirs = ["."] if has_ruff_config(root) else []
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return dirs
    for name in entries:
        if name.startswith(".") or name in SKIP_DIRS:
            continue
        directory = os.path.join(root, name)
        if os.path.isdir(directory) and has_ruff_config(directory):
            dirs.append(name)
    return dirs


def within(path, root):
    """True when `path` sits inside `root`.

    A hook fires on every edit of the session, including edits to files in
    other repositories. Without this, one project's rules get applied to
    another project's files.
    """
    path, root = os.path.abspath(path), os.path.abspath(root)
    return path == root or path.startswith(root + os.sep)


# --- running ruff -----------------------------------------------------------


def run(argv, cwd):
    """Exit code and combined output; a code of None means it never ran."""
    try:
        done = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT
        )
    except (OSError, subprocess.SubprocessError):
        return None, ""
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def violations(argv, cwd):
    """Ruff's report, or None when there is nothing to say.

    Ruff exits 1 for violations and 2 or above for its own errors — a bad flag,
    an unparseable config, no such binary. Reporting the second kind as a lint
    failure is how a broken toolchain becomes a wall of nonsense that the model
    then sets about "fixing".
    """
    code, out = run(argv, cwd)
    return (out.strip() or "ruff reported violations") if code == 1 else None


def probe(directory):
    """Prefer the project's own ruff over whatever is on PATH.

    A uv project pins a ruff version; PATH may carry another, and two versions
    disagree about formatting in ways neither run can settle. Probed rather than
    assumed, because `uv run ruff` fails in a project that doesn't depend on it.
    """
    markers = ("uv.lock", PYPROJECT)
    if shutil.which("uv") and any(
        os.path.isfile(os.path.join(directory, name)) for name in markers
    ):
        candidate = ["uv", "run", "ruff"]
        if run([*candidate, "--version"], directory)[0] == 0:
            return candidate
    return ["ruff"] if shutil.which("ruff") else None


def command_for(directory, key, cfg, state):
    """Resolved argv for a directory, or None to skip it. Cached per session."""
    if cfg.get("command"):
        return list(cfg["command"])
    cache = state.setdefault("command", {})
    if key not in cache:
        cache[key] = probe(directory)
    return list(cache[key]) if cache[key] else None


# --- session state, kept outside the repo it describes ----------------------


def state_path(event):
    base = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.expanduser(
        "~/.claude/ruff-gate"
    )
    raw = str(event.get("session_id") or "unknown")
    return os.path.join(base, "sessions", re.sub(r"[^\w.-]", "_", raw) + ".json")


def load_state(event):
    try:
        with open(state_path(event)) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(event, state):
    path = state_path(event)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sweep(os.path.dirname(path))
        with open(path, "w") as fh:
            json.dump(state, fh)
    except OSError:
        pass


def sweep(directory):
    """Abandoned sessions never reach a Stop, so this is the only reclaim."""
    cutoff = time.time() - STATE_TTL
    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass


# --- configuration ----------------------------------------------------------


def load_config(root):
    """Config merged over the defaults, plus a complaint if the file is broken.

    A malformed config silently falling back to defaults is the worst outcome:
    you would edit it, see no change, and never learn why. The gate says so.
    """
    cfg = dict(DEFAULTS)
    path = os.path.join(root, CONFIG)
    if not os.path.isfile(path):
        return cfg, None
    try:
        with open(path) as fh:
            loaded = json.load(fh)
    except (OSError, ValueError) as exc:
        return cfg, f"{CONFIG} is unreadable ({exc}); running with defaults."
    if not isinstance(loaded, dict):
        return cfg, f"{CONFIG} must hold a JSON object; running with defaults."
    unknown = sorted(set(loaded) - set(DEFAULTS))
    cfg.update(loaded)
    if unknown:
        return cfg, f"{CONFIG} has unknown key(s): {', '.join(unknown)}."
    return cfg, None


def is_off(root, cfg):
    return (
        os.environ.get("RUFF_GATE", "").lower() == "off"
        or os.path.exists(os.path.join(root, OFF))
        or not cfg.get("enabled", True)
    )


# --- modes ------------------------------------------------------------------


def mode_lint(event, root, cfg, state):
    path = (event.get("tool_input") or {}).get("file_path") or ""
    if not path.endswith(".py") or not os.path.isfile(path):
        return 0, ""
    path = os.path.abspath(path)
    if not within(path, root) or governing_config(path, root) is None:
        return 0, ""

    # Recorded before anything below can bail, because this is what scope
    # "session" reads at Stop — a file whose lint never ran still has to be
    # checked there.
    state["files"] = sorted(set(state.get("files") or []) | {path})

    command = command_for(root, ".", cfg, state)
    if command is None:
        return 0, ""
    report = violations([*command, "check", os.path.relpath(path, root)], root)
    return (2, report) if report else (0, "")


def gate_session(root, cfg, state):
    live = [
        os.path.relpath(path, root)
        for path in sorted(state.get("files") or [])
        if path.endswith(".py")
        and os.path.isfile(path)
        and governing_config(path, root)
    ]
    if not live:
        return "", []
    command = command_for(root, ".", cfg, state)
    if command is None:
        return "", []

    shown = " ".join(command)
    paths = " ".join(live)
    sections = []
    report = violations([*command, "check", *live], root)
    if report:
        sections.append(("lint", report, f"{shown} check --fix {paths}"))
    if cfg.get("format"):
        report = violations([*command, "format", "--check", *live], root)
        if report:
            sections.append(("format", report, f"{shown} format {paths}"))

    plural = "" if len(live) == 1 else "s"
    return f"{len(live)} file{plural} this turn", sections


def gate_tree(root, cfg, state):
    dirs = cfg.get("dirs") or discover_dirs(root)
    sections = []
    for name in dirs:
        directory = os.path.join(root, name)
        if not os.path.isdir(directory):
            continue
        command = command_for(directory, name, cfg, state)
        if command is None:
            continue
        label = "root" if name == "." else name
        prefix = "" if name == "." else f"cd {name} && "
        shown = " ".join(command)

        report = violations([*command, "check", "."], directory)
        if report:
            fix = f"{prefix}{shown} check --fix ."
            sections.append((f"{label} (lint)", report, fix))
        if cfg.get("format"):
            report = violations([*command, "format", "--check", "."], directory)
            if report:
                fix = f"{prefix}{shown} format ."
                sections.append((f"{label} (format)", report, fix))
    scope = " + ".join("root" if name == "." else name for name in dirs)
    return scope, sections


def mode_gate(event, root, cfg, state, complaint):
    gate = gate_tree if cfg.get("scope") == "tree" else gate_session
    scope, sections = gate(root, cfg, state)
    if not sections:
        return (2, "ruff-gate: " + complaint) if complaint else (0, "")

    lines = [f"ruff violations ({scope}):"]
    for label, report, fix in sections:
        lines.append(f"--- {label} ---")
        lines.append(report)
        lines.append("  fix: " + fix)
    if complaint:
        lines.append("ruff-gate: " + complaint)
    return 2, "\n".join(lines)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("lint", "gate"):
        return 0
    try:
        event = json.load(sys.stdin)
    except ValueError:
        event = {}
    if not isinstance(event, dict):
        event = {}

    launched = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd")
    root = os.path.abspath(launched or os.getcwd())
    cfg, complaint = load_config(root)
    if is_off(root, cfg):
        return 0

    state = load_state(event)
    if mode == "lint":
        code, message = mode_lint(event, root, cfg, state)
    else:
        code, message = mode_gate(event, root, cfg, state, complaint)
    # An empty state means nothing here concerned us, and a gate installed
    # globally would otherwise leave a file behind for every session in every
    # repo it correctly ignored.
    if state:
        save_state(event, state)

    if message:
        sys.stderr.write(message + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
