---
description: |
  Shared custom safe-output job for the CI Doctor MQ workflow.
  Remediates a *transient* merge-queue pipeline failure. The agent calls it
  whenever the failure is transient and knows nothing about the PR's merge-queue
  status; this job resolves that status live and decides on its own: it re-runs
  only the failed jobs when the PR is still queued, and when the PR was already
  dropped it leaves a hidden-marker comment and dispatches the separate
  ci-doctor-mq-readd.yml workflow. It never re-adds a PR to the merge queue itself.
safe-outputs:
  jobs:
    remediate-transient-failure:
      description: "Remediate a TRANSIENT merge-queue pipeline failure. Call this at most once and ONLY when the investigation concludes the failure is transient (Infrastructure, Flaky Test, Network, or External Service categories such as runner hiccups, network timeouts, cancelled jobs, or downstream outages). The job resolves the PR's live merge-queue status itself and decides what to do — you do NOT know or provide the queue status: if the PR is still in the queue it re-runs the failed jobs; if the PR was dropped from the queue it marks the failure as transient on the PR so that a separate workflow can re-add it (this job never re-adds the PR itself). Do NOT call for deterministic Code Issue / Dependencies / Configuration failures that a restart or re-queue cannot fix."
      runs-on: ubuntu-latest
      output: "Transient-failure remediation requested for the analysed workflow run."
      permissions:
        actions: write         # re-run the failed jobs; dispatch the re-add workflow
        contents: read
        pull-requests: write   # read live merge-queue status; post the re-run / transient-failure comment
      inputs:
        run_id:
          description: "Numeric ID of the analysed GitHub Actions workflow run (github.event.workflow_run.id for merge-queue triggers, or the run_id input for workflow_dispatch). Report as a numeric string."
          required: true
          type: string
        repository:
          description: "The owner/repo of the repository that owns the analysed run (e.g. 'openvinotoolkit/openvino'). Defaults to the current repository when omitted."
          required: false
          type: string
          default: "not_found"
        reason:
          description: "Short justification for why the failure is transient and remediation is expected to help (e.g. 'network timeout while downloading dependencies')."
          required: true
          type: string
      steps:
        - name: Checkout agentic-workflow scripts
          uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
          with:
            sparse-checkout: .github/scripts/agentic-workflows
            persist-credentials: false
        - name: Set up Python
          uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97  # v7.0.0
          with:
            python-version: '3.13'
        - name: Install PyGithub
          run: python -m pip install --quiet PyGithub==2.9.1
        - name: Remediate transient failure
          env:
            # GITHUB_TOKEN (with actions: write) re-runs the failed jobs, dispatches the
            # re-add workflow and comments on the PR. The merge-queue token is deliberately
            # absent: only ci-doctor-mq-readd.yml may re-add a PR to the merge queue.
            GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          run: |
            export PYTHONPATH=.github/scripts/agentic-workflows/:${PYTHONPATH}
            python .github/scripts/agentic-workflows/remediate_transient_failure.py
        # The `echo` steps are for collecting and aggregating statistics in Grafana
        - name: Re-run of failed jobs was triggered
          if: ${{ env.RERUN_FAILED_JOBS == 'true' }}
          run: echo "CI Doctor re-ran the failed jobs for the analysed run (PR still in the merge queue)."
        - name: Transient failure marker was posted
          if: ${{ env.TRANSIENT_MARKER_POSTED == 'true' }}
          run: echo "CI Doctor marked the failure as transient on the PR (it had been dropped from the merge queue); the re-add workflow was dispatched."
---

# CI Doctor MQ — Remediate Transient Failure

Shared definition of the `remediate-transient-failure` custom safe-output job
used by the CI Doctor Merge Queue workflow. It is the single remediation entry
point, so the agent only has to decide *whether the failure is transient*, not
*which* remedy applies. The job never re-adds a pull request to the merge queue
itself: that is done by the separate `ci-doctor-mq-readd.yml` workflow.

When invoked, the job:

1. Resolves the PR behind the analysed run (from the
   `gh-readonly-queue/<base>/pr-<number>-<sha>` head branch, falling back to the
   run's associated pull requests).
2. Reads the PR's **live** merge-queue status (`common.merge_queue_status`, which
   prefers the GraphQL `mergeQueue` entries and falls back to the PR's add/remove
   timeline events). Doing this at action time avoids acting on a stale snapshot.
3. Picks the remedy:
   - **`in_queue`** — re-runs only the failed jobs via
     `POST /repos/{owner}/{repo}/actions/runs/{run_id}/rerun-failed-jobs`
     (refuses a run already on its second attempt, to avoid restart loops) and
     posts an outcome comment on the PR. The scheduled re-run is the remedy, so
     **no marker is left** and the PR is never handed to the re-add workflow.
   - **`not_in_queue`** — the merge group is gone, so nothing can be re-run.
     Posts a PR comment carrying the hidden **transient marker** (investigated
     run URL and reason; format and parsing in `transient_marker.py`) and
     dispatches `ci-doctor-mq-readd.yml` for the PR. The marker is left only for
     a failed, never re-run `merge_group` run of an open, non-draft, unmerged PR,
     and not twice for the same run (the dispatch is still sent, so re-running
     this job can complete a failed dispatch). The dispatch is needed because CI
     Doctor usually finishes after the queue already dropped the PR, so the
     workflow's `dequeued` trigger alone would run before the marker exists. The
     re-add workflow decides whether re-adding is still safe.
   - **`merged`** / **`unknown`** — takes no action (fail safe).

It only uses the default `GITHUB_TOKEN` (`actions: write` to re-run and dispatch,
`pull-requests: write` to comment). The `MERGE_QUEUE_TOKEN` secret is
intentionally not available here: it is used only by the single `gh pr merge`
step of `ci-doctor-mq-readd.yml`.

Import it via `imports:` in the consuming workflow's frontmatter, and instruct
the agent to call `remediate_transient_failure` only when the failure is
transient.
