"""Run with: python3 -m unittest discover -s plugins/plan-explainer/tests

The renderer runs on every ExitPlanMode, so the failures that matter are the
ones you would pay for on every plan: a browser tab for a plan with nothing to
show, a diagram whose source arrives altered, a file dropped into the repo you
are planning in, and a crash that holds up the approval prompt.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.normpath(os.path.join(TESTS, "..", "hooks", "render.py"))

_spec = importlib.util.spec_from_file_location("render", SCRIPT)
render = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render)

PLAN_WITHOUT_EXPLAINER = """# Fix the login timeout

## Context
The session expires early.

## Verification
Run the suite.
"""

PLAN_WITH_EXPLAINER = """# Scheduled send: queue messages for later

## Context
Users want to send later.

## Explainer

### Code map
```mermaid
flowchart LR
  A[compose]:::changed --> B[(scheduled_messages)]:::data
```

### Decisions
Chose a table over a cron entry.

## Verification
Run the suite.
"""

EXPECTED_EXPLAINER = """### Code map
```mermaid
flowchart LR
  A[compose]:::changed --> B[(scheduled_messages)]:::data
```

### Decisions
Chose a table over a cron entry."""

HOSTILE = """### Escapes
A plan can quote HTML: </script><script>alert(1)</script>, </SCRIPT x>, <!-- and &amp;.
```mermaid
flowchart LR
  A -->|"a < b && c > d"| B
```"""

TITLE_CASES = {
    "Plan: Fix the login timeout": "Fix the login timeout",
    "ui-ux #186 — Key-generation errors lose their DCError code": (
        "Key-generation errors lose their DCError code"
    ),
    "ui-ux #167 (new): Title loading chrome: a readiness bar and a per-launch quip": (
        "Title loading chrome"
    ),
    "ui-ux #143 (+ #131) — settle the server restore before play": (
        "settle the server restore before play"
    ),
    "Workflows × /test-ui — concurrency answer + confirming experiment": (
        "Workflows × /test-ui"
    ),
    "Plan-mode explainer: keep plan mode, render with a hook": "Plan-mode explainer",
    "Rename `a:b` key": "Rename `a:b` key",
    (
        "ui-ux #161 — Leaving Play during the “Stay” seconds strands the label, "
        "and the tap deals the next hand"
    ): "Leaving Play during the “Stay” seconds strands the label",
}

DOCUMENT_TAG = re.compile(r"<(!doctype|html|head|body)[\s>]", re.IGNORECASE)
# A browser ends a script block at `</script` plus whitespace, `/` or `>`, in any case.
EMBEDDED_JSON = re.compile(
    r'<script type="application/json" id="explainer-source">(.*?)</script[\s/>]',
    re.DOTALL | re.IGNORECASE,
)


def run_hook(payload, cwd):
    env = dict(os.environ, PLAN_EXPLAINER_NO_OPEN="1")
    return subprocess.run(
        [sys.executable, SCRIPT],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=30,
        check=False,
    )


class HookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.plans = os.path.join(self.tmp, "plans")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.plans)
        os.makedirs(self.repo)
        self.plan_path = os.path.join(self.plans, "eager-bubble.md")

    def exit_plan_mode(self, plan=None, plan_file_path=None):
        tool_input = {}
        if plan is not None:
            tool_input["plan"] = plan
        if plan_file_path is not None:
            tool_input["planFilePath"] = plan_file_path
        return run_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "ExitPlanMode",
                "permission_mode": "plan",
                "tool_input": tool_input,
            },
            self.repo,
        )


class ExplainerExtraction(unittest.TestCase):
    def test_stops_at_the_next_level_two_heading_and_keeps_subsections(self):
        self.assertEqual(
            render.extract_explainer(PLAN_WITH_EXPLAINER), EXPECTED_EXPLAINER
        )

    def test_a_plan_without_an_explainer_section_has_none(self):
        self.assertIsNone(render.extract_explainer(PLAN_WITHOUT_EXPLAINER))

    def test_a_level_two_heading_inside_a_code_fence_does_not_end_the_section(self):
        plan = (
            "# P\n\n## Explainer\n\n### Example\n```markdown\n## Not a heading\n```\n"
            "After the fence.\n\n## Verification\nRun it.\n"
        )
        self.assertEqual(
            render.extract_explainer(plan),
            "### Example\n```markdown\n## Not a heading\n```\nAfter the fence.",
        )

    def test_an_explainer_heading_quoted_in_an_earlier_fence_is_not_the_section(self):
        plan = (
            "# P\n\n## Context\n```markdown\n## Explainer\nquoted\n```\n\n"
            "## Explainer\nreal\n"
        )
        self.assertEqual(render.extract_explainer(plan), "real")

    def test_crlf_line_endings_still_find_the_section(self):
        plan = "# P\r\n\r\n## Explainer\r\nbody\r\n\r\n## Verification\r\nRun it.\r\n"
        self.assertEqual(render.extract_explainer(plan), "body")

    def test_any_heading_that_starts_with_explainer_opens_the_section(self):
        plan = "# P\n\n## Explainer (draft)\nbody\n"
        self.assertEqual(render.extract_explainer(plan), "body")

    def test_a_trailing_level_one_heading_ends_the_section(self):
        plan = "# P\n\n## Explainer\nbody\n\n# Appendix\nnot explainer\n"
        self.assertEqual(render.extract_explainer(plan), "body")


class PageTitle(unittest.TestCase):
    """Headings from real plans. The cut-at-the-first-colon rule named 13 of 106 "Plan"."""

    def test_titles_name_the_change_not_the_label_in_front_of_it(self):
        for heading, expected in TITLE_CASES.items():
            with self.subTest(heading=heading):
                self.assertEqual(render.page_title(heading), expected)


class NamedExplainer(HookCase):
    """A heading-derived title can only trim: "ui-ux #183: the crash-reporting switch is
    hard to engage" became "the crash-reporting switch is hard to engage"."""

    def page_title_for(self, plan):
        self.exit_plan_mode(plan, self.plan_path)
        with open(os.path.join(self.plans, "eager-bubble.artifact.html")) as fh:
            return re.search(r"<title>(.*?)</title>", fh.read()).group(1)

    def test_a_name_on_the_explainer_heading_titles_the_page(self):
        plan = "# ui-ux #183: the switch is hard to engage\n\n## Explainer: Crash Toggle Row\nbody\n"
        self.assertEqual(self.page_title_for(plan), "Crash Toggle Row")

    def test_a_bare_explainer_heading_falls_back_to_the_plan_heading(self):
        plan = "# Plan: Fix the login timeout\n\n## Explainer\nbody\n"
        self.assertEqual(self.page_title_for(plan), "Fix the login timeout")

    def test_the_name_is_escaped_like_any_other_title(self):
        plan = "# P\n\n## Explainer: Tags & <b>\nbody\n"
        self.assertEqual(self.page_title_for(plan), "Tags &amp; &lt;b&gt;")


