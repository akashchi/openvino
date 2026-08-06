# Copyright (C) 2018-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Record a CI Doctor MQ investigation summary to the Grafana metrics database.

Used by the `record-investigation-db` custom safe-output job of the CI Doctor MQ
workflow (.github/workflows/shared/agentic-workflows/record-investigation-db.md).
Reads the agent output referenced by GH_AW_AGENT_OUTPUT and inserts one row into
the ``ci_doctor_mq_investigations`` table of the metrics Postgres database (the
same database the workflow_rerunner writes to). The table is created on demand
via ``CREATE TABLE IF NOT EXISTS`` so the first run bootstraps it.
"""

from __future__ import annotations

import os

import psycopg2
from psycopg2 import sql

from common import handle_numeric_id, read_agent_item, require_env, resolve_repository

# Branch and subdirectory the CI Doctor MQ workflow persists its memory to.
MEMORY_BRANCH = "memory/ci-doctor-mq"
MEMORY_SUBDIR = "mq"

_VALID_CATEGORIES = {
    "Code Issue",
    "Infrastructure",
    "Dependencies",
    "Configuration",
    "Flaky Test",
    "External Service",
    "Network",
}

_TRUE_VALUES = {"true", "1", "yes"}
_FALSE_VALUES = {"false", "0", "no", ""}


def parse_bool(value: str, label: str) -> bool:
    """Parse a string-encoded boolean safe-output field, defaulting to False."""
    normalized = (value or "").strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    print(f"Warning: {label}='{value}' is not a recognized boolean; treating as False.")
    return False


def optional(value: str) -> str | None:
    """Return the trimmed value, or None for empty / 'not_found' placeholders."""
    trimmed = (value or "").strip()
    if not trimmed or trimmed == "not_found":
        return None
    return trimmed


def blob_url(server_url: str, repository: str, path: str) -> str:
    """Build a GitHub blob URL for a file on the memory branch."""
    return f"{server_url}/{repository}/blob/{MEMORY_BRANCH}/{MEMORY_SUBDIR}/{path}"


def create_table(cursor: "psycopg2.extensions.cursor") -> None:
    """Create the investigations metrics table if it does not exist yet."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ci_doctor_mq_investigations (
            id                     BIGSERIAL PRIMARY KEY,
            recorded_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
            repository_full_name   TEXT,
            failed_pipeline_url    TEXT,
            failed_pipeline_name   TEXT,
            failed_pipeline_run_id BIGINT,
            failed_job_names       TEXT,
            pull_request_url       TEXT,
            restarted              BOOLEAN,
            readded_to_merge_queue BOOLEAN,
            comment_created        BOOLEAN,
            failure_category       TEXT,
            ci_doctor_run_url      TEXT,
            pattern_signature      TEXT,
            investigation_file_url TEXT,
            pattern_file_url       TEXT
        )
        """
    )


def record_investigation(connection, row: dict[str, object]) -> None:
    """Ensure the table exists and insert a single investigation row."""
    cursor = None
    try:
        cursor = connection.cursor()
        create_table(cursor)
        insert_query = sql.SQL(
            """
            INSERT INTO ci_doctor_mq_investigations (
                repository_full_name, failed_pipeline_url, failed_pipeline_name,
                failed_pipeline_run_id, failed_job_names, pull_request_url,
                restarted, readded_to_merge_queue, comment_created,
                failure_category, ci_doctor_run_url, pattern_signature,
                investigation_file_url, pattern_file_url
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """
        )
        cursor.execute(
            insert_query,
            (
                row["repository_full_name"],
                row["failed_pipeline_url"],
                row["failed_pipeline_name"],
                row["failed_pipeline_run_id"],
                row["failed_job_names"],
                row["pull_request_url"],
                row["restarted"],
                row["readded_to_merge_queue"],
                row["comment_created"],
                row["failure_category"],
                row["ci_doctor_run_url"],
                row["pattern_signature"],
                row["investigation_file_url"],
                row["pattern_file_url"],
            ),
        )
        new_id = cursor.fetchone()[0]
        connection.commit()
        print(f"Recorded CI Doctor MQ investigation as row id={new_id}.")
    except psycopg2.Error as error:
        connection.rollback()
        raise SystemExit(f"Failed to record investigation to database: {error}")
    finally:
        if cursor:
            cursor.close()


def main() -> None:
    item = read_agent_item("record_investigation_db")
    run_id = handle_numeric_id(item.get("run_id") or "", "run_id")
    repository = resolve_repository(item.get("repository") or "")

    category = (item.get("category") or "").strip()
    if category and category not in _VALID_CATEGORIES:
        print(f"Warning: category '{category}' is not one of the known CI Doctor categories.")

    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    investigation_id = optional(item.get("investigation_id") or "")
    signature_hash = optional(item.get("signature_hash") or "")

    row = {
        "repository_full_name": repository,
        "failed_pipeline_url": optional(item.get("pipeline_url") or ""),
        "failed_pipeline_name": optional(item.get("workflow_name") or ""),
        "failed_pipeline_run_id": int(run_id),
        "failed_job_names": optional(item.get("failed_job_names") or ""),
        "pull_request_url": optional(item.get("pr_url") or ""),
        "restarted": parse_bool(item.get("restarted") or "", "restarted"),
        "readded_to_merge_queue": parse_bool(item.get("readded_to_merge_queue") or "", "readded_to_merge_queue"),
        "comment_created": parse_bool(item.get("comment_created") or "", "comment_created"),
        "failure_category": category or None,
        "ci_doctor_run_url": optional(os.environ.get("CI_DOCTOR_RUN_URL", "")),
        "pattern_signature": optional(item.get("signature") or ""),
        "investigation_file_url": blob_url(server_url, repository, f"investigations/{investigation_id}.json")
        if investigation_id
        else None,
        "pattern_file_url": blob_url(server_url, repository, f"patterns/{signature_hash}.json")
        if signature_hash
        else None,
    }

    print(f"Recording CI Doctor MQ investigation for {repository} run {run_id} (category: {category or 'n/a'}).")

    connection = psycopg2.connect(
        host=require_env("PGHOST", "PGHOST is not configured; cannot record investigation."),
        port=os.environ.get("PGPORT", "5432"),
        user=require_env("PGUSER", "PGUSER is not configured; cannot record investigation."),
        password=require_env("PGPASSWORD", "PGPASSWORD is not configured; cannot record investigation."),
        database=require_env("PGDATABASE", "PGDATABASE is not configured; cannot record investigation."),
    )
    try:
        record_investigation(connection, row)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
