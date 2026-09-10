---
id: FM-0003
title: test.yml declares no permissions, timeout, or concurrency
type: chore
priority: 2
depends_on: []
touches:
  - .github/workflows/test.yml
forbidden:
  - src/**
  - scripts/**
  - examples/**
risk: low
acceptance:
  - claim: >-
      Both jobs declare `contents: read` explicitly. The repository default is
      already `read`, so this is defence against that default changing, not a
      fix for a token that is currently too broad.
    witness: .github/workflows/test.yml
  - claim: >-
      Both jobs declare a `timeout-minutes`. Observed durations are 5 and 4
      minutes, against a 6-hour default, so a wedged JVM cannot burn a runner
      for 72x longer than the job has ever needed.
    witness: .github/workflows/test.yml
  - claim: >-
      A `concurrency` group keyed on the ref cancels superseded runs, and a
      commit on a branch with an open PR no longer runs the matrix twice.
    witness: .github/workflows/test.yml
---

Migrated from GitHub issue #36. Found in review of PR #35, deliberately left out
of that PR to keep it about the two assertions.

## Context

`.github/workflows/test.yml` declares nothing about the jobs' own bounds. Three
gaps, all one-liners, grouped because they are the same kind of omission — what
the job says about itself.

## Problem

**No `permissions:` block.** Both jobs inherit the repository-default
`GITHUB_TOKEN` scope. That default is currently `read` already (checked
2026-09-10 via `actions/permissions/workflow`), so this is not a live
over-permission -- it is an unstated dependency on a setting outside the file,
which one org-level change silently widens. Declaring `contents: read` makes the
workflow say what it needs. The original framing of this spec claimed the
default was broader; it was not.

**No `timeout-minutes:`.** The GitHub default is 6 hours. Observed on `main`
(run 33982347328): 5 min for `full`, 4 min for `no-reasoner`. `PROBE_TIMEOUT =
60` in `scripts/reasoner.py` already makes this argument one layer in — a wedged
JVM should not hang the thing that called it. Something around 20-30 minutes
leaves generous headroom.

**No `concurrency:` group.** Pushing twice to a branch in quick succession runs
both to completion.

**Related: every commit on a branch with an open PR runs the whole matrix
twice.** `on: push` (unfiltered) plus `on: pull_request` both fire — visible on
PR #35, where run 33942532815 (push) and 33942534565 (pull_request) are the same
commit. Four jobs where two would do.

## Out of scope

Pinning the actions themselves — that is FM-0005.

## Notes for the agent

The usual fix for the double-run is restricting `push` to `branches: [main]` and
letting `pull_request` cover everything else, which also makes the `concurrency`
group behave sensibly.

FM-0003 through FM-0006 all touch `.github/workflows/test.yml`. Land them in
order rather than in parallel.

## Comments
