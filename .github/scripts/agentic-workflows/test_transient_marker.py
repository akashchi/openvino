# Copyright (C) 2018-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import unittest
from types import SimpleNamespace
from unittest import mock

from transient_marker import (
    BOT_LOGIN,
    DEFAULT_REASON,
    MAX_REASON_LENGTH,
    READDED_MARKER,
    TRANSIENT_MARKER,
    bot_markers,
    build_marker,
    parse_markers,
    run_id_from_url,
    sanitize_reason,
)

RUN_URL = "https://github.com/openvinotoolkit/openvino/actions/runs/123456"


def comment(body, login=BOT_LOGIN):
    return SimpleNamespace(body=body, user=SimpleNamespace(login=login))


class SanitizeReasonTest(unittest.TestCase):
    def test_collapses_whitespace_into_one_line(self):
        self.assertEqual(sanitize_reason("  network \r\n timeout\twhile\n\ndownloading "), "network timeout while downloading")

    def test_removes_markup_that_could_escape_the_marker_or_code_span(self):
        reason = sanitize_reason("done --> <script>alert(1)</script> `rm -rf`")
        self.assertNotIn(">", reason)
        self.assertNotIn("<", reason)
        self.assertNotIn("`", reason)

    def test_limits_length(self):
        self.assertEqual(len(sanitize_reason("x" * 1000)), MAX_REASON_LENGTH)

    def test_empty_reason_gets_default(self):
        for value in ("", "   \n", None, "<>`"):
            with self.subTest(value=value):
                self.assertEqual(sanitize_reason(value), DEFAULT_REASON)


class MarkerTest(unittest.TestCase):
    def test_round_trip(self):
        body = "visible text\n" + build_marker(TRANSIENT_MARKER, run_url=RUN_URL, reason="runner lost")
        self.assertEqual(parse_markers(body, TRANSIENT_MARKER), [{"run_url": RUN_URL, "reason": "runner lost"}])

    def test_marker_is_an_html_comment(self):
        marker = build_marker(TRANSIENT_MARKER, run_url=RUN_URL)
        self.assertTrue(marker.startswith("<!-- ci-doctor-mq-transient:v1\n"))
        self.assertTrue(marker.endswith("\n-->"))

    def test_reason_with_equals_sign_is_kept_whole(self):
        body = build_marker(TRANSIENT_MARKER, run_url=RUN_URL, reason="exit code=1")
        self.assertEqual(parse_markers(body, TRANSIENT_MARKER)[0]["reason"], "exit code=1")

    def test_crlf_line_endings_are_accepted(self):
        body = build_marker(TRANSIENT_MARKER, run_url=RUN_URL, reason="x").replace("\n", "\r\n")
        self.assertEqual(parse_markers(body, TRANSIENT_MARKER), [{"run_url": RUN_URL, "reason": "x"}])

    def test_returns_markers_in_order(self):
        body = build_marker(TRANSIENT_MARKER, run_url="a") + "\n" + build_marker(TRANSIENT_MARKER, run_url="b")
        self.assertEqual([m["run_url"] for m in parse_markers(body, TRANSIENT_MARKER)], ["a", "b"])

    def test_other_marker_names_and_versions_are_ignored(self):
        body = build_marker(READDED_MARKER, run_url=RUN_URL)
        self.assertEqual(parse_markers(body, TRANSIENT_MARKER), [])
        self.assertEqual(parse_markers(body.replace(":v1", ":v2"), READDED_MARKER), [])

    def test_unterminated_marker_is_ignored(self):
        self.assertEqual(parse_markers(f"<!-- {TRANSIENT_MARKER}:v1\nrun_url={RUN_URL}\n", TRANSIENT_MARKER), [])

    def test_empty_body(self):
        self.assertEqual(parse_markers("", TRANSIENT_MARKER), [])
        self.assertEqual(parse_markers(None, TRANSIENT_MARKER), [])

    def test_build_rejects_values_that_would_break_the_marker(self):
        for value in ("two\nlines", "carriage\rreturn", "close --> early"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    build_marker(TRANSIENT_MARKER, reason=value)


class BotMarkersTest(unittest.TestCase):
    def test_only_comments_authored_by_the_actions_bot_count(self):
        marker = build_marker(TRANSIENT_MARKER, run_url=RUN_URL, reason="x")
        comments = [
            comment(marker, login="some-contributor"),
            comment("no marker here"),
            comment(marker),
            SimpleNamespace(body=marker, user=None),
            comment(None),
        ]
        self.assertEqual(bot_markers(comments, TRANSIENT_MARKER), [{"run_url": RUN_URL, "reason": "x"}])

    def test_marker_names_are_independent(self):
        comments = [comment(build_marker(READDED_MARKER, run_url=RUN_URL))]
        self.assertEqual(bot_markers(comments, TRANSIENT_MARKER), [])
        self.assertEqual(bot_markers(comments, READDED_MARKER), [{"run_url": RUN_URL}])


class RunIdFromUrlTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        os.environ.pop("GITHUB_SERVER_URL", None)
        self.addCleanup(patcher.stop)

    def test_run_url_of_the_repository(self):
        self.assertEqual(run_id_from_url(RUN_URL, "openvinotoolkit/openvino"), "123456")
        self.assertEqual(run_id_from_url(RUN_URL + "/", "openvinotoolkit/openvino"), "123456")

    def test_repository_comparison_ignores_case(self):
        self.assertEqual(run_id_from_url(RUN_URL, "OpenVINOToolkit/OpenVINO"), "123456")

    def test_rejects_other_repository_host_or_shape(self):
        for url in (
            "https://github.com/other/openvino/actions/runs/1",
            "https://evil.example/openvinotoolkit/openvino/actions/runs/1",
            "http://github.com/openvinotoolkit/openvino/actions/runs/1",
            "https://github.com/openvinotoolkit/openvino/actions/runs/1/job/2",
            "https://github.com/openvinotoolkit/openvino/actions/runs/abc",
            "https://github.com/openvinotoolkit/openvino/actions/runs/1?x=1",
            "https://github.com/openvinotoolkit/openvino/actions/runs/1#frag",
            "https://github.com/openvinotoolkit/openvino/pull/1",
            "",
            None,
        ):
            with self.subTest(url=url):
                self.assertEqual(run_id_from_url(url, "openvinotoolkit/openvino"), "")

    def test_honours_the_server_url(self):
        with mock.patch.dict(os.environ, {"GITHUB_SERVER_URL": "https://ghe.example.com"}):
            self.assertEqual(run_id_from_url("https://ghe.example.com/o/r/actions/runs/7", "o/r"), "7")
            self.assertEqual(run_id_from_url("https://github.com/o/r/actions/runs/7", "o/r"), "")


if __name__ == "__main__":
    unittest.main()
