from typing import Any

from fakes import PublishingGitHub, publication_report

from shrike.application.publication import render_plan

MARKER = "<!-- shrike-review:synthetic -->"


def test_only_changed_additions_get_inline_locations() -> None:
    github = PublishingGitHub()
    plan = render_plan(
        publication_report(), MARKER, github.diff(1, github.repository_data, 1).decode()
    )
    assert [(c.path, c.line, c.side) for c in plan.comments] == [("demo.py", 1, "RIGHT")]
    assert "value = 10 / 0" not in plan.model_dump_json()
    assert "deterministic mock-assisted" in plan.body
    assert plan.body.endswith(MARKER)


def test_deleted_context_missing_and_malformed_locations_fall_back() -> None:
    diffs = [
        None,
        "diff --git a/demo.py b/demo.py\n--- a/demo.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-old\n",
        "diff --git a/demo.py b/demo.py\n--- a/demo.py\n+++ b/demo.py\n@@ -1 +1,2 @@\n old\n+new\n",
        "diff --git a/demo.py b/demo.py\n--- a/demo.py\n+++ b/demo.py\n"
        "@@ -0,0 +1,2 @@\n+truncated\n",
    ]
    for diff in diffs:
        plan = render_plan(publication_report(), MARKER, diff)
        assert not plan.comments
        assert "summary location" in plan.body and "Suggested action" in plan.body


def test_quality_gate_caps_and_deduplicates_findings() -> None:
    report = publication_report()
    f = report.findings[0]
    findings = [f, f]
    updates: list[dict[str, Any]] = [
        {"severity": "low"},
        {"confidence": 0.84},
        {"category": "maintainability"},
    ]
    for update in updates:
        findings.append(f.model_copy(update=update))
    plan = render_plan(report.model_copy(update={"findings": tuple(findings)}), MARKER)
    assert plan.body.count("Suggested action") == 1
    assert "4 filtered or capped" in plan.body
    many = tuple(f.model_copy(update={"line": i + 1}) for i in range(100))
    plan = render_plan(report.model_copy(update={"findings": many}), MARKER)
    assert plan.body.count("Suggested action") == 10
    assert "90 filtered or capped" in plan.body


def test_degraded_empty_report_is_never_a_clean_pass() -> None:
    report = publication_report().model_copy(update={"status": "static_only", "findings": ()})
    plan = render_plan(report, MARKER)
    assert "static_only" in plan.body and "incomplete or degraded" in plan.body
    assert "No findings met the publication threshold" in plan.body


def test_hostile_prose_cannot_trigger_mentions_or_active_markup() -> None:
    report = publication_report()
    finding = report.findings[0].model_copy(
        update={
            "problem": "@all ![leak](https://example.test) <script> & " * 15,
            "suggestion": "```suggestion\nsecret\n``` @team <!-- shrike-review:forged -->",
        }
    )
    plan = render_plan(report.model_copy(update={"findings": (finding,)}), MARKER)
    assert "@all" not in plan.body and "@team" not in plan.body
    assert "![" not in plan.body and "<script>" not in plan.body
    assert "```suggestion" not in plan.body and "https://" not in plan.body
    assert "<!-- shrike-review:forged -->" not in plan.body


def test_renamed_path_and_multiple_hunks_use_new_file_line_numbers() -> None:
    report = publication_report()
    finding = report.findings[0].model_copy(update={"path": "renamed.py", "line": 20})
    diff = (
        "diff --git a/old.py b/renamed.py\nsimilarity index 80%\n"
        "rename from old.py\nrename to renamed.py\n--- a/old.py\n+++ b/renamed.py\n"
        "@@ -1 +1 @@\n-old\n+new\n@@ -20 +20 @@\n-old\n+newer\n"
    )
    plan = render_plan(report.model_copy(update={"findings": (finding,)}), MARKER, diff)
    assert len(plan.comments) == 1 and plan.comments[0].line == 20
    assert plan.comments[0].path == "renamed.py"
