---
description: |
  Shared custom safe-output job for the CI Doctor MQ workflow.
  Records a summary of the completed investigation to the Grafana-connected
  metrics Postgres database (the same database the workflow_rerunner writes to).
  Runs on the `aks-linux-small` runner because only that runner can reach the
  metrics database.
safe-outputs:
  jobs:
    record-investigation-db:
      description: "Record a summary of the completed investigation to the CI Doctor MQ metrics database. Call this exactly once at the end of every actionable investigation (i.e. whenever an investigation record and pattern were produced in Phase 5), after the signature hash and investigation id are known. Do NOT call it on noop / missing_data paths."
      runs-on: aks-linux-small
      output: "Investigation summary recorded to the metrics database."
      permissions:
        contents: read
      inputs:
        run_id:
          description: "Numeric ID of the analysed failed GitHub Actions workflow run (github.event.workflow_run.id for merge-queue triggers, or the run_id input for workflow_dispatch). Report as a numeric string."
          required: true
          type: string
        repository:
          description: "The owner/repo of the repository that owns the analysed run (e.g. 'openvinotoolkit/openvino'). Defaults to the current repository when omitted."
          required: false
          type: string
          default: "not_found"
        pipeline_url:
          description: "URL of the failed GitHub Actions workflow run that was analysed by the CI Doctor."
          required: true
          type: string
        workflow_name:
          description: "Name of the failed workflow (as reported by `get_workflow_run`, e.g. 'Linux (Ubuntu 22.04, Python 3.11)'). Never the CI Doctor MQ workflow name."
          required: true
          type: string
        failed_job_names:
          description: "Comma-separated list of every job that failed in the analysed run (e.g. 'Build, Python unit tests')."
          required: true
          type: string
        pr_url:
          description: "URL of the pull request associated with the failed merge-queue pipeline. Omit when no PR is associated."
          required: false
          type: string
          default: "not_found"
        restarted:
          description: "Whether the failed pipeline's failed jobs were re-run by this investigation (i.e. rerun_failed_jobs was called). String-encoded boolean: 'true' or 'false'."
          required: true
          type: string
        readded_to_merge_queue:
          description: "Whether the associated PR was re-added to the merge queue by this investigation (i.e. readd_to_merge_queue was called). String-encoded boolean: 'true' or 'false'."
          required: true
          type: string
        comment_created:
          description: "Whether a remediation comment was posted on the associated PR by this investigation (i.e. add_comment was called). String-encoded boolean: 'true' or 'false'."
          required: true
          type: string
        category:
          description: "Failure category. One of: Code Issue, Infrastructure, Dependencies, Configuration, Flaky Test, External Service, Network."
          required: true
          type: string
        signature:
          description: "The stable, job-agnostic failure signature string (<normalized-error>|<category>) shared with the pattern record."
          required: true
          type: string
        investigation_id:
          description: "Filesystem-safe investigation identifier (<YYYY-MM-DD-HH-MM-SS-sss>-<run-id>), matching the investigation file name without extension. Used to build a link to the investigation record."
          required: true
          type: string
        signature_hash:
          description: "Hash of the failure signature, matching the pattern file name <signature-hash>.json. Used to build a link to the pattern record."
          required: true
          type: string
      steps:
        - name: Checkout agentic-workflow scripts
          uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0  # v7.0.0
          with:
            sparse-checkout: .github/scripts/agentic-workflows
            persist-credentials: false
        
        - name: Set up Python
          uses: actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405  # v6.2.0
          with:
            python-version: '3.13'
        
        - name: Install psycopg2
          run: python -m pip install --quiet psycopg2-binary==2.9.12
        
        - name: Record investigation to database
          env:
            PGHOST: ${{ secrets.METRICS_DATABASE_HOST }}
            PGUSER: ${{ secrets.METRICS_DATABASE_USERNAME }}
            PGPASSWORD: ${{ secrets.METRICS_DATABASE_PASSWORD }}
            PGDATABASE: ${{ secrets.METRICS_DATABASE_NAME }}
            PGPORT: '5432'
            CI_DOCTOR_RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
          run: |
            export PYTHONPATH=.github/scripts/agentic-workflows/:${PYTHONPATH}
            python .github/scripts/agentic-workflows/record_investigation_db.py
---

# CI Doctor MQ — Record Investigation to Metrics Database

Shared definition of the `record-investigation-db` custom safe-output job used
by the CI Doctor Merge Queue workflow. It inserts one row summarising the
investigation into the `ci_doctor_mq_investigations` table of the Grafana-
connected metrics Postgres database (the same database the
[workflow_rerunner](../../workflow_rerunner.yml) writes to), so investigations
can be dashboarded alongside automatic reruns.

The job runs on the `aks-linux-small` runner because only that runner has
network access to the metrics database. It reuses the `METRICS_DATABASE_*`
secrets and creates the target table on demand via `CREATE TABLE IF NOT EXISTS`,
so the first run bootstraps it (the metrics DB user must have `CREATE`
privilege). The `ci_doctor_run_url` and the links to the investigation and
pattern files are derived by the job/script from the workflow context, so the
agent only needs to supply the investigation `signature`, `investigation_id`,
and `signature_hash`.

Import it via `imports:` in the consuming workflow's frontmatter, and instruct
the agent to call `record_investigation_db` exactly once per actionable
investigation.
