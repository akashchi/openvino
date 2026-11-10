# Copyright (C) 2018-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Decide whether a pull request may be re-added to the merge queue after a transient failure.

Used by .github/workflows/ci-doctor-mq-readd.yml, which runs when a pull request is
dequeued (or when CI Doctor MQ dispatches it). CI Doctor MQ never re-adds a pull
request itself: it only leaves a comment with a hidden marker (``transient_marker.py``)
when it concludes that a merge-queue failure was transient. This script re-checks, at
the time of the dequeue, that re-adding is still safe.

Sub-commands (the pull request is taken from ``$PR_NUMBER``):

``evaluate``
    Read-only. Re-adds are allowed only when ALL of these hold, otherwise the pull
    request is left alone (the reason is logged and written to the step summary):

    * the PR is open, not a draft, not merged and not in the merge queue;
    * the latest CI Doctor transient marker (authored by the Actions bot) points at a
      run of this repository, and the PR was not already re-added once by CI Doctor;
    * that investigated run is a ``merge_group`` run of this PR for its current base branch
      (a PR retargeted since is not re-added) that is still a completed failure and was
      never re-run;
    * the run started after the PR was last added to the merge queue (the marker belongs
      to the failure that caused the latest dequeue), and nothing was pushed to the PR
      since: the newest of its queue-entry, pushed-commit and force-push timeline items
      is that queue entry. Commit dates are not consulted, because the pusher sets them;
    * no other ``merge_group`` pipeline of the same merge-group commit failed, because
      those failures were not investigated and might not be transient.

    Writes the ``readd`` step output (and ``pr_number``, ``head_sha``, ``run_url`` when
    it is ``true``).

``record``
    Run after the workflow enqueued the PR. Comments on the PR (with a hidden marker)
    so CI Doctor re-adds a pull request at most once.

Only the default ``GITHUB_TOKEN`` is used here. The enqueue itself needs the
merge-queue token and is done by a separate workflow step, so that token never reaches
this script or the packages it imports.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from typing import TYPE_CHECKING, Iterable, NamedTuple

from common import (
    base_branch_from_merge_queue_branch,
    github_client,
    handle_numeric_id,
    merge_queue_status,
    pr_number_from_merge_queue_branch,
    require_env,
    resolve_repository,
)
from transient_marker import READDED_MARKER, TRANSIENT_MARKER, bot_markers, build_marker, run_id_from_url

if TYPE_CHECKING:
    from github import Github
    from github.PullRequest import PullRequest
    from github.Repository import Repository
    from github.WorkflowRun import WorkflowRun

# A run that ended like this failed; cancelled/skipped/successful/in-progress runs do not count.
FAILED_CONCLUSIONS = frozenset({"failure", "timed_out", "startup_failure"})
MAX_LISTED_RUNS = 5

QUEUE_ENTRY = "AddedToMergeQueueEvent"
# What a timeline item that comes after the queue entry means for the PR.
_CHANGES = {
    "PullRequestCommit": "commits were pushed to it",
    "HeadRefForcePushedEvent": "its branch was force-pushed",
}

