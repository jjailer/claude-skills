#!/usr/bin/env python3
"""PreToolUse hook: two commit-time reminders about the intent layer.

Node section — speaks when a commit touches code under a node it leaves
untouched. A commit that updates code and its node together is silent.

Two node kinds, two ways to be struck. A committed CLAUDE.md is struck by
appearing in the commit. A gitignored CLAUDE.local.md never can, so it is
struck by being newer than the code that implicates it — the same "you did the
work" test read off the clock instead of off the diff.

Harvest section — speaks when the session shows independent signs of a
recurring pitfall, so the friction gets routed into the intent layer instead of
evaporating. The script never judges whether something *is* a pitfall; it only
decides whether the session was eventful enough to be worth one paragraph, and
cites the evidence. The model that lived the session does the judging — it
knows what it assumed, which is the whole value and is unrecoverable from a
transcript alone.

Ordering caveat: a PreToolUse hook that returns additionalContext without a
permissionDecision does not stop the tool. The model reads this *after* the
commit runs, which is why both sections point at `--amend`.
"""

import glob
import json
import os
import re
import subprocess
import sys

NODE = "CLAUDE.md"
# The personal tier: gitignored, loads right after CLAUDE.md in the same
# directory, and is the node you can act on in a repo whose CLAUDE.md is not
# yours to change. Local wins a directory holding both, for that reason.
LOCAL_NODE = "CLAUDE.local.md"

# --- harvest tuning ---------------------------------------------------------
# Fire only when this many independent signal families trip. One family alone
# is ordinary iteration; the bar is deliberately set where a real session
# rarely reaches it. Calibrated against replayed sessions — see README.
FAMILIES_TO_FIRE = 2
MAX_EVIDENCE_LINES = 3
STATE_DIR = os.path.expanduser("~/.claude/intent-layer/harvest")

# A user turn opening with one of these is plausibly a correction. Crude on
# purpose: the model re-judges every line it is shown, so a false positive
# costs a sentence, while a clever regex that misses real corrections costs the
# whole feature.
CORRECTION = re.compile(
    r"^(no[,.! ]|nope\b|actually\b|that'?s wrong\b|don'?t\b|stop\b|"
    r"i said\b|revert\b|undo\b|why did you\b|you (?:broke|missed|forgot)\b)",
    re.IGNORECASE,
)
# pytest node ids, in either order the runner prints them.
TEST_ID = re.compile(r"(?:^|\s)(?:FAILED|ERROR)\s+(\S+::\S+)|(\S+::\S+)\s+(?:FAILED|ERROR)")
DENIED = "The user doesn't want to proceed with this tool use"
TEST_PATH = re.compile(r"(^|/)(tests?|spec|__tests__)/|(^|/)test_[^/]*$|_test\.[a-z]+$")
# Denying one of these is the review gate working, not friction worth routing.
# Replaying real sessions, "ExitPlanMode was denied 2x" was the single largest
# source of false fires — it means a plan got iterated on, which is the point.
CONVERSATIONAL = frozenset(
    {"ExitPlanMode", "AskUserQuestion", "EnterPlanMode", "TaskCreate", "TaskUpdate"}
)


