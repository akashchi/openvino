# Copyright (C) 2018-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import contextlib
import io
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
from unittest.mock import Mock

import remediate_transient_failure as job
from transient_marker import BOT_LOGIN, TRANSIENT_MARKER, build_marker, parse_markers

REPOSITORY = "openvinotoolkit/openvino"
RUN_URL = f"https://github.com/{REPOSITORY}/actions/runs/555"


def make_run(**overrides):
    values = {
        "id": 555,
        "html_url": RUN_URL,
        "event": "merge_group",
        "conclusion": "failure",
        "run_attempt": 1,
        "head_branch": "gh-readonly-queue/master/pr-42-0123abc",
        "pull_requests": [],
    }
    values.update(overrides)
    run = SimpleNamespace(**values)
    run.rerun_failed_jobs = Mock(return_value=True)
    return run


def make_pull(comments=(), **overrides):
    values = {"number": 42, "merged": False, "state": "open", "draft": False}
    values.update(overrides)
    pull = SimpleNamespace(**values)
    pull.get_issue_comments = Mock(return_value=list(comments))
    pull.create_issue_comment = Mock()
    return pull


def make_repo(pull):
    repo = Mock()
    repo.default_branch = "master"
    repo.get_pull.return_value = pull
    return repo


def bot_comment(body):
    return SimpleNamespace(body=body, user=SimpleNamespace(login=BOT_LOGIN))


class RemediateTestCase(unittest.TestCase):
    def setUp(self):
        env_file = tempfile.NamedTemporaryFile("w+", delete=False)
        env_file.close()
        self.env_path = env_file.name
        self.addCleanup(os.unlink, self.env_path)
        patcher = mock.patch.dict(os.environ, {"GITHUB_ENV": self.env_path})
        patcher.start()
        self.addCleanup(patcher.stop)
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def github_env(self):
        with open(self.env_path, encoding="utf-8") as handle:
            return handle.read().splitlines()

    def remediate(self, status, run, pull, reason="network timeout"):
        repo = make_repo(pull)
        with mock.patch.object(job, "merge_queue_status", return_value=status):
            job.remediate(Mock(), repo, run, str(run.id), REPOSITORY, reason)
        return repo

    def assert_no_side_effects(self, run, pull, repo):
        run.rerun_failed_jobs.assert_not_called()
        pull.create_issue_comment.assert_not_called()
        repo.get_workflow.assert_not_called()
        self.assertEqual(self.github_env(), [])


class PullRequestStillQueuedTest(RemediateTestCase):
    def test_reruns_failed_jobs_without_leaving_a_marker(self):
        run, pull = make_run(), make_pull()
        repo = self.remediate("in_queue", run, pull)

        run.rerun_failed_jobs.assert_called_once_with()
        pull.create_issue_comment.assert_called_once()
        body = pull.create_issue_comment.call_args.args[0]
        self.assertNotIn("<!--", body)
        self.assertIn(RUN_URL, body)
        repo.get_workflow.assert_not_called()
        self.assertEqual(self.github_env(), ["RERUN_FAILED_JOBS=true"])

    def test_second_attempt_is_not_re_run_and_leaves_no_marker(self):
        run, pull = make_run(run_attempt=2), make_pull()
        repo = self.remediate("in_queue", run, pull)
        self.assert_no_side_effects(run, pull, repo)

    def test_rejected_rerun_is_an_error_and_leaves_no_marker(self):
        run, pull = make_run(), make_pull()
        run.rerun_failed_jobs.return_value = False
        with self.assertRaises(SystemExit):
            self.remediate("in_queue", run, pull)
        pull.create_issue_comment.assert_not_called()