# When the PR last entered the merge queue, and which of its queue-entry, pushed-commit and force-push
# timeline items is the newest. GitHub places a pushed commit in the timeline when it is pushed, so a
# commit pushed after the queue entry never sorts before it, whatever its (pusher-controlled) commit date.
_HISTORY_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      queued: timelineItems(last: 1, itemTypes: [ADDED_TO_MERGE_QUEUE_EVENT]) {
        nodes { ... on AddedToMergeQueueEvent { createdAt } }
      }
      latest: timelineItems(last: 1, itemTypes: [ADDED_TO_MERGE_QUEUE_EVENT, PULL_REQUEST_COMMIT, HEAD_REF_FORCE_PUSHED_EVENT]) {
        nodes { __typename }
      }
    }
  }
}
"""


class Skip(Exception):
    """A condition for re-adding the pull request is not met (an outcome, not an error)."""


class PullRequestHistory(NamedTuple):
    last_queued: datetime
    latest_item: str  # GraphQL type of the newest queue-entry, pushed-commit or force-push timeline item


def check_pull_request_open(pull: "PullRequest") -> None:
    if pull.merged:
        raise Skip(f"PR #{pull.number} is already merged.")
    if pull.state != "open":
        raise Skip(f"PR #{pull.number} is not open (state={pull.state}).")
    if pull.draft:
        raise Skip(f"PR #{pull.number} is a draft.")


def latest_marker_run_id(comments: Iterable, repository: str) -> str:
    """Return the run id of the latest transient marker left by the Actions bot."""
    markers = bot_markers(comments, TRANSIENT_MARKER)
    if not markers:
        raise Skip("the PR has no CI Doctor transient-failure marker.")
    run_url = markers[-1].get("run_url", "")
    run_id = run_id_from_url(run_url, repository)
    if not run_id:
        raise Skip(f"the latest transient-failure marker does not reference a run of {repository}: '{run_url}'.")
    return run_id


def check_not_readded(comments: Iterable) -> None:
    if bot_markers(comments, READDED_MARKER):
        raise Skip("CI Doctor already re-added this PR to the merge queue once; not re-adding it again.")


def check_investigated_run(run: "WorkflowRun", pull: "PullRequest") -> None:
    """The investigated pipeline must be this PR's merge-queue run, still failed and never re-run."""
    if run.event != "merge_group":
        raise Skip(f"run {run.html_url} is a '{run.event}' run, not a merge-queue run.")
    if pr_number_from_merge_queue_branch(run.head_branch or "") != str(pull.number):
        raise Skip(f"run {run.html_url} (branch '{run.head_branch}') does not belong to PR #{pull.number}.")
    # A PR retargeted after the failure would otherwise be enqueued into another branch's queue.
    if base_branch_from_merge_queue_branch(run.head_branch or "") != pull.base.ref:
        raise Skip(
            f"run {run.html_url} (branch '{run.head_branch}') is not a merge-queue run for the current base branch '{pull.base.ref}' of PR #{pull.number}."
        )
    if run.status != "completed" or run.conclusion != "failure":
        raise Skip(f"run {run.html_url} is {run.status}/{run.conclusion}, no longer a completed failure.")
    attempt = run.run_attempt or 1
    if attempt != 1:
        raise Skip(f"run {run.html_url} was re-run (attempt {attempt}).")


def _latest_created_at(timeline: dict | None) -> datetime | None:
    nodes = (timeline or {}).get("nodes") or []
    created = [node["createdAt"] for node in nodes if node and node.get("createdAt")]
    return datetime.fromisoformat(created[-1].replace("Z", "+00:00")) if created else None


def _latest_type(timeline: dict | None) -> str | None:
    nodes = (timeline or {}).get("nodes") or []
    return (nodes[-1] or {}).get("__typename") if nodes else None


def pull_request_history(gh: "Github", repository: str, number: int) -> PullRequestHistory:
    owner, _, name = repository.partition("/")
    _, data = gh.requester.requestJsonAndCheck(
        "POST",
        "/graphql",
        input={"query": _HISTORY_QUERY, "variables": {"owner": owner, "repo": name, "number": number}},
    )
    if data.get("errors"):
        raise SystemExit(f"GraphQL history lookup for PR #{number} failed: {data['errors']}")
    pull = ((data.get("data") or {}).get("repository") or {}).get("pullRequest") or {}
    queued = _latest_created_at(pull.get("queued"))
    if queued is None:
        raise SystemExit(f"PR #{number} has no ADDED_TO_MERGE_QUEUE_EVENT in its timeline; cannot tell when it was queued.")
    latest = _latest_type(pull.get("latest"))
    if latest is None:
        raise SystemExit(f"PR #{number} has no queue-entry, commit or force-push item in its timeline; cannot tell whether it changed.")
    return PullRequestHistory(last_queued=queued, latest_item=latest)


def check_run_matches_history(pull: "PullRequest", run: "WorkflowRun", history: PullRequestHistory) -> None:
    """The failure must come from the queue entry that was just dequeued, and the PR must not have changed since."""
    # Each queue entry creates a new merge group, so a run created before the latest entry belongs to an earlier one.
    if run.created_at < history.last_queued:
        raise Skip(
            f"run {run.html_url} was created at {run.created_at}, before PR #{pull.number} was last "
            f"added to the merge queue ({history.last_queued}); the marker is stale."
        )
    if history.latest_item != QUEUE_ENTRY:
        change = _CHANGES.get(history.latest_item, f"its latest timeline item is {history.latest_item}")
        raise Skip(f"PR #{pull.number} changed after it was last added to the merge queue ({change}); run {run.html_url} no longer describes it.")


