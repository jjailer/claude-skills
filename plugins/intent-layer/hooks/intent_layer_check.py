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
commit runs, which is why both sections point at `--amend`. The same ordering
means the index is read *before* the command runs, so staging done inside the
command itself (`git add f && git commit`) has to be predicted from the command.

Replay mode — `intent_layer_check.py --replay [N]` — runs the node section's
resolution over the last N commits on HEAD and prints how often it would have
fired, for capture's health check. It shares the resolver with the hook, so it
measures the rule the hook actually applies.
"""

import glob
import json
import os
import re
import shlex
import subprocess
import sys
import time

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
STATE_TTL_SECONDS = 14 * 24 * 3600
REPLAY_DEFAULT = 30

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
SESSION_ID = re.compile(r"[\w-]+")

# --- command parsing --------------------------------------------------------
# git's own global options that consume the following token. Everything else
# before the subcommand is a flag or carries its value after `=`.
GIT_GLOBAL_WITH_VALUE = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env",
     "--super-prefix", "--list-cmds"}
)
# Short options of `git commit` whose value is the rest of the cluster or the
# next token — so a message can never be mistaken for `-a`.
COMMIT_SHORT_WITH_VALUE = frozenset("mFCct")
# Short options whose value can only be attached (`-S<key>`, `-uno`).
COMMIT_SHORT_ATTACHED = frozenset("Su")
COMMIT_LONG_WITH_VALUE = frozenset(
    {"--message", "--file", "--reuse-message", "--reedit-message", "--fixup",
     "--squash", "--author", "--date", "--cleanup", "--trailer", "--template",
     "--pathspec-from-file"}
)
ADD_LONG_WITH_VALUE = frozenset({"--pathspec-from-file", "--chmod"})


def git(cwd, *args):
    """Run git, returning its stdout lines. Any failure yields no lines.

    `core.quotepath=off` because resolution is textual: git otherwise quotes
    any non-ASCII path ("sub/caf\\303\\251.py"), whose leading quote puts it in
    a directory that holds no node.
    """
    try:
        result = subprocess.run(
            ("git", "-c", "core.quotepath=off", *args),
            cwd=cwd, capture_output=True, text=True, timeout=10,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    return result.stdout.splitlines() if result.returncode == 0 else []


def ignores_local_nodes(top, prefix=()):
    """Whether this repo is set up to keep its intent layer out of the commit.

    The gitignore entry is the mode marker, and it costs one git call instead of
    a tree walk. `/intent-layer:capturing-intent-layer` writes it as the gate
    before the first local node exists, so the signal is present from the start
    of a campaign rather than after the first node lands.

    `-q` is deliberately omitted: `git()` reports failure as no output, which a
    quiet run cannot be told apart from "not ignored". Without it the path is
    echoed when ignored, so the two cases differ in stdout.
    """
    return bool(git(top, *prefix, "check-ignore", LOCAL_NODE))


# --- which files the commit will contain -------------------------------------


OPERATOR_UNIT = re.compile(r"&>>?|[<>]+[&|]?|&&|\|\||\|&|;;|[;&|()\n]")
FALLBACK_SPLIT = re.compile(r"(&&|\|\||;|(?<![<>])&(?![<>])|(?<![<>])\|(?![<>])|[()\n])")


def shell_segments(command):
    """Split a shell command into simple commands, each a list of words.

    Only as much shell as deciding "is this a commit, and what does it stage"
    needs: quoting, the list and pipe operators, newlines, redirections, and
    heredoc bodies (whose lines are data, not commands). Anything subtler —
    `$(...)`, `bash -c`, aliases — is not a commit as far as this hook knows,
    which fails quiet rather than loud.

    An unbalanced quote makes shlex give up entirely; that is usually an
    apostrophe in an unquoted heredoc body, so fall back to a plain split
    rather than going silent on the commit in front of it.

    A `#` opens a comment only as the first word of a command. shlex cannot
    say whether a word was quoted, and treating a quoted `"#12: fix"` message
    as a comment would drop the pathspecs after it.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars="();<>|&\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    tokens = []
    try:
        for token in lexer:
            if token and all(ch in "();<>|&\n" for ch in token):
                tokens.extend((unit, "op") for unit in OPERATOR_UNIT.findall(token))
            else:
                tokens.append((token, "word"))
    except ValueError:
        tokens = []
        for piece in FALLBACK_SPLIT.split(command):
            if FALLBACK_SPLIT.fullmatch(piece):
                tokens.append((piece, "op"))
            else:
                tokens.extend((word, "raw") for word in piece.split())

    segments, current = [], []
    pending, delimiter, line_start = [], None, False
    i = 0
    while i < len(tokens):
        text, kind = tokens[i]
        i += 1
        if delimiter is not None:
            # Inside a heredoc body: skip to the line holding only the delimiter.
            if line_start and text == delimiter and (i == len(tokens) or tokens[i][0] == "\n"):
                delimiter = pending.pop(0) if pending else None
            line_start = text == "\n"
            continue
        if kind == "op":
            redirect = bool(re.match(r"&?[<>]", text))
        else:
            redirect = kind == "raw" and bool(re.match(r"\d*&?[<>]", text))
        if not redirect and kind == "op":
            if current:
                segments.append(current)
                current = []
            if text == "\n" and pending:
                delimiter, line_start = pending.pop(0), True
            continue
        if redirect:
            # Drop the operator, its target, and a bare fd number before it.
            if kind == "op" and current and current[-1].isdigit():
                current.pop()
            target = re.sub(r"^\d*&?[<>]+[&|-]?", "", text) if kind == "raw" else ""
            if not target and i < len(tokens) and tokens[i][1] != "op":
                target = tokens[i][0]
                i += 1
            if re.match(r"\d*<<(?!<)", text):
                pending.append(target.lstrip("-").strip("'\""))
            continue
        if not current and text.startswith("#"):
            while i < len(tokens) and tokens[i][0] != "\n":
                i += 1
            continue
        current.append(text)
    if current:
        segments.append(current)
    return segments


