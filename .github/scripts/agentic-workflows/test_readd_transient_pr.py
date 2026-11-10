# Copyright (C) 2018-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import contextlib
import io
import os
import re
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock
from unittest.mock import Mock

import readd_transient_pr as job
from transient_marker import (
    BOT_LOGIN,
    READDED_MARKER,
    TRANSIENT_MARKER,
    build_marker,
    parse_markers,
)

REPOSITORY = "openvinotoolkit/openvino"
RUN_URL = f"https://github.com/{REPOSITORY}/actions/runs/555"
HEAD_SHA = "a" * 40
MERGE_GROUP_SHA = "b" * 40

ADDED_TO_QUEUE = "2025-01-01T11:00:00Z"
RUN_CREATED = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)


def bot_comment(body, login=BOT_LOGIN):
    return SimpleNamespace(body=body, user=SimpleNamespace(login=login))


def transient_comment(run_url=RUN_URL, login=BOT_LOGIN):
    return bot_comment(build_marker(TRANSIENT_MARKER, run_url=run_url, reason="runner lost"), login)


def make_run(**overrides):
    values = {
        "id": 555,
        "name": "Linux (Ubuntu 22.04, Python 3.11)",
        "html_url": RUN_URL,
        "event": "merge_group",
        "status": "completed",
        "conclusion": "failure",
        "run_attempt": 1,
        "head_branch": "gh-readonly-queue/master/pr-42-0123abc",
        "head_sha": MERGE_GROUP_SHA,
        "created_at": RUN_CREATED,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_pull(comments, **overrides):
    values = {
        "number": 42,
        "merged": False,
        "state": "open",
        "draft": False,
        "head": SimpleNamespace(sha=HEAD_SHA),
        "base": SimpleNamespace(ref="master"),
    }
    values.update(overrides)
    pull = SimpleNamespace(**values)
    pull.get_issue_comments = Mock(return_value=list(comments))
    pull.create_issue_comment = Mock()
    return pull


def pull_request_history(queued=(ADDED_TO_QUEUE,), latest=job.QUEUE_ENTRY):
    """A GraphQL response with the PR's latest ADDED_TO_MERGE_QUEUE item and the type of its newest
    queue-entry, pushed-commit or force-push timeline item (``None``: the timeline returned nothing)."""
    pull = {
        "queued": {"nodes": [{"createdAt": value} for value in queued]},
        "latest": {"nodes": [{"__typename": latest}] if latest else []},
    }
    return {}, {"data": {"repository": {"pullRequest": pull}}}


class EvaluateTestCase(unittest.TestCase):
    """A PR that may be re-added; tests break one condition at a time."""

    def setUp(self):
        self.run = make_run()
        self.pull = make_pull([transient_comment()])
        self.repo = Mock()
        self.repo.get_workflow_run.return_value = self.run
        self.repo.get_workflow_runs.return_value = [self.run]
        self.gh = Mock()
        self.gh.requester.requestJsonAndCheck.return_value = pull_request_history()
        patcher = mock.patch.object(job, "merge_queue_status", return_value="not_in_queue")
        self.queue_status = patcher.start()
        self.addCleanup(patcher.stop)

    def evaluate(self):
        return job.evaluate(self.gh, self.repo, REPOSITORY, self.pull)

    def assert_skipped(self, fragment):
        with self.assertRaisesRegex(job.Skip, fragment):
            self.evaluate()


class EvaluateAllowedTest(EvaluateTestCase):
    def test_returns_the_investigated_run(self):
        self.assertIs(self.evaluate(), self.run)
        self.repo.get_workflow_run.assert_called_once_with(555)

    def test_other_pipelines_that_did_not_fail_are_ignored(self):
        self.repo.get_workflow_runs.return_value = [
            self.run,
            make_run(id=1, conclusion="success"),
            make_run(id=2, conclusion="cancelled"),
            make_run(id=3, conclusion="skipped"),
            make_run(id=4, status="in_progress", conclusion=None),
        ]
        self.assertIs(self.evaluate(), self.run)
        self.repo.get_workflow_runs.assert_called_once_with(event="merge_group", head_sha=MERGE_GROUP_SHA)

    def test_run_created_in_the_same_second_as_the_queue_entry_is_current(self):
        self.gh.requester.requestJsonAndCheck.return_value = pull_request_history(queued=["2025-01-01T12:00:00Z"])
        self.assertIs(self.evaluate(), self.run)

    def test_latest_marker_wins(self):
        run_1 = transient_comment("https://github.com/openvinotoolkit/openvino/actions/runs/1")
        run_555 = transient_comment()
        for comments, expected_run_id in (([run_1, run_555], 555), ([run_555, run_1], 1)):
            with self.subTest(expected_run_id):
                self.repo.get_workflow_run.reset_mock()
                self.pull.get_issue_comments.return_value = comments
                self.evaluate()
                self.repo.get_workflow_run.assert_called_once_with(expected_run_id)


class EvaluatePullRequestTest(EvaluateTestCase):
    def test_merged_closed_or_draft_pull_requests_are_skipped(self):
        for overrides, fragment in (
            ({"merged": True, "state": "closed"}, "already merged"),
            ({"state": "closed"}, "not open"),
            ({"draft": True}, "draft"),
        ):
            with self.subTest(overrides):
                self.pull = make_pull([transient_comment()], **overrides)
                self.assert_skipped(fragment)

    def test_pull_request_that_is_queued_again_is_skipped(self):
        for status in ("in_queue", "merged", "unknown"):
            with self.subTest(status):
                self.queue_status.return_value = status
                self.assert_skipped(f"status: {status}")


class EvaluateMarkerTest(EvaluateTestCase):
    def test_missing_marker(self):
        self.pull.get_issue_comments.return_value = [bot_comment("just a comment")]
        self.assert_skipped("no CI Doctor transient-failure marker")

    def test_marker_from_another_author_is_ignored(self):
        self.pull.get_issue_comments.return_value = [transient_comment(login="some-contributor")]
        self.assert_skipped("no CI Doctor transient-failure marker")

    def test_marker_for_a_run_of_another_repository_is_rejected(self):
        self.pull.get_issue_comments.return_value = [transient_comment("https://github.com/other/repo/actions/runs/555")]
        self.assert_skipped("does not reference a run of")
        self.repo.get_workflow_run.assert_not_called()

    def test_pull_request_is_re_added_at_most_once(self):
        readded = bot_comment(build_marker(READDED_MARKER, run_url=RUN_URL))
        self.pull.get_issue_comments.return_value = [transient_comment(), readded, transient_comment()]
        self.assert_skipped("already re-added")
        self.repo.get_workflow_run.assert_not_called()

    def test_readded_marker_from_another_author_does_not_block(self):
        forged = bot_comment(build_marker(READDED_MARKER, run_url=RUN_URL), login="some-contributor")
        self.pull.get_issue_comments.return_value = [transient_comment(), forged]
        self.assertIs(self.evaluate(), self.run)


class EvaluateInvestigatedRunTest(EvaluateTestCase):
    def test_run_that_is_not_a_completed_failure_is_skipped(self):
        for overrides in (
            {"conclusion": "success"},
            {"conclusion": "cancelled"},
            {"status": "in_progress", "conclusion": None},
            {"status": "queued", "conclusion": None},
        ):
            with self.subTest(overrides):
                self.repo.get_workflow_run.return_value = make_run(**overrides)
                self.assert_skipped("no longer a completed failure")

    def test_run_that_was_re_run_is_skipped(self):
        self.repo.get_workflow_run.return_value = make_run(run_attempt=2)
        self.assert_skipped("was re-run")

    def test_run_without_an_attempt_number_counts_as_the_first_attempt(self):
        run = make_run(run_attempt=None)
        self.repo.get_workflow_run.return_value = run
        self.assertIs(self.evaluate(), run)

    def test_run_that_is_not_a_merge_queue_run_is_skipped(self):
        self.repo.get_workflow_run.return_value = make_run(event="pull_request")
        self.assert_skipped("not a merge-queue run")

    def test_run_of_another_pull_request_is_skipped(self):
        self.repo.get_workflow_run.return_value = make_run(head_branch="gh-readonly-queue/master/pr-43-0123abc")
        self.assert_skipped("does not belong to PR #42")

    def test_run_for_another_base_branch_is_skipped(self):
        self.pull = make_pull([transient_comment()], base=SimpleNamespace(ref="releases/2026/1"))
        self.assert_skipped("current base branch 'releases/2026/1' of PR #42")
        self.gh.requester.requestJsonAndCheck.assert_not_called()

    def test_base_branch_with_slashes_is_matched_in_full(self):
        run = make_run(head_branch="gh-readonly-queue/releases/2026/1/pr-42-0123abc")
        self.repo.get_workflow_run.return_value = run
        self.pull = make_pull([transient_comment()], base=SimpleNamespace(ref="releases/2026/1"))
        self.assertIs(self.evaluate(), run)
        # Only a prefix of the base branch must not match.
        self.pull = make_pull([transient_comment()], base=SimpleNamespace(ref="releases"))
        self.assert_skipped("current base branch 'releases'")

    def test_branch_that_is_not_a_merge_queue_branch_is_skipped(self):
        self.repo.get_workflow_run.return_value = make_run(head_branch="feature/pr-42-0123abc")
        self.assert_skipped("is not a merge-queue run for the current base branch")

    def test_full_ref_name_of_the_merge_queue_branch_is_accepted(self):
        run = make_run(head_branch="refs/heads/gh-readonly-queue/master/pr-42-0123abc")
        self.repo.get_workflow_run.return_value = run
        self.assertIs(self.evaluate(), run)


class EvaluateFreshnessTest(EvaluateTestCase):
    def test_run_from_an_earlier_queue_entry_is_stale(self):
        self.gh.requester.requestJsonAndCheck.return_value = pull_request_history(queued=["2025-01-01T12:30:00Z"])
        self.assert_skipped("marker is stale")

    def test_the_latest_queue_entry_is_used(self):
        self.gh.requester.requestJsonAndCheck.return_value = pull_request_history(queued=["2025-01-01T11:00:00Z", "2025-01-01T13:00:00Z"])
        self.assert_skipped("marker is stale")

    def test_changes_after_the_latest_queue_entry_are_skipped(self):
        for item_type, fragment in (
            ("PullRequestCommit", "commits were pushed to it"),
            ("HeadRefForcePushedEvent", "its branch was force-pushed"),
            ("SomethingNew", "latest timeline item is SomethingNew"),
        ):
            with self.subTest(item_type):
                self.gh.requester.requestJsonAndCheck.return_value = pull_request_history(latest=item_type)
                self.assert_skipped(fragment)

    def test_graphql_errors_are_an_error_not_a_skip(self):
        self.gh.requester.requestJsonAndCheck.return_value = ({}, {"errors": [{"message": "boom"}]})
        with self.assertRaisesRegex(SystemExit, "boom"):
            self.evaluate()

    def test_missing_queue_history_is_an_error_not_a_skip(self):
        self.gh.requester.requestJsonAndCheck.return_value = pull_request_history(queued=())
        with self.assertRaisesRegex(SystemExit, "no ADDED_TO_MERGE_QUEUE_EVENT"):
            self.evaluate()

    def test_missing_latest_item_is_an_error_not_a_skip(self):
        self.gh.requester.requestJsonAndCheck.return_value = pull_request_history(latest=None)
        with self.assertRaisesRegex(SystemExit, "cannot tell whether it changed"):
            self.evaluate()

    def test_query_targets_the_pull_request(self):
        self.evaluate()
        (method, path), kwargs = self.gh.requester.requestJsonAndCheck.call_args
        self.assertEqual((method, path), ("POST", "/graphql"))
        self.assertEqual(kwargs["input"]["variables"], {"owner": "openvinotoolkit", "repo": "openvino", "number": 42})
        query = kwargs["input"]["query"]
        # Each alias must ask for the newest item only (the checks compare against the end of the timeline),
        # and "latest" must include the queue entry itself, or every PR would look changed after it.
        item_types = {
            alias: set(re.findall(r"[A-Z_]+", types)) for alias, types in re.findall(r"(\w+): timelineItems\(last: 1, itemTypes: \[([^\]]*)\]\)", query)
        }
        self.assertEqual(
            item_types,
            {
                "queued": {"ADDED_TO_MERGE_QUEUE_EVENT"},
                "latest": {"ADDED_TO_MERGE_QUEUE_EVENT", "PULL_REQUEST_COMMIT", "HEAD_REF_FORCE_PUSHED_EVENT"},
            },
        )


class EvaluateOtherFailuresTest(EvaluateTestCase):
    def test_another_failed_pipeline_blocks_the_re_add(self):
        for conclusion in ("failure", "timed_out", "startup_failure"):
            with self.subTest(conclusion):
                other = make_run(id=9, name="Windows (VS 2022)", conclusion=conclusion, html_url=RUN_URL + "9")
                self.repo.get_workflow_runs.return_value = [self.run, other]
                self.assert_skipped("Windows \\(VS 2022\\)")

    def test_listing_of_other_failures_is_bounded(self):
        others = [make_run(id=100 + n, name=f"Pipeline {n}") for n in range(job.MAX_LISTED_RUNS + 3)]
        self.repo.get_workflow_runs.return_value = [self.run, *others]
        with self.assertRaises(job.Skip) as raised:
            self.evaluate()
        message = str(raised.exception)
        self.assertIn(f"{len(others)} other", message)
        self.assertIn(f"Pipeline {job.MAX_LISTED_RUNS - 1}", message)
        self.assertNotIn(f"Pipeline {job.MAX_LISTED_RUNS} ", message)


class EvaluateOrderTest(EvaluateTestCase):
    def test_cheap_checks_run_before_api_heavy_ones(self):
        self.pull.get_issue_comments.return_value = []
        self.assert_skipped("no CI Doctor transient-failure marker")
        self.repo.get_workflow_run.assert_not_called()
        self.gh.requester.requestJsonAndCheck.assert_not_called()
        self.queue_status.assert_not_called()

    def test_queue_state_is_checked_last(self):
        self.repo.get_workflow_runs.return_value = [self.run, make_run(id=9, conclusion="failure")]
        self.assert_skipped("failed as well")
        self.queue_status.assert_not_called()


class OutputFilesTestCase(unittest.TestCase):
    def setUp(self):
        self.files = {}
        patched = {}
        for name in ("GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY"):
            handle = tempfile.NamedTemporaryFile("w+", delete=False)
            handle.close()
            self.addCleanup(os.unlink, handle.name)
            self.files[name] = handle.name
            patched[name] = handle.name
        patcher = mock.patch.dict(os.environ, patched)
        patcher.start()
        self.addCleanup(patcher.stop)
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def read(self, name):
        with open(self.files[name], encoding="utf-8") as handle:
            return handle.read()


class RunEvaluateTest(OutputFilesTestCase):
    def test_allowed_pull_request_is_published_as_step_outputs(self):
        pull = make_pull([])
        with mock.patch.object(job, "evaluate", return_value=make_run()):
            job.run_evaluate(Mock(), Mock(), REPOSITORY, pull)
        self.assertEqual(
            self.read("GITHUB_OUTPUT").splitlines(),
            ["readd=true", "pr_number=42", f"head_sha={HEAD_SHA}", f"run_url={RUN_URL}"],
        )
        self.assertIn(RUN_URL, self.read("GITHUB_STEP_SUMMARY"))

    def test_skip_is_reported_but_not_an_error(self):
        with mock.patch.object(job, "evaluate", side_effect=job.Skip("the PR has no marker.")):
            job.run_evaluate(Mock(), Mock(), REPOSITORY, make_pull([]))
        self.assertEqual(self.read("GITHUB_OUTPUT"), "readd=false\n")
        self.assertIn("the PR has no marker.", self.read("GITHUB_STEP_SUMMARY"))

    def test_errors_propagate_and_publish_nothing(self):
        with mock.patch.object(job, "evaluate", side_effect=SystemExit("GraphQL failed")):
            with self.assertRaises(SystemExit):
                job.run_evaluate(Mock(), Mock(), REPOSITORY, make_pull([]))
        self.assertEqual(self.read("GITHUB_OUTPUT"), "")


class RunRecordTest(OutputFilesTestCase):
    def test_comments_with_the_readded_marker(self):
        pull = make_pull([])
        with mock.patch.dict(os.environ, {"RUN_URL": RUN_URL}):
            job.run_record(REPOSITORY, pull)
        pull.create_issue_comment.assert_called_once()
        body = pull.create_issue_comment.call_args.args[0]
        self.assertEqual(parse_markers(body, READDED_MARKER), [{"run_url": RUN_URL}])
        self.assertIn("re-added", body)

    def test_run_url_of_another_repository_is_rejected(self):
        pull = make_pull([])
        with mock.patch.dict(os.environ, {"RUN_URL": "https://github.com/other/repo/actions/runs/1"}):
            with self.assertRaises(SystemExit):
                job.run_record(REPOSITORY, pull)
        pull.create_issue_comment.assert_not_called()

    def test_missing_run_url_is_an_error(self):
        pull = make_pull([])
        with mock.patch.dict(os.environ):
            os.environ.pop("RUN_URL", None)
            with self.assertRaises(SystemExit):
                job.run_record(REPOSITORY, pull)


class MainTest(OutputFilesTestCase):
    def setUp(self):
        super().setUp()
        self.pull = make_pull([])
        self.repo = Mock()
        self.repo.get_pull.return_value = self.pull
        gh = Mock()
        gh.get_repo.return_value = self.repo
        patcher = mock.patch.object(job, "github_client", return_value=gh)
        self.github_client = patcher.start()
        self.addCleanup(patcher.stop)
        env = mock.patch.dict(
            os.environ,
            {"PR_NUMBER": "42", "GH_TOKEN": "token", "GITHUB_REPOSITORY": REPOSITORY, "RUN_URL": RUN_URL},
        )
        env.start()
        self.addCleanup(env.stop)

    def test_evaluate_command(self):
        with mock.patch.object(job, "run_evaluate") as run_evaluate:
            job.main(["evaluate"])
        self.github_client.assert_called_once_with("token")
        self.repo.get_pull.assert_called_once_with(42)
        run_evaluate.assert_called_once()
        self.assertIs(run_evaluate.call_args.args[3], self.pull)

    def test_record_command(self):
        job.main(["record"])
        self.pull.create_issue_comment.assert_called_once()

    def test_pr_number_must_be_numeric(self):
        with mock.patch.dict(os.environ, {"PR_NUMBER": "42; echo pwned"}):
            with self.assertRaises(SystemExit):
                job.main(["evaluate"])

    def test_pr_number_is_required(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("PR_NUMBER")
            with self.assertRaises(SystemExit):
                job.main(["evaluate"])


if __name__ == "__main__":
    unittest.main()