def check_only_failed_pipeline(repo: "Repository", run: "WorkflowRun") -> None:
    """No other merge-group pipeline may have failed: those failures were not investigated."""
    others = [
        other for other in repo.get_workflow_runs(event="merge_group", head_sha=run.head_sha) if other.id != run.id and other.conclusion in FAILED_CONCLUSIONS
    ]
    if others:
        listed = ", ".join(f"{other.name} ({other.html_url})" for other in others[:MAX_LISTED_RUNS])
        raise Skip(f"{len(others)} other merge-queue pipeline(s) failed as well: {listed}; those failures were not investigated and might not be transient.")


def check_not_queued(gh: "Github", repo: "Repository", pull: "PullRequest") -> None:
    status = merge_queue_status(gh, repo, pull)
    if status != "not_in_queue":
        raise Skip(f"PR #{pull.number} is not out of the merge queue (status: {status}).")


def evaluate(gh: "Github", repo: "Repository", repository: str, pull: "PullRequest") -> "WorkflowRun":
    """Return the investigated run when the PR may be re-added, else raise :class:`Skip`."""
    check_pull_request_open(pull)
    comments = list(pull.get_issue_comments())
    run_id = latest_marker_run_id(comments, repository)
    check_not_readded(comments)
    run = repo.get_workflow_run(int(run_id))
    check_investigated_run(run, pull)
    check_run_matches_history(pull, run, pull_request_history(gh, repository, pull.number))
    check_only_failed_pipeline(repo, run)
    # Last, so the queue state is as fresh as possible when the workflow enqueues the PR.
    check_not_queued(gh, repo, pull)
    return run


def _readded_comment(run_url: str) -> str:
    """Comment body stating that CI Doctor re-added the PR, led by the hidden marker."""
    marker = build_marker(READDED_MARKER, run_url=run_url)
    return (
        f"{marker}\n\n"
        "### CI Doctor — Merge Queue: re-added\n\n"
        "This pull request left the merge queue because of a transient failure that CI Doctor investigated "
        f"({run_url}). That pipeline was the only one that failed and it was not re-run, "
        "so CI Doctor **re-added the pull request to the merge queue**.\n\n"
        "CI Doctor re-adds a pull request at most once.\n"
    )


def _append(env_name: str, text: str) -> None:
    """Append ``text`` to the file named by ``$<env_name>`` (``GITHUB_OUTPUT``, ``GITHUB_STEP_SUMMARY``), if set."""
    path = os.environ.get(env_name)
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)


def run_evaluate(gh: "Github", repo: "Repository", repository: str, pull: "PullRequest") -> None:
    try:
        run = evaluate(gh, repo, repository, pull)
    except Skip as skip:
        print(f"Not re-adding PR #{pull.number}: {skip}")
        _append("GITHUB_STEP_SUMMARY", f"### CI Doctor MQ re-add\n\nPR #{pull.number} was not re-added: {skip}\n")
        _append("GITHUB_OUTPUT", "readd=false\n")
        return

    print(f"PR #{pull.number} may be re-added: run {run.html_url} is the only failed pipeline and was not re-run.")
    _append("GITHUB_STEP_SUMMARY", f"### CI Doctor MQ re-add\n\nRe-adding PR #{pull.number} (investigated run: {run.html_url}).\n")
    _append(
        "GITHUB_OUTPUT",
        f"readd=true\npr_number={pull.number}\nhead_sha={pull.head.sha}\nrun_url={run.html_url}\n",
    )


def run_record(repository: str, pull: "PullRequest") -> None:
    run_url = require_env("RUN_URL", "RUN_URL is not set; cannot record the re-add.")
    if not run_id_from_url(run_url, repository):
        raise SystemExit(f"RUN_URL is not a run of {repository}: '{run_url}'")
    pull.create_issue_comment(_readded_comment(run_url))
    print(f"Recorded the re-add on PR #{pull.number}.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("evaluate", "record"))
    command = parser.parse_args(argv).command

    pr_number = handle_numeric_id(require_env("PR_NUMBER", "PR_NUMBER is not set."), "PR_NUMBER")
    repository = resolve_repository("")
    gh = github_client(require_env("GH_TOKEN", "GITHUB_TOKEN is not configured."))
    repo = gh.get_repo(repository)
    pull = repo.get_pull(int(pr_number))

    if command == "evaluate":
        run_evaluate(gh, repo, repository, pull)
    else:
        run_record(repository, pull)


if __name__ == "__main__":
    main()