def git_invocation(words, cwd):
    """Parse one simple command as git: (subcommand, args, cwd, prefix) or None.

    Global options are walked properly so that `git -C sub commit` is a commit
    and `git commit-tree` is not. `-C` moves the effective cwd; `--git-dir` and
    `--work-tree` are carried as an absolute prefix for every later git call.
    """
    words = list(words)
    while words and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0], re.DOTALL):
        words.pop(0)
    if not words or os.path.basename(words[0]) != "git":
        return None
    prefix = []
    i = 1
    while i < len(words):
        word = words[i]
        if not word.startswith("-"):
            return word, words[i + 1:], cwd, tuple(prefix)
        name, eq, value = word.partition("=")
        if name in GIT_GLOBAL_WITH_VALUE and not eq:
            if i + 1 >= len(words):
                return None
            value = words[i + 1]
            i += 1
        if name == "-C":
            cwd = os.path.join(cwd, os.path.expanduser(value))
        elif name in ("--git-dir", "--work-tree"):
            prefix.append(f"{name}={os.path.join(cwd, os.path.expanduser(value))}")
        i += 1
    return None


def parse_command(command, cwd):
    """The first `git commit` in the command, and the `git add`s that precede it.

    Returns None when the command commits nothing. Each invocation carries the
    cwd it will actually run in, tracked across `cd`, because relative
    pathspecs mean nothing without it.
    """
    adds = []
    for words in shell_segments(command):
        stripped = [w for w in words if not re.fullmatch(r"[A-Za-z_]\w*=.*", w, re.DOTALL)]
        if stripped and stripped[0] in ("cd", "pushd"):
            targets = [w for w in stripped[1:] if not w.startswith("-")]
            target = os.path.expanduser(targets[0]) if targets else os.path.expanduser("~")
            cwd = os.path.normpath(os.path.join(cwd, target))
            continue
        invocation = git_invocation(words, cwd)
        if not invocation:
            continue
        subcommand = invocation[0]
        if subcommand == "add":
            adds.append(invocation)
        elif subcommand == "commit":
            return invocation, adds
    return None


def split_commit_args(args):
    """(sweeps tracked files, --include, pathspecs) from `git commit`'s own words.

    `-a` is read only from this commit's option tokens: short clusters count
    (`-am`), but an option's value never does, so neither `-m "fix -all"` nor
    an `ls -la` earlier in the command sweeps anything in.
    """
    sweep = include = False
    paths = []
    i = 0
    while i < len(args):
        word = args[i]
        i += 1
        if word == "--":
            paths.extend(args[i:])
            break
        if word.startswith("--"):
            name, eq, _ = word.partition("=")
            if name == "--all":
                sweep = True
            elif name == "--include":
                include = True
            elif name in COMMIT_LONG_WITH_VALUE and not eq:
                i += 1
            continue
        if word.startswith("-") and len(word) > 1:
            for pos, flag in enumerate(word[1:], start=1):
                if flag in COMMIT_SHORT_WITH_VALUE:
                    if pos == len(word) - 1:
                        i += 1
                    break
                if flag in COMMIT_SHORT_ATTACHED:
                    break
                if flag == "a":
                    sweep = True
                elif flag == "i":
                    include = True
            continue
        paths.append(word)
    return sweep, include, paths


