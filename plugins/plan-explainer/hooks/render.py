#!/usr/bin/env python3
"""Render a plan's `## Explainer` section to HTML when the plan goes up for approval.

Runs as a PreToolUse hook on ExitPlanMode, so the page opens while the approval
prompt waits. Plan mode lets the model write only the plan file; this hook is
how the explainer leaves it. Claude Code injects the plan text and its path into
`tool_input` (`plan`, `planFilePath`); the file is the fallback when the text
is absent.

Two files land beside the plan: `<stem>.explainer.html`, a full document opened
locally, and `<stem>.artifact.html`, the same page as a bare fragment, because
the Artifact publisher wraps a page in its own doctype and head. A plan with
no explainer removes both, so a re-plan never leaves a stale page to publish.

This is a renderer, never a gate: every path exits 0 or 1, never 2, so nothing
here can hold up a plan. `PLAN_EXPLAINER_NO_OPEN=1` skips the browser.
"""

import html
import json
import os
import re
import subprocess
import sys
import webbrowser

TEMPLATE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "explainer_template.html"
)
# "## Explainer: Crash Toggle Row" names the page; a bare "## Explainer" falls back to the plan's heading.
EXPLAINER_HEADING = re.compile(r"^## Explainer\b(?::\s*(.*\S))?")
SECTION_END = re.compile(r"^#{1,2} ")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
PLAN_TITLE = re.compile(r"^# (.+)$", re.MULTILINE)
TITLE_SEPARATOR = re.compile(r":\s+|\s+[—–-]\s+")
# A heading often opens with a label, not a name: "Plan: …", "ui-ux #186 — …".
TITLE_LABEL = re.compile(r"^(plan|.*#\d+.*)$", re.IGNORECASE)
TITLE_MAX_WORDS = 10
DOCUMENT_HEAD = (
    '<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
)
FALLBACK_TITLE = "Plan Explainer"


def extract_explainer(plan):
    return explainer_section(plan)[1]


def explainer_section(plan):
    """(name, text) of the `## Explainer` section, up to the next `#` or `##` heading, both
    outside fences; text is None when there is no section, name None when the heading is bare."""
    name = None
    body = None
    fence = None  # (marker character, length) of the open fence
    for line in plan.replace("\r\n", "\n").split("\n"):
        if fence is None:
            heading = EXPLAINER_HEADING.match(line) if body is None else None
            if heading:
                name = heading.group(1) or None
                body = []
                continue
            if body is not None and SECTION_END.match(line):
                break
        if body is not None:
            body.append(line)
        match = FENCE.match(line)
        if match:
            marker, rest = match.groups()
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1] and not rest.strip():
                fence = None
    text = "\n".join(body).strip() if body is not None else ""
    return name, text or None


def plan_heading(plan):
    match = PLAN_TITLE.search(plan)
    return match.group(1).strip() if match else FALLBACK_TITLE


def page_title(heading):
    """A name for the gallery: the heading minus any leading label and trailing explanation."""
    parts = TITLE_SEPARATOR.split(heading, maxsplit=1)
    if len(parts) == 2 and TITLE_LABEL.match(parts[0].strip()):
        heading = parts[1]
        parts = TITLE_SEPARATOR.split(heading, maxsplit=1)
    title = parts[0] if len(parts) == 2 and len(parts[0].split()) >= 2 else heading
    if len(title.split()) > TITLE_MAX_WORDS:
        clause = title.split(", ", 1)[0]
        words = clause.split()
        title = clause if len(words) <= TITLE_MAX_WORDS else " ".join(words[:8]) + "…"
    return title.strip() or FALLBACK_TITLE


def embed_json(text):
    # Inside <script>, only `</` can end the block; escaping every `<`, `>` and `&`
    # also keeps `<!--` from switching the parser into its script-data escape state.
    return (
        json.dumps(text, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def render_fragment(plan, explainer, name=None):
    heading = plan_heading(plan)
    with open(TEMPLATE, encoding="utf-8") as fh:
        template = fh.read()
    return (
        template.replace("{{TITLE}}", html.escape(name or page_title(heading)))
        .replace("{{HEADING}}", html.escape(heading))
        .replace("{{SOURCE_JSON}}", embed_json(explainer))
    )


def output_paths(plan_file_path):
    stem = os.path.splitext(plan_file_path)[0]
    return stem + ".explainer.html", stem + ".artifact.html"


def write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main():
    try:
        tool_input = json.load(sys.stdin).get("tool_input") or {}
    except (ValueError, AttributeError) as exc:
        print(f"plan-explainer: unreadable hook input ({exc})", file=sys.stderr)
        return 1

    plan_file_path = tool_input.get("planFilePath")
    plan = tool_input.get("plan")
    if plan is None and plan_file_path:
        try:
            with open(plan_file_path, encoding="utf-8") as fh:
                plan = fh.read()
        except OSError as exc:
            print(f"plan-explainer: cannot read the plan ({exc})", file=sys.stderr)
            return 1
    if not plan or not plan_file_path:
        return 0

    name, explainer = explainer_section(plan)
    if explainer is None:
        # A re-plan that dropped its explainer must not leave the old page to be published.
        for path in output_paths(plan_file_path):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                print(f"plan-explainer: cannot remove {path} ({exc})", file=sys.stderr)
                return 1
        return 0

    try:
        fragment = render_fragment(plan, explainer, name)
        local_path, artifact_path = output_paths(plan_file_path)
        write(local_path, DOCUMENT_HEAD + fragment)
        write(artifact_path, fragment)
    except OSError as exc:
        print(f"plan-explainer: cannot write the explainer ({exc})", file=sys.stderr)
        return 1

    if os.environ.get("PLAN_EXPLAINER_NO_OPEN") != "1":
        open_page(local_path)
    return 0


def open_page(path):
    # webbrowser falls back to a console browser (lynx, w3m) on a headless Linux box and
    # waits for it to exit, which would hold ExitPlanMode until the hook times out.
    if sys.platform == "darwin":
        subprocess.Popen(
            ["open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    elif (
        os.name == "nt"
        or os.environ.get("DISPLAY")
        or os.environ.get("WAYLAND_DISPLAY")
    ):
        webbrowser.open("file://" + os.path.abspath(path))


if __name__ == "__main__":
    sys.exit(main())
