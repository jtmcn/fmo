---
id: FM-0007
title: the workflow's actions are 1-3 majors behind and nothing bumps them
type: chore
priority: 3
claimed_by: joel
depends_on:
  - FM-0004
touches:
  - .github/workflows/test.yml
  - .github/dependabot.yml
forbidden:
  - src/**
  - scripts/**
  - examples/**
risk: low
acceptance:
  - claim: >-
      Each action in the workflow is on its current major, or the file says why
      it is held back. Checked 2026-09-10: checkout v4 against v7.0.1,
      setup-python v5 against v7.0.0, setup-java v4 against v6.0.1, cache v4
      against v6.1.0.
    witness: .github/workflows/test.yml
  - claim: >-
      A `.github/dependabot.yml` watches the `github-actions` ecosystem, so the
      next major does not depend on someone happening to look.
    witness: .github/dependabot.yml
  - claim: >-
      Both jobs still pass after the bump, with the same figures as before --
      `skips: 0` for the JDK job, `skips: N, of which probed: N` for the stub
      job. A major bump that quietly stopped the reasoner from being reached
      would otherwise read as green.
    witness: .github/workflows/test.yml
---

Found while investigating FM-0005, which proposed the opposite change.

## Context

The workflow pins its actions to major tags, and those majors are behind:

```
actions/checkout       v4  ->  v7.0.1
actions/setup-python   v5  ->  v7.0.0
actions/setup-java     v4  ->  v6.0.1
actions/cache          v4  ->  v6.1.0
```

Nothing is broken. The v4 and v5 lines are still maintained -- on 2026-07-20
`actions/checkout` shipped v2.8.0 through v7.0.1 on the same day, a `node24`
runtime migration backported across every major line, and all four actions here
now report `using: node24`. Floating tags absorbed that for free.

## Problem

Being three majors behind is not itself a fault, but nothing in this repo would
notice if it became one. There is no `dependabot.yml`, so the version of every
action is decided by whoever last happened to look at the file. The 2026-07-20
backport is the reason that has been survivable so far, and it is a courtesy of
the action's maintainers rather than a property of this repo.

That is the same shape this repo keeps writing down elsewhere: a thing that
happens to be true, with nothing that would fail if it stopped being true.

## Out of scope

**Pinning to commit SHAs.** Declined in FM-0005 on the measured blast radius --
public repo, zero secrets, read-only default token, nothing published. Note the
interaction, though: Dependabot is the prerequisite that would make SHA pins
survivable, so if that decision is ever revisited, it is revisited *after* this
spec, not instead of it.

## Notes for the agent

Bump one major at a time and read the changelog for each; `setup-python` and
`cache` have both changed default behaviour across majors in ways that would
show up here (cache key handling, and what a cache miss does).

The third acceptance claim matters more than it looks. `make test` exits 0 when
every reasoner target skips, so an action bump that broke the JDK setup would
turn the `full` job green over a suite that reasoned about nothing -- which is
exactly what PR #35's assertions were added to catch. Read the two `skips:`
lines from the run, do not just look at the check mark.

FM-0003 through FM-0007 all touch `.github/workflows/test.yml`; the chain is
FM-0003 -> FM-0004 -> FM-0007 -> FM-0006.

## Comments

**2026-09-18 — done.** PR #44, run 35375801601, branch
`joel/fm-0007-bump-actions`. checkout v4->v7, setup-python v5->v7, setup-java
v4->v6, cache v4->v6. All three claims pass:

- Every `uses:` names the action's current major as of today; nothing is held
  back, so the file has nothing to explain.
- `.github/dependabot.yml` watches `github-actions` monthly. Note it takes
  effect once this is on the default branch; Dependabot reads the config from
  `main`, not from the PR.
- `skips: 0` for the JDK job and `skips: 6, of which probed: 6` for the stub
  job — the same figures as run 35374733804 before the bump. The JDK job is the
  one that matters: `setup-java@v6` changed the metadata API it resolves
  distributions from, and a JDK it failed to deliver would have turned the
  reasoner targets into skips over a green run.

Two dependencies were checked at the new tags rather than assumed:
`actions/cache/restore` exists at v6 and still sets `cache-hit`, and
`setup-python@v7` still outputs `python-version`. The run confirms the second
independently — both jobs restored `poetry-Linux-3.12.14-579856eb…`, which is
the key FM-0004 builds from that output. Had it gone, the key would have read
`poetry-Linux--579856eb…` and missed.

The bump was only today's instance of the fault. The fault was that nothing
would notice the next one, and `dependabot.yml` is the part that answers it.
