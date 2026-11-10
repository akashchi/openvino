# Copyright (C) 2018-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Remediate a transient merge-queue pipeline failure.

Single custom safe-output job for the CI Doctor MQ workflow
(.github/workflows/shared/agentic-workflows/remediate-transient-failure.md). The
agent calls it whenever the failure is transient (Infrastructure / Flaky Test /
Network / External Service).

This job resolves the PR's merge-queue status live (``common.merge_queue_status``)
and picks the remedy itself:
  - PR still ``in_queue``   -> re-run only the failed jobs (a re-run keeps it moving)
                               and comment on the PR. No marker is left: the re-run
                               is the remedy.
  - PR ``not_in_queue``     -> the merge group is gone, so nothing can be re-run. Leave
                               a PR comment with the hidden transient marker
                               (``transient_marker.py``) and dispatch
                               ``ci-doctor-mq-readd.yml``, which decides whether the
                               PR may be re-added to the merge queue.
  - PR ``merged``/``unknown`` or no PR -> no-op.

This job never re-adds a PR itself and holds no merge-queue token. It only uses the
default ``GITHUB_TOKEN`` (``actions: write`` to re-run and dispatch,
``pull-requests: write`` to comment).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from common import (
    github_client,
    handle_numeric_id,
    merge_queue_status,
    pr_number_from_merge_queue_branch,
    read_agent_item,
    require_env,
    resolve_repository,
)
from transient_marker import TRANSIENT_MARKER, bot_markers, build_marker, sanitize_reason

if TYPE_CHECKING:
    from github import Github
    from github.PullRequest import PullRequest
    from github.Repository import Repository
    from github.WorkflowRun import WorkflowRun

READD_WORKFLOW_FILE = "ci-doctor-mq-readd.yml"


def _rerun_comment(run: "WorkflowRun", reason: str) -> str:
    """Comment body announcing that the PR's failed jobs were re-run."""
    return (
        "### CI Doctor — Merge Queue remediation\n\n"
        "This PR's merge-queue pipeline failed transiently, so CI Doctor **re-ran its failed jobs** "
        "(the PR is still in the merge queue).\n\n"
        f"- **Failed run**: {run.html_url}\n"
        f"- **Reason**: {reason or 'transient failure'}\n"
    )


def _transient_comment(run: "WorkflowRun", reason: str) -> str:
    """Comment body stating that the failure is transient, led by the hidden marker."""
    reason = sanitize_reason(reason)
    marker = build_marker(TRANSIENT_MARKER, run_url=run.html_url, reason=reason)
    return (
        f"{marker}\n\n"
        "### CI Doctor — Merge Queue: transient failure\n\n"
        "CI Doctor investigated the failed merge-queue pipeline and concluded that its error is "
        "**transient / sporadic**, not caused by this pull request.\n\n"
        f"- **Investigated run**: {run.html_url}\n"
        f"- **Reason**: `{reason}`\n\n"
        "The failed jobs could not be re-run because the pull request had already left the merge queue. "
        f"If no other pipeline failed, the `{READD_WORKFLOW_FILE}` workflow re-adds the pull request "
        "to the merge queue (once).\n"
    )


def resolve_pr_number(run: "WorkflowRun") -> str:
    """Best-effort PR number behind a merge-queue run, or '' when none applies."""
    number = pr_number_from_merge_queue_branch(run.head_branch or "")
    if number:
        return number
    try:
        pulls = run.pull_requests or []
    except Exception:
        pulls = []
    return str(pulls[0].number) if pulls else ""


def rerun_failed_jobs(run: "WorkflowRun", run_id: str, repository: str, pull: "PullRequest", reason: str) -> None:
    """Re-run only the failed jobs of ``run`` (loop-guarded) and comment on the PR."""
    attempt = run.run_attempt or 1
    if attempt > 1:
        print(f"Run {run_id} already has {attempt} attempts; not re-running to avoid loops.")
        return
    if not run.rerun_failed_jobs():
        raise SystemExit(f"GitHub API rejected the re-run request for {repository} run {run_id}.")
    print(f"Successfully requested re-run of failed jobs for {repository} run {run_id}.")
    _set_github_env("RERUN_FAILED_JOBS", "true")
    pull.create_issue_comment(_rerun_comment(run, reason))
    print(f"Recorded re-run comment on PR #{pull.number}.")