class PullRequestAlreadyDroppedTest(RemediateTestCase):
    def test_posts_marker_and_dispatches_the_readd_workflow(self):
        run, pull = make_run(), make_pull()
        repo = self.remediate("not_in_queue", run, pull, reason="network timeout")

        run.rerun_failed_jobs.assert_not_called()
        pull.create_issue_comment.assert_called_once()
        body = pull.create_issue_comment.call_args.args[0]
        self.assertEqual(
            parse_markers(body, TRANSIENT_MARKER),
            [{"run_url": RUN_URL, "reason": "network timeout"}],
        )
        self.assertIn("transient", body)
        repo.get_workflow.assert_called_once_with("ci-doctor-mq-readd.yml")
        repo.get_workflow.return_value.create_dispatch.assert_called_once_with(ref="master", inputs={"pr_number": "42"}, throw=True)
        self.assertEqual(self.github_env(), ["TRANSIENT_MARKER_POSTED=true"])

    def test_reason_is_sanitized_before_it_reaches_the_comment(self):
        run, pull = make_run(), make_pull()
        self.remediate("not_in_queue", run, pull, reason="x --> <b>bold</b>\n`code` @maintainer")
        body = pull.create_issue_comment.call_args.args[0]
        (marker,) = parse_markers(body, TRANSIENT_MARKER)
        self.assertEqual(marker["reason"], "x -- bbold/b code @maintainer")
        self.assertEqual(body.count("-->"), 1)
        self.assertNotIn("<b>", body)
        self.assertNotIn("`code`", body)

    def test_empty_reason_falls_back_to_a_default(self):
        run, pull = make_run(), make_pull()
        self.remediate("not_in_queue", run, pull, reason="")
        (marker,) = parse_markers(pull.create_issue_comment.call_args.args[0], TRANSIENT_MARKER)
        self.assertEqual(marker["reason"], "transient failure")

    def test_existing_marker_for_the_run_is_not_duplicated_but_dispatch_is_retried(self):
        existing = bot_comment(build_marker(TRANSIENT_MARKER, run_url=RUN_URL, reason="x"))
        run, pull = make_run(), make_pull(comments=[existing])
        repo = self.remediate("not_in_queue", run, pull)

        pull.create_issue_comment.assert_not_called()
        repo.get_workflow.return_value.create_dispatch.assert_called_once()
        self.assertEqual(self.github_env(), [])

    def test_marker_for_another_run_or_from_another_author_does_not_count(self):
        other_run = bot_comment(build_marker(TRANSIENT_MARKER, run_url=RUN_URL + "9", reason="x"))
        forged = SimpleNamespace(
            body=build_marker(TRANSIENT_MARKER, run_url=RUN_URL, reason="x"),
            user=SimpleNamespace(login="some-contributor"),
        )
        run, pull = make_run(), make_pull(comments=[other_run, forged])
        self.remediate("not_in_queue", run, pull)
        pull.create_issue_comment.assert_called_once()

    def test_dispatch_failure_is_an_error(self):
        run, pull = make_run(), make_pull()
        repo = make_repo(pull)
        repo.get_workflow.return_value.create_dispatch.side_effect = RuntimeError("422 no workflow_dispatch trigger")
        with mock.patch.object(job, "merge_queue_status", return_value="not_in_queue"):
            with self.assertRaisesRegex(RuntimeError, "422"):
                job.remediate(Mock(), repo, run, "555", REPOSITORY, "x")

    def test_no_marker_when_the_readd_workflow_cannot_act_on_it(self):
        cases = {
            "not a merge-queue run": ({"event": "pull_request"}, {}),
            "run did not fail": ({"conclusion": "cancelled"}, {}),
            "run was already re-run": ({"run_attempt": 2}, {}),
            "pull request is a draft": ({}, {"draft": True}),
            "pull request is closed": ({}, {"state": "closed"}),
            "pull request is merged": ({}, {"merged": True}),
        }
        for name, (run_overrides, pull_overrides) in cases.items():
            with self.subTest(name):
                run, pull = make_run(**run_overrides), make_pull(**pull_overrides)
                repo = self.remediate("not_in_queue", run, pull)
                self.assert_no_side_effects(run, pull, repo)


class NothingToRemediateTest(RemediateTestCase):
    def test_merged_and_unknown_statuses_do_nothing(self):
        for status in ("merged", "unknown"):
            with self.subTest(status):
                run, pull = make_run(), make_pull()
                repo = self.remediate(status, run, pull)
                self.assert_no_side_effects(run, pull, repo)

    def test_run_without_a_pull_request_does_nothing(self):
        run = make_run(head_branch="master")
        repo = make_repo(make_pull())
        with mock.patch.object(job, "merge_queue_status") as status:
            job.remediate(Mock(), repo, run, "555", REPOSITORY, "x")
        status.assert_not_called()
        run.rerun_failed_jobs.assert_not_called()


class ResolvePrNumberTest(unittest.TestCase):
    def test_number_comes_from_the_merge_queue_branch(self):
        self.assertEqual(job.resolve_pr_number(make_run()), "42")

    def test_falls_back_to_associated_pull_requests(self):
        run = make_run(head_branch="feature", pull_requests=[SimpleNamespace(number=7)])
        self.assertEqual(job.resolve_pr_number(run), "7")

    def test_no_pull_request(self):
        self.assertEqual(job.resolve_pr_number(make_run(head_branch="feature")), "")


if __name__ == "__main__":
    unittest.main()