def added_paths(invocation, top):
    """Root-relative paths a `git add` in the same command is about to stage."""
    _, args, cwd, prefix = invocation
    everything = update = dry_run = False
    paths = []
    i = 0
    while i < len(args):
        word = args[i]
        i += 1
        if word == "--":
            paths.extend(args[i:])
            break
        if word.startswith("--"):
            name, eq, _ = word.partition("=")
            everything |= name == "--all"
            update |= name == "--update"
            dry_run |= name == "--dry-run"
            if name in ADD_LONG_WITH_VALUE and not eq:
                i += 1
        elif word.startswith("-") and len(word) > 1:
            everything |= "A" in word
            update |= "u" in word
            dry_run |= "n" in word
        else:
            paths.append(word)
    if dry_run:
        return set()
    if paths:
        kinds = ("-m", "-d") if update and not everything else ("-m", "-d", "-o")
        return set(git(cwd, *prefix, "ls-files", *kinds, "--exclude-standard",
                       "--full-name", "--", *paths))
    found = set()
    if everything or update:
        found |= set(git(top, *prefix, "diff", "--name-only"))
    if everything:
        found |= set(git(top, *prefix, "ls-files", "-o", "--exclude-standard", "--full-name"))
    return found


def committed_paths(commit, adds, top):
    """Root-relative paths the commit will contain, predicted before it runs.

    The index is only a starting point: PreToolUse fires before the command, so
    anything staged by the command itself is invisible to `diff --cached`.

    A pathspec commit (`git commit <paths>`, without `--include`) commits
    exactly those paths and nothing else that is staged, so it replaces the
    index view rather than adding to it.
    """
    _, args, cwd, prefix = commit
    sweep, include, paths = split_commit_args(args)
    added = set()
    for invocation in adds:
        added |= added_paths(invocation, top)
    staged = set(git(top, *prefix, "diff", "--cached", "--name-only")) | added
    if sweep:
        staged |= set(git(top, *prefix, "diff", "--name-only"))
    if not paths:
        return staged
    named = set(git(cwd, *prefix, "diff", "--cached", "--name-only", "--", *paths))
    named |= set(git(cwd, *prefix, "diff", "--name-only", "--", *paths))
    untracked = git(cwd, *prefix, "ls-files", "-o", "--exclude-standard", "--full-name",
                    "--", *paths)
    named |= added & set(untracked)
    return staged | named if include else named


# --- which nodes those files implicate ---------------------------------------


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


def struck(node, files, changed_nodes, root, local_clock=True):
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

    Replay passes `local_clock=False`: today's mtimes say nothing about a
    commit from last month, so a local node is never struck there.
    """
    if os.path.basename(node) != LOCAL_NODE:
        return node in changed_nodes
    if not local_clock:
        return False
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


def implicated_nodes(changed, nodes, root, local_clock=True):
    """Map each unaccompanied node to the changed files that implicate it."""
    changed_nodes = {p for p in changed if os.path.basename(p) == NODE}
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
        if not struck(node, files, changed_nodes, root, local_clock)
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


# --- harvest ------------------------------------------------------------------


def session_id(event):
    """The session id, only if it is safe to use as a file name and glob."""
    session = event.get("session_id")
    return session if isinstance(session, str) and SESSION_ID.fullmatch(session) else None


def transcript_path(event, cwd):
    """Locate this session's transcript, preferring what the event tells us.

    `transcript_path` is documented as common to every hook payload, but no
    captured PreToolUse payload was available to confirm it, so the derived
    path is a real fallback rather than defensive padding: Claude Code stores
    transcripts at ~/.claude/projects/<slug>/<session_id>.jsonl, where the slug
    is the absolute cwd with both "/" and "." replaced by "-".
    """
    direct = event.get("transcript_path")
    if isinstance(direct, str) and direct and os.path.isfile(direct):
        return direct

    session = session_id(event)
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
    newest, newest_mtime = None, None
    try:
        names = os.listdir(directory)
    except OSError:
        return None
    for name in names:
        if not name.endswith(".jsonl"):
            continue
        candidate = os.path.join(directory, name)
        # Stat each one separately: a transcript can vanish between the listing
        # and the stat, and that must cost one candidate, not the hook.
        try:
            mtime = os.path.getmtime(candidate)
        except OSError:
            continue
        if newest_mtime is None or mtime > newest_mtime:
            newest, newest_mtime = candidate, mtime
    return newest


def _text(content):
    """Flatten a tool_result content field, which is a str or a block list."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b["text"] for b in content if isinstance(b, dict) and isinstance(b.get("text"), str)
        )
    return ""