def git(cwd, *args):
    """Run git, returning its stdout lines. Any failure yields no lines."""
    try:
        result = subprocess.run(
            ("git", *args), cwd=cwd, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return result.stdout.splitlines() if result.returncode == 0 else []


def ignores_local_nodes(cwd):
    """Whether this repo is set up to keep its intent layer out of the commit.

    The gitignore entry is the mode marker, and it costs one git call instead of
    a tree walk. `/capture-intent-layer` writes it as the gate before the first
    local node exists, so the signal is present from the start of a campaign
    rather than after the first node lands.

    `-q` is deliberately omitted: `git()` reports failure as no output, which a
    quiet run cannot be told apart from "not ignored". Without it the path is
    echoed when ignored, so the two cases differ in stdout.
    """
    return bool(git(cwd, "check-ignore", LOCAL_NODE))


def sweeps_tracked_files(command):
    """True for `git commit -a` / `-am` / `--all`, which stage at commit time."""
    for token in command.split():
        if token.startswith("--"):
            if token == "--all":
                return True
        elif token.startswith("-") and "a" in token[1:]:
            return True
    return False


def has_local_node(directory, root, cache):
    """Whether a CLAUDE.local.md sits in `directory`, memoized per directory.

    Local nodes are gitignored, so `git ls-files` cannot enumerate them, and a
    tree walk on every commit is not affordable. Instead the lookup rides the
    ancestor climb below: a few stats per changed file, one per directory
    across the whole commit.
    """
    if directory not in cache:
        cache[directory] = os.path.isfile(os.path.join(root, directory, LOCAL_NODE))
    return cache[directory]


def nearest_node(path, nodes, root, cache):
    """Nearest ancestor node, resolved from the path string.

    Deliberately textual rather than filesystem-based so that deleted and
    renamed paths still resolve — a `git rm` under a node is exactly when that
    node most likely has a tombstone to prune. The one filesystem call is the
    CLAUDE.local.md check, which asks whether a file exists *now* rather than
    resolving a path out of the diff, so it leaves that property intact.

    A local node wins a directory holding both: it loads last, and in the case
    that puts it there — a repo whose CLAUDE.md is not yours to change — it is
    the only one of the two you can act on.

    The root node is reachable only from top-level files. It nominally sits
    above everything, so letting deep paths fall back to it would implicate it
    on nearly every commit in nearly every repo, and a reminder that always
    fires is one you learn to ignore. A directory whose changes deserve
    intent-layer attention deserves its own node.
    """
    directory = os.path.dirname(path)
    if not directory:
        if has_local_node("", root, cache):
            return LOCAL_NODE
        return NODE if NODE in nodes else None
    while directory:
        if has_local_node(directory, root, cache):
            return os.path.join(directory, LOCAL_NODE)
        candidate = os.path.join(directory, NODE)
        if candidate in nodes:
            return candidate
        directory = os.path.dirname(directory)
    return None


def struck(node, files, changed_nodes, root):
    """Whether the node counts as already updated for the work in this commit.

    A committed node is struck by appearing in the commit: the work is right
    there in the diff. A gitignored one never can appear there, so it is struck
    by being at least as new as the code implicating it — the same "you did the
    work" test read off the clock instead of off the diff, and it matches the
    order the work actually happens in: edit code, edit node, commit.

    Deletions deliberately cannot strike it. `os.path.getmtime` raises on a
    path that is gone, and a commit of pure deletions under a node is exactly
    when that node most likely has a tombstone to prune, so nothing is struck
    and the reminder fires.
    """
    if os.path.basename(node) != LOCAL_NODE:
        return node in changed_nodes
    newest = None
    for path in files:
        try:
            mtime = os.path.getmtime(os.path.join(root, path))
        except OSError:
            continue
        newest = mtime if newest is None else max(newest, mtime)
    if newest is None:
        return False
    try:
        return os.path.getmtime(os.path.join(root, node)) >= newest
    except OSError:
        return False


def implicated_nodes(changed, nodes, changed_nodes, root):
    """Map each unaccompanied node to the changed files that implicate it."""
    found = {}
    cache = {}
    for path in sorted(changed):
        if os.path.basename(path) in (NODE, LOCAL_NODE):
            continue
        node = nearest_node(path, nodes, root, cache)
        if node:
            found.setdefault(node, []).append(path)
    # Struck per node against its own files, not against the commit as a whole:
    # a change in a sibling subtree says nothing about whether this node is
    # current.
    return {
        node: files
        for node, files in found.items()
        if not struck(node, files, changed_nodes, root)
    }


def render(found, redirect=False):
    count = len(found)
    noun = "node" if count == 1 else "nodes"
    lines = [f"This commit changes code under {count} intent-layer {noun} it does not update:"]
    for node, files in sorted(found.items()):
        more = f" (+{len(files) - 1} more)" if len(files) > 1 else ""
        lines.append(f"  {node}  <- {files[0]}{more}")
    # A local node is gitignored, so it can never be in the commit. When every
    # implicated node is one, say *when* to update it instead of *where*.
    when = (
        "before you commit"
        if all(os.path.basename(node) == LOCAL_NODE for node in found)
        else "in this same commit"
    )
    lines.append(
        "Did contracts, invariants, traps, the sanctioned choice, or dependencies change? Update "
        f"or prune the node {when} — or state why it needs no change. Only what a "
        "model can't re-derive from the code earns a line. Rules: intent-layer skill."
    )
    # A committed node only reaches this list when no local node sits beside it
    # — the resolver would have preferred one. So in a repo that keeps its layer
    # local, every CLAUDE.md named above is one nobody here can edit, and the
    # answer is to start its sibling. Says this once per directory: the sibling
    # then wins the resolver, and the reminder goes back to normal.
    if redirect and any(os.path.basename(node) == NODE for node in found):
        lines.append(
            f"This repo gitignores {LOCAL_NODE}, so its intent layer is kept out of the commit. "
            f"If a {NODE} above isn't yours to edit, write what you learned to the {LOCAL_NODE} "
            "beside it instead — it loads immediately after, and supplements rather than replaces "
            "it. Never restate a line it already has."
        )
    return "\n".join(lines)


def transcript_path(event):
    """Locate this session's transcript, preferring what the event tells us.

    `transcript_path` is documented as common to every hook payload, but no
    captured PreToolUse payload was available to confirm it, so the derived
    path is a real fallback rather than defensive padding: Claude Code stores
    transcripts at ~/.claude/projects/<slug>/<session_id>.jsonl, where the slug
    is the absolute cwd with both "/" and "." replaced by "-".
    """
    direct = event.get("transcript_path")
    if direct and os.path.isfile(direct):
        return direct

    session = event.get("session_id")
    cwd = event.get("cwd") or os.getcwd()
    projects = os.path.expanduser("~/.claude/projects")
    slug = os.path.abspath(cwd).replace("/", "-").replace(".", "-")
    directory = os.path.join(projects, slug)
    if session:
        candidate = os.path.join(directory, f"{session}.jsonl")
        if os.path.isfile(candidate):
            return candidate
        # A session commits from wherever it happens to be, which is often not
        # the directory it started in — so the slug above can point at a real
        # directory belonging to some *other* session. Find this session's own
        # file wherever it lives, and give up if it isn't there. Harvesting a
        # different session's friction is worse than harvesting none.
        found = glob.glob(os.path.join(projects, "*", f"{session}.jsonl"))
        return found[0] if found else None
    try:
        files = [
            os.path.join(directory, name)
            for name in os.listdir(directory)
            if name.endswith(".jsonl")
        ]
    except OSError:
        return None
    return max(files, key=os.path.getmtime) if files else None


def _text(content):
    """Flatten a tool_result content field, which is a str or a block list."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "") for b in content if isinstance(b, dict)
        )
    return ""


def scan_session(path, cwd=None):
    """One pass over the transcript, returning raw counts per signal family.

    Sidechain (subagent) turns are skipped throughout: a subagent's retries are
    its own business and it cannot carry a lesson back into the intent layer.

    `cwd` confines the churn signal to files inside the repo. Without it, plan
    files under ~/.claude/plans dominate: replaying real sessions they were
    edited 7-14 times apiece and appeared in most false fires. Iterating on a
    plan is the process working, and it says nothing about the code.
    """
    root = os.path.abspath(cwd) + os.sep if cwd else None
    tools = {}           # tool_use_id -> (name, input)
    test_fails = {}      # test id -> count
    bash_errors = {}     # normalized command -> count
    denials = {}         # tool name -> count
    edits = {}           # file path -> count
    corrections = 0
    edit_between_failures = False
    seen_failure = False

    try:
        handle = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None

    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if entry.get("isSidechain"):
                continue

            kind = entry.get("type")
            message = entry.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")

            if kind == "assistant" and isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    name = block.get("name") or ""
                    data = block.get("input") or {}
                    tools[block.get("id")] = (name, data)
                    if name in ("Edit", "Write", "NotebookEdit"):
                        target = data.get("file_path") or ""
                        inside = not root or os.path.abspath(target).startswith(root)
                        if target and inside and not TEST_PATH.search(target):
                            edits[target] = edits.get(target, 0) + 1
                            if seen_failure:
                                edit_between_failures = True

            elif kind == "user":
                # A real user turn carries a plain string. Slash-command
                # plumbing (<command-name>, <local-command-stdout>) arrives the
                # same way and must not be mistaken for the user talking.
                if isinstance(content, str) and entry.get("promptId"):
                    stripped = content.strip()
                    if stripped and not stripped.startswith("<"):
                        if CORRECTION.match(stripped):
                            corrections += 1
                    continue
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    name, data = tools.get(block.get("tool_use_id"), ("", {}))
                    body = _text(block.get("content"))
                    was_test_run = False
                    for match in TEST_ID.finditer(body):
                        test_id = match.group(1) or match.group(2)
                        test_fails[test_id] = test_fails.get(test_id, 0) + 1
                        seen_failure = True
                        was_test_run = True
                    if not block.get("is_error"):
                        continue
                    if DENIED in body:
                        if name not in CONVERSATIONAL:
                            denials[name] = denials.get(name, 0) + 1
                    elif was_test_run:
                        # A failing test run is one event, not two. Counting the
                        # non-zero exit here as well would let a single red test
                        # trip two "independent" families and clear the bar on
                        # its own — which is the bar quietly deleting itself.
                        continue
                    elif name == "Bash":
                        command = (data.get("command") or "").split()
                        key = " ".join(command[:3])
                        if key:
                            bash_errors[key] = bash_errors.get(key, 0) + 1

    return {
        "test_fails": test_fails,
        "edit_between_failures": edit_between_failures,
        "bash_errors": bash_errors,
        "corrections": corrections,
        "denials": denials,
        "edits": edits,
    }


def qualifies(scan):
    """Turn raw counts into evidence lines, one per tripped signal family.

    Each family is a different *kind* of friction, so two of them agreeing is
    much stronger than one counter reaching two. The families, and why each
    threshold is where it is:

    S1  A test failing repeatedly is worthless on its own — red-green
        guarantees it. The intervening edit to a non-test file is what
        separates "a fix that didn't work" from a normal RED phase.
    S2  The same command erroring twice is a wrong-directory or wrong-flag
        loop, not a typo.
    S3  Two corrections mean the misunderstanding survived the first one.
    S4  A repeated permission denial routes to a settings allowlist, not the
        intent layer — but it is real friction and belongs in the count.
    S5  Weak. Churn on one file is a tiebreaker, never a reason on its own.
    """
    evidence = []

    worst = max(scan["test_fails"].items(), key=lambda kv: kv[1], default=None)
    if worst and worst[1] >= 2 and scan["edit_between_failures"]:
        evidence.append(f"{worst[0]} failed {worst[1]}x across fix attempts")

    for command, count in sorted(
        scan["bash_errors"].items(), key=lambda kv: -kv[1]
    )[:1]:
        if count >= 2:
            evidence.append(f"`{command}` errored {count}x")

    if scan["corrections"] >= 2:
        evidence.append(f"you corrected course {scan['corrections']}x")

    for tool, count in sorted(scan["denials"].items(), key=lambda kv: -kv[1])[:1]:
        if count >= 2:
            evidence.append(f"{tool or 'a tool'} was denied {count}x")

    busiest = max(scan["edits"].items(), key=lambda kv: kv[1], default=None)
    if busiest and busiest[1] >= 6:
        evidence.append(f"{busiest[0]} edited {busiest[1]}x")

    return evidence


def harvest_state(session):
    """Evidence already reported this session, and a writer to update it.

    Kept under ~/.claude rather than the repo so a harvest can never show up in
    `git status`, and keyed by session so it expires on its own.
    """
    path = os.path.join(STATE_DIR, f"{session or 'unknown'}.json")
    try:
        with open(path, encoding="utf-8") as handle:
            reported = set(json.load(handle))
    except (OSError, ValueError):
        reported = set()

    def remember(evidence):
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(sorted(reported | set(evidence)), handle)
        except OSError:
            pass

    return reported, remember


def render_harvest(evidence):
    lines = [
        f"This session shows {len(evidence)} signals of a recurring pitfall, "
        "not ordinary iteration:"
    ]
    lines.extend(f"  {item}" for item in evidence[:MAX_EVIDENCE_LINES])
    lines.append(
        "Name each one in one sentence — what you assumed, what was actually true — then route it:"
    )
    lines.append("  re-derivable by reading the code   -> drop it; context is not free")
    lines.append("  advisory rule you would ignore     -> PreToolUse hook")
    lines.append("  repeatable multi-step procedure    -> skill")
    lines.append("  non-derivable invariant or trap    -> nearest node")
    lines.append(
        "Land it in this commit (`git commit --amend --no-edit`; nothing is pushed yet). Nothing "
        "durable came out of it? Say so in one line and move on — iteration is not a pitfall. "
        "Rules: harvesting-pitfalls skill."
    )
    return "\n".join(lines)


def harvest(event):
    """The harvest section, or None. Owns its own quiet ladder."""
    path = transcript_path(event)
    if not path:
        return None
    scan = scan_session(path, event.get("cwd") or os.getcwd())
    if not scan:
        return None
    evidence = qualifies(scan)
    if len(evidence) < FAMILIES_TO_FIRE:
        return None

    reported, remember = harvest_state(event.get("session_id"))
    # Re-arm only on genuinely new friction. Without this the same two signals
    # would be re-reported on every commit for the rest of the session.
    fresh = [item for item in evidence if item not in reported]
    if len(fresh) < FAMILIES_TO_FIRE:
        return None
    remember(evidence)
    return render_harvest(fresh)


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

    found = implicated_nodes(changed, nodes, changed_nodes, cwd)

    # The two sections are independent. The harvest must be able to speak when
    # no node is implicated at all — that is the common case for a pitfall
    # whose home is a hook or a skill rather than a node.
    sections = [
        render(found, ignores_local_nodes(cwd)) if found else None,
        harvest(event),
    ]
    message = "\n\n".join(section for section in sections if section)
    if not message:
        return 0

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": message,
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