def _set_github_env(key: str, value: str) -> None:
    """Append ``key=value`` to ``$GITHUB_ENV`` so later workflow steps can react."""
    github_env = os.environ.get("GITHUB_ENV")
    if not github_env:
        return
    with open(github_env, "a", encoding="utf-8") as handle:
        handle.write(f"{key}={value}\n")


def _marker_skip_reason(run: "WorkflowRun", pull: "PullRequest") -> str | None:
    """Return why a transient marker is pointless for this run/PR, or None to proceed.

    These mirror the conditions the re-add workflow enforces, so a marker is only
    left when that workflow could act on it.
    """
    if run.event != "merge_group":
        return f"Run {run.id} is a '{run.event}' run, not a merge-queue run; not leaving a transient marker."
    if run.conclusion != "failure":
        return f"Run {run.id} concluded '{run.conclusion}', not 'failure'; not leaving a transient marker."
    attempt = run.run_attempt or 1
    if attempt > 1:
        return f"Run {run.id} already has {attempt} attempts; not leaving a transient marker."
    if pull.merged:
        return f"PR #{pull.number} is already merged; not leaving a transient marker."
    if pull.state != "open":
        return f"PR #{pull.number} is not open (state={pull.state}); not leaving a transient marker."
    if pull.draft:
        return f"PR #{pull.number} is a draft; not leaving a transient marker."
    return None


def dispatch_readd(repo: "Repository", pr_number: int) -> None:
    """Start the re-add workflow for ``pr_number`` (a dequeue that already happened cannot trigger it)."""
    workflow = repo.get_workflow(READD_WORKFLOW_FILE)
    workflow.create_dispatch(ref=repo.default_branch, inputs={"pr_number": str(pr_number)}, throw=True)
    print(f"Dispatched {READD_WORKFLOW_FILE} for PR #{pr_number}.")


def mark_transient(repo: "Repository", run: "WorkflowRun", pull: "PullRequest", reason: str) -> None:
    """Comment that ``run`` failed transiently (hidden marker) and hand the PR to the re-add workflow.

    Idempotent: an existing marker for the same run is not duplicated, but the
    dispatch is still sent so a re-run of this job can complete a failed dispatch.
    The re-add workflow guards against acting twice.
    """
    skip_reason = _marker_skip_reason(run, pull)
    if skip_reason:
        print(skip_reason)
        return

    known_runs = {marker.get("run_url") for marker in bot_markers(pull.get_issue_comments(), TRANSIENT_MARKER)}
    if run.html_url in known_runs:
        print(f"PR #{pull.number} already has a transient marker for {run.html_url}; not posting another.")
    else:
        pull.create_issue_comment(_transient_comment(run, reason))
        print(f"Recorded transient-failure comment with marker on PR #{pull.number}.")
        _set_github_env("TRANSIENT_MARKER_POSTED", "true")
    dispatch_readd(repo, pull.number)


def remediate(gh: "Github", repo: "Repository", run: "WorkflowRun", run_id: str, repository: str, reason: str) -> None:
    """Pick and perform the remedy for a transient failure of ``run``."""
    pr_number = resolve_pr_number(run)
    if not pr_number:
        print("No pull request associated with this run; cannot remediate.")
        return

    pull = repo.get_pull(int(pr_number))
    status = merge_queue_status(gh, repo, pull)
    print(f"Live merge-queue status for PR #{pr_number}: {status}")

    if status == "in_queue":
        print(f"PR #{pr_number} is still in the merge queue; re-running failed jobs.")
        rerun_failed_jobs(run, run_id, repository, pull, reason)
    elif status == "not_in_queue":
        print(f"PR #{pr_number} already left the merge queue, so nothing can be re-run; recording the transient failure.")
        mark_transient(repo, run, pull, reason)
    elif status == "merged":
        print(f"PR #{pr_number} is already merged; no remediation needed.")
    else:
        print(f"PR #{pr_number} merge-queue status is '{status}'; cannot safely remediate. Skipping.")


def main() -> None:
    item = read_agent_item("remediate_transient_failure")
    run_id = handle_numeric_id(item.get("run_id") or "", "run_id")
    repository = resolve_repository(item.get("repository") or "")
    reason = item.get("reason") or ""

    print(f"Remediating transient failure for {repository} run {run_id} (reason: {reason})")

    token = require_env("GH_TOKEN", "GITHUB_TOKEN is not configured; cannot remediate.")
    gh = github_client(token)
    repo = gh.get_repo(repository)
    run = repo.get_workflow_run(int(run_id))
    remediate(gh, repo, run, run_id, repository, reason)


if __name__ == "__main__":
    main()