def _key(value):
    """A value usable as a dict key, or None. Transcript ids are untrusted."""
    return value if isinstance(value, str) else None


def scan_session(path, roots=()):
    """One pass over the transcript, returning raw counts per signal family.

    Sidechain (subagent) turns are skipped throughout: a subagent's retries are
    its own business and it cannot carry a lesson back into the intent layer.

    `roots` confines the churn signal to files inside the repo. Without it, plan
    files under ~/.claude/plans dominate: replaying real sessions they were
    edited 7-14 times apiece and appeared in most false fires. Iterating on a
    plan is the process working, and it says nothing about the code.

    Every field is type-checked before use. A line of a shape this scan does
    not expect is skipped, because a crash here would take the node section
    down with it.
    """
    prefixes = tuple(os.path.abspath(root) + os.sep for root in roots)
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
            if not isinstance(entry, dict) or entry.get("isSidechain"):
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
                    name = _key(block.get("name")) or ""
                    data = block.get("input")
                    if not isinstance(data, dict):
                        data = {}
                    tool_id = _key(block.get("id"))
                    if tool_id:
                        tools[tool_id] = (name, data)
                    if name in ("Edit", "Write", "NotebookEdit"):
                        target = _key(data.get("file_path")) or ""
                        inside = not prefixes or os.path.abspath(target).startswith(prefixes)
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
                    name, data = tools.get(_key(block.get("tool_use_id")), ("", {}))
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
                        command = (_key(data.get("command")) or "").split()
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
    """Turn raw counts into (identity, evidence line) pairs, one per tripped family.

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

    The identity names *what* the friction is and never how many times it
    happened. It is what dedupe remembers: keyed on the rendered line, a count
    going from 2 to 3 would read as brand-new friction on every later commit.
    """
    evidence = []

    worst = max(scan["test_fails"].items(), key=lambda kv: kv[1], default=None)
    if worst and worst[1] >= 2 and scan["edit_between_failures"]:
        evidence.append(
            (f"test_fail:{worst[0]}", f"{worst[0]} failed {worst[1]}x across fix attempts")
        )

    for command, count in sorted(
        scan["bash_errors"].items(), key=lambda kv: -kv[1]
    )[:1]:
        if count >= 2:
            evidence.append((f"bash_error:{command}", f"`{command}` errored {count}x"))

    if scan["corrections"] >= 2:
        evidence.append(("corrections", f"you corrected course {scan['corrections']}x"))

    for tool, count in sorted(scan["denials"].items(), key=lambda kv: -kv[1])[:1]:
        if count >= 2:
            evidence.append((f"denial:{tool}", f"{tool or 'a tool'} was denied {count}x"))

    busiest = max(scan["edits"].items(), key=lambda kv: kv[1], default=None)
    if busiest and busiest[1] >= 6:
        evidence.append((f"edit_churn:{busiest[0]}", f"{busiest[0]} edited {busiest[1]}x"))

    return evidence


def harvest_state(session):
    """Friction identities already reported this session, and a writer to add more.

    Kept under ~/.claude rather than the repo so a harvest can never show up in
    `git status`. Keyed by session, and a session id never recurs, so each
    write also sweeps out files untouched for STATE_TTL_SECONDS — otherwise the
    directory would grow by one file per session forever.
    """
    path = os.path.join(STATE_DIR, f"{session or 'unknown'}.json")
    try:
        with open(path, encoding="utf-8") as handle:
            loaded = json.load(handle)
        reported = {item for item in loaded if isinstance(item, str)}
    except (OSError, ValueError, TypeError):
        reported = set()

    def remember(identities):
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(sorted(reported | set(identities)), handle)
        except OSError:
            pass
        cutoff = time.time() - STATE_TTL_SECONDS
        try:
            names = os.listdir(STATE_DIR)
        except OSError:
            return
        for name in names:
            stale = os.path.join(STATE_DIR, name)
            try:
                if os.path.getmtime(stale) < cutoff:
                    os.remove(stale)
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
        "Name each one in one sentence — what you assumed, what was actually true. Check it "
        "against the harvesting-pitfalls skill's bar and pre-filters, then route it down the "
        "intent-layer skill's *Where a rule belongs* table; the first row that fits wins, and "
        "most sessions land on \"drop it\"."
    )
    lines.append(
        "Land it in the commit this hook fired on: once `git log -1` shows it landed, "
        "`git commit --amend --no-edit` folds it in. Nothing durable came out of it? Say so in "
        "one line and move on — iteration is not a pitfall."
    )
    return "\n".join(lines)


