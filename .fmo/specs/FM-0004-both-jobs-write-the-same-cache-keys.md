---
id: FM-0004
title: both jobs write the same cache keys, so one reservation fails on every run
type: bug
priority: 2
depends_on:
  - FM-0003
touches:
  - .github/workflows/test.yml
forbidden:
  - src/**
  - scripts/**
  - examples/**
risk: low
acceptance:
  - claim: >-
      The two jobs no longer contend for one cache key, and a run's log carries
      no `Failed to save: Unable to reserve cache` line.
    witness: .github/workflows/test.yml
  - claim: >-
      The virtualenv cache key varies with the resolved Python version, so a
      runner-image patch bump cannot restore a venv built against a different
      interpreter.
    witness: .github/workflows/test.yml
---

Migrated from GitHub issue #37. Found in review of PR #35.

## Context

`.github/workflows/test.yml` gives both jobs identical cache keys:

```yaml
key: poetry-${{ runner.os }}-${{ hashFiles('poetry.lock') }}
key: robot-${{ env.ROBOT_VERSION }}
```

## Problem

The jobs run in parallel, so both try to reserve the same key and one loses.
Observed on `main`, run 33982347328:

```
full suite (JDK 21)  Post Cache robot.jar
  Failed to save: Unable to reserve cache with key robot-v1.9.10, another job may be creating this cache.
full suite (JDK 21)  Post Cache the virtualenv
  Failed to save: Unable to reserve cache with key poetry-Linux-579856eb..., another job may be creating this cache.
full suite (no usable reasoner)  Post Cache robot.jar
  Cache saved with key: robot-v1.9.10
```

Not currently harmful — the loser's content is byte-identical to the winner's,
and `Verify robot.jar` checks the digest on the restore path, so a bad entry
cannot go unnoticed. But it puts a red-herring `Failed to save` in the log of
every run, which is a poor thing to have in a repo whose whole subject is
telling a real failure from a benign one. Whoever debugs a genuine cache problem
here will first have to rule this out.

Worth noting which job wins: the reservation is taken by `no-reasoner`, the job
whose `java` cannot run. The jar it caches was never successfully executed in
that job. Harmless because the digest is verified rather than trusted, but it is
the reverse of what you would assume from reading the file.

**Separately, the venv cache key omits the Python version.** `poetry-${{
runner.os }}-${{ hashFiles('poetry.lock') }}` does not vary with the
interpreter, and `runner.os` is `Linux` for every Ubuntu image, so the key cannot
tell 3.12.x from 3.12.y.

## Out of scope

Whether the two jobs should share their setup steps at all — that is FM-0006.

## Notes for the agent

Blocked on FM-0003 only because both edit the same file.

## Comments