class Outputs(HookCase):
    def test_a_plan_without_an_explainer_writes_nothing(self):
        result = self.exit_plan_mode(PLAN_WITHOUT_EXPLAINER, self.plan_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.listdir(self.plans), [])

    def test_dropping_the_explainer_on_a_re_plan_removes_the_stale_pages(self):
        self.exit_plan_mode(PLAN_WITH_EXPLAINER, self.plan_path)
        result = self.exit_plan_mode(PLAN_WITHOUT_EXPLAINER, self.plan_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.listdir(self.plans), [])

    def test_outputs_land_beside_the_plan_file_never_in_the_working_directory(self):
        result = self.exit_plan_mode(PLAN_WITH_EXPLAINER, self.plan_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            sorted(os.listdir(self.plans)),
            ["eager-bubble.artifact.html", "eager-bubble.explainer.html"],
        )
        self.assertEqual(os.listdir(self.repo), [])

    def test_reads_the_plan_file_when_tool_input_carries_only_its_path(self):
        with open(self.plan_path, "w") as fh:
            fh.write(PLAN_WITH_EXPLAINER)
        result = self.exit_plan_mode(plan_file_path=self.plan_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("eager-bubble.explainer.html", os.listdir(self.plans))

    def test_local_page_declares_utf8_and_the_artifact_page_is_a_bare_fragment(self):
        self.exit_plan_mode(PLAN_WITH_EXPLAINER, self.plan_path)
        with open(os.path.join(self.plans, "eager-bubble.explainer.html")) as fh:
            local = fh.read()
        with open(os.path.join(self.plans, "eager-bubble.artifact.html")) as fh:
            fragment = fh.read()
        self.assertTrue(local.lower().startswith("<!doctype html>"))
        self.assertIn('<meta charset="utf-8">', local)
        self.assertIsNone(DOCUMENT_TAG.search(fragment))


class Embedding(HookCase):
    def test_markdown_survives_embedding_unchanged_even_when_it_quotes_html(self):
        plan = f"# Hostile\n\n## Explainer\n\n{HOSTILE}\n"
        self.exit_plan_mode(plan, self.plan_path)
        with open(os.path.join(self.plans, "eager-bubble.artifact.html")) as fh:
            page = fh.read()
        blobs = EMBEDDED_JSON.findall(page)
        self.assertEqual(
            len(blobs), 1, "the quoted </script> broke out of the data block"
        )
        self.assertEqual(json.loads(blobs[0]), HOSTILE)


class NeverBlocks(HookCase):
    def test_malformed_input_does_not_block_exit_plan_mode(self):
        result = run_hook("not json", self.repo)
        self.assertNotEqual(result.returncode, 2)

    def test_a_missing_plan_file_does_not_block_exit_plan_mode(self):
        result = self.exit_plan_mode(plan_file_path=os.path.join(self.plans, "gone.md"))
        self.assertNotEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