def harvest(event, cwd, top):
    """The harvest section, or None. Owns its own quiet ladder."""
    path = transcript_path(event, cwd)
    if not path:
        return None
    scan = scan_session(path, (cwd, top))
    if not scan:
        return None
    evidence = qualifies(scan)
    if len(evidence) < FAMILIES_TO_FIRE:
        return None

    reported, remember = harvest_state(session_id(event))
    # Re-arm only on genuinely new friction. Without this the same two signals
    # would be re-reported on every commit for the rest of the session.
    fresh = [text for identity, text in evidence if identity not in reported]
    if len(fresh) < FAMILIES_TO_FIRE:
        return None
    remember(identity for identity, _ in evidence)
    return render_harvest(fresh)


# --- entry points -------------------------------------------------------------


def toplevel(cwd, prefix=()):
    lines = git(cwd, *prefix, "rev-parse", "--show-toplevel")
    return lines[0] if lines else None


def replay(argv):
    """Print how often the node section would have fired over recent history.

    Resolved against the nodes that exist *now*, with the hook's own resolver,
    so the number answers "would the layer as it stands be noisy?". A committed
    node is struck by appearing in the commit, exactly as at commit time. A
    local node leaves no trace in history, so it is never struck, and any count
    resting on one is an upper bound — `local_upper_bound` says when that is so.
    """
    try:
        limit = max(int(argv[0]), 0) if argv else REPLAY_DEFAULT
    except ValueError:
        limit = REPLAY_DEFAULT
    top = toplevel(os.getcwd())
    shas = git(top, "log", "--no-merges", "-n", str(limit), "--format=%H") if top else []
    nodes = {
        p for p in git(top, "ls-tree", "-r", "--name-only", "HEAD")
        if os.path.basename(p) == NODE
    } if top else set()

    fired, counts, local = 0, {}, False
    for sha in shas:
        files = [p for p in git(top, "show", "--name-only", "--format=", sha) if p]
        found = implicated_nodes(files, nodes, top, local_clock=False)
        if found:
            fired += 1
        for node in found:
            counts[node] = counts.get(node, 0) + 1
            local |= os.path.basename(node) == LOCAL_NODE
    json.dump(
        {
            "commits": len(shas),
            "fired": fired,
            "rate": fired / len(shas) if shas else 0.0,
            "local_upper_bound": local,
            "nodes": dict(sorted(counts.items())),
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    return 0


def main():
    if sys.argv[1:2] == ["--replay"]:
        return replay(sys.argv[2:])

    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return 0
    if not isinstance(event, dict) or event.get("tool_name") != "Bash":
        return 0
    tool_input = event.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return 0

    cwd = event.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()
    parsed = parse_command(command, cwd)
    if not parsed:
        return 0
    commit, adds = parsed
    prefix = commit[3]
    top = toplevel(commit[2], prefix)
    if not top:
        return 0

    # The two sections are independent. The harvest must be able to speak when
    # no node is implicated at all — that is the common case for a pitfall
    # whose home is a hook or a skill rather than a node — and when nothing is
    # staged, as with `git commit --amend --no-edit` after a session of work.
    harvested = harvest(event, cwd, top)

    changed = committed_paths(commit, adds, top)
    found = {}
    if changed:
        changed_nodes = {p for p in changed if os.path.basename(p) == NODE}
        # Union with staged nodes: a node created by this commit isn't tracked yet.
        nodes = {
            p for p in git(top, *prefix, "ls-files", "--", f"*{NODE}")
            if os.path.basename(p) == NODE
        } | changed_nodes
        found = implicated_nodes(changed, nodes, top)

    sections = [
        render(found, ignores_local_nodes(top, prefix)) if found else None,
        harvested,
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
    # Last line of defence for "exit 0 on every path". Every known input shape
    # is checked where it is read; this catches the one nobody predicted — most
    # likely a shell construct the command parser has never seen. A hook that
    # errors on a commit is a hook that gets removed, and a missed reminder
    # costs far less than that.
    try:
        status = main()
    except Exception:
        status = 0
    sys.exit(status)
