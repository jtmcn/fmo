---
id: FM-0004
title: both jobs write the same cache keys, so one reservation fails on every cache miss
type: bug
priority: 2
claimed_by: joel
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
      At most one job saves each cache key. `full` saves; `no-reasoner` only
      restores, so the two jobs cannot contend for a reservation.
    witness: .github/workflows/test.yml
  - claim: >-
      The landing PR's CI run carries no `Unable to reserve cache` line. That
      run is a guaranteed miss, because the second claim changes the venv key,
      and a miss is the only time the race shows.
    witness: >-
      gh run view <landing PR run> --log | grep -c 'Unable to reserve cache'
      (expect 0, alongside at least one `Cache saved with key`)
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

The jobs run in parallel, so on a cache miss both try to reserve the same key and
one loses. Observed on `main`, run 33982347328:

```
full suite (JDK 21)  Post Cache robot.jar
  Failed to save: Unable to reserve cache with key robot-v1.9.10, another job may be creating this cache.
full suite (JDK 21)  Post Cache the virtualenv
  Failed to save: Unable to reserve cache with key poetry-Linux-579856eb..., another job may be creating this cache.
full suite (no usable reasoner)  Post Cache robot.jar
  Cache saved with key: robot-v1.9.10
```

On a hit neither job saves, so the line appears only when a key is new to the
branch's cache scope: 3 of the last 15 runs, as of 2026-09-15.

Not currently harmful — the loser's content is byte-identical to the winner's,
and `Verify robot.jar` checks the digest on the restore path, so a bad entry
cannot go unnoticed. But it puts a red-herring `Failed to save` in the log of
every run that misses, which is a poor thing to have in a repo whose whole
subject is telling a real failure from a benign one. Whoever debugs a genuine
cache problem here will first have to rule this out.

Worth noting which job wins: the reservation is taken by `no-reasoner`, the job
whose `java` cannot run. The jar it caches was never successfully executed in
that job. Harmless because the digest is verified rather than trusted, but it is
the reverse of what you would assume from reading the file.

**Separately, the venv cache key omits the Python version.** `poetry-${{
runner.os }}-${{ hashFiles('poetry.lock') }}` does not vary with the
interpreter, and `runner.os` is `Linux` for every Ubuntu image, so the key cannot
tell 3.12.x from 3.12.y. CI resolved `3.12` to `3.12.14` on 2026-09-15.

The two halves interact: once the Python version is in the key, every runner
patch bump is a miss, so fixing the second makes the first happen more often.
Land them together.

## Out of scope

Whether the two jobs should share their setup steps at all — that is FM-0006.
Per-job keys (`${{ github.job }}` in the key) were considered and not chosen:
they remove the contention by storing every cache twice.

## Notes for the agent

- `full` keeps `actions/cache` for both caches and is the only job that saves.
  `full` is the job that actually runs the jar, so it should be the one that
  caches it.
- `no-reasoner` switches both caches to `actions/cache/restore` (same major as
  `actions/cache`). Its `Fetch robot.jar` guard (`cache-hit != 'true'`) and
  `Verify robot.jar` step stay as they are, so a miss there still fetches and
  checks the digest, it just saves nothing.
- Give `actions/setup-python` an `id` and put
  `steps.<id>.outputs.python-version` in the venv key, in both jobs. The
  restore-only job must compute the identical key or it will never hit.
- Witness for the second claim: the PR's own run. Read the `Post Cache` lines
  from the log rather than the check mark; a green run with the line present
  still fails the claim.

## Comments

**2026-09-15 — triaged, `ready-for-agent`.** Verified against CI: the race
reproduces only on a miss (runs 33929105686, 33929123233, 33982347328), and is
absent from every hit since, including d4cbf68 after FM-0003 landed. FM-0003 is
done, so this is unblocked. The first claim's old witness was the workflow
file, which cannot see a log line; it is split into a structural claim the file
can witness and a log claim the landing PR's run can falsify. Fix shape chosen:
restore-only in `no-reasoner`, over per-job keys.

**2026-09-18 — done.** PR #43, run 35372397038, on the branch
`joel/fm-0004-cache-keys`. All three claims pass:

- `full` is the only job with `actions/cache`; `no-reasoner` uses
  `actions/cache/restore` for both caches.
- The run carries no `Unable to reserve cache` line, and exactly one
  `Cache saved with key`, from `full`. It was a real miss, not a quiet hit: the
  new venv key had never been stored, and the log shows it saved as
  `poetry-Linux-3.12.14-579856eb…`. `robot-v1.9.10` was unchanged and restored
  in both jobs, which is the restore-only path working.
- The key now carries `3.12.14` rather than `3.12`.

Both assertions held too — `skips: 0` for the JDK job, `skips: 6, of which
probed: 6` for the stub job — so the bump did not buy a green run over a suite
that reasoned about nothing.
