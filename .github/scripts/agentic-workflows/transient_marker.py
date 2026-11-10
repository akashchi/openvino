# Copyright (C) 2018-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Hidden PR-comment markers shared by CI Doctor MQ and the merge-queue re-add workflow.

CI Doctor MQ never re-adds a pull request to the merge queue itself. When it
concludes that a merge-queue failure is transient and no re-run is possible, it
leaves a PR comment carrying an invisible marker. The ``ci-doctor-mq-readd.yml``
workflow looks for that marker before it re-adds the PR, and leaves a second
marker behind so a PR is re-added at most once.

A marker is an HTML comment (not rendered by GitHub) holding ``key=value`` lines::

    <!-- ci-doctor-mq-transient:v1
    run_url=https://github.com/<owner>/<repo>/actions/runs/<id>
    reason=<one line>
    -->

Anyone can post a comment containing such text, so a marker is only honoured when
the comment was authored by the GitHub Actions bot (``BOT_LOGIN``), i.e. by a
workflow running with the default ``GITHUB_TOKEN``.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from typing import Any, Iterable

BOT_LOGIN = "github-actions[bot]"
TRANSIENT_MARKER = "ci-doctor-mq-transient"
READDED_MARKER = "ci-doctor-mq-readded"
MARKER_VERSION = "v1"

DEFAULT_REASON = "transient failure"
MAX_REASON_LENGTH = 300

_RUN_PATH_RE = re.compile(r"/([^/]+/[^/]+)/actions/runs/([0-9]+)/?")


def sanitize_reason(reason: str) -> str:
    """Return ``reason`` as a single line that is safe inside an HTML comment and a code span."""
    # Without ``>`` the text cannot close the comment early; ``<`` and backticks
    # would otherwise inject markup into the visible part of the comment.
    text = re.sub(r"[<>`]", "", reason or "")
    text = " ".join(text.split())
    return text[:MAX_REASON_LENGTH].rstrip() or DEFAULT_REASON


def build_marker(name: str, **fields: str) -> str:
    """Return an invisible marker named ``name`` with one ``key=value`` line per field."""
    lines = [f"<!-- {name}:{MARKER_VERSION}"]
    for key, value in fields.items():
        if "\n" in value or "\r" in value or ">" in value:
            raise ValueError(f"marker field '{key}' must be a single line without '>'")
        lines.append(f"{key}={value}")
    lines.append("-->")
    return "\n".join(lines)


def parse_markers(body: str, name: str) -> list[dict[str, str]]:
    """Return the fields of every ``name`` marker in ``body`` (CRLF tolerated), in order."""
    pattern = re.compile(rf"<!--[ \t]*{re.escape(name)}:{MARKER_VERSION}[ \t]*\n(.*?)-->", re.DOTALL)
    markers: list[dict[str, str]] = []
    for match in pattern.finditer((body or "").replace("\r\n", "\n")):
        fields: dict[str, str] = {}
        for line in match.group(1).splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip():
                fields[key.strip()] = value.strip()
        markers.append(fields)
    return markers


def bot_markers(comments: Iterable[Any], name: str) -> list[dict[str, str]]:
    """Return the ``name`` markers of comments authored by the Actions bot, oldest first."""
    markers: list[dict[str, str]] = []
    for comment in comments:
        author = getattr(getattr(comment, "user", None), "login", None)
        if author == BOT_LOGIN:
            markers += parse_markers(comment.body or "", name)
    return markers


def run_id_from_url(url: str, repository: str) -> str:
    """Return the run id of an Actions run URL of ``repository`` on this server, else ''."""
    parts = urllib.parse.urlsplit(url or "")
    server = urllib.parse.urlsplit(os.environ.get("GITHUB_SERVER_URL") or "https://github.com")
    if (parts.scheme, parts.netloc.lower()) != (server.scheme, server.netloc.lower()):
        return ""
    if parts.query or parts.fragment:
        return ""
    match = _RUN_PATH_RE.fullmatch(parts.path)
    if not match or match.group(1).lower() != repository.lower():
        return ""
    return match.group(2)
