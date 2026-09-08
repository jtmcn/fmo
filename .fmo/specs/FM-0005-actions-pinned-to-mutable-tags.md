---
id: FM-0005
title: actions are pinned to mutable major tags, not commit SHAs
type: chore
priority: 3
depends_on:
  - FM-0004
touches:
  - .github/workflows/test.yml
forbidden:
  - src/**
  - scripts/**
  - examples/**
risk: low
acceptance:
  - claim: >-
      Every `uses:` names a commit SHA with the version in a trailing comment,
      so no third party can change what runs by moving a tag.
    witness: .github/workflows/test.yml
  - claim: >-
      If the decision goes the other way, the argument for keeping floating
      tags is written down rather than left implicit.
    witness: docs/agents/issue-tracker.md
---

Migrated from GitHub issue #38. Found in review of PR #35.

## Context

`.github/workflows/test.yml` pins its actions to major tags:

```
actions/checkout@v4    actions/setup-python@v5
actions/setup-java@v4  actions/cache@v4   (x4)
```

## Problem

A major tag is a moving pointer. Whoever controls the action repo can move `v4`
to any commit, and the workflow — which runs on every push to `main` — will
execute it.

That is the same mutability argument PR #35 made about ROBOT, and answered
there: `ROBOT_VERSION: v1.9.10` was not enough, so the jar is now checked against
a SHA-256 digest on both the download and the cache-restore path, because a
release asset can be replaced behind its tag.

The actions are the remaining half of that argument, and the larger half:
`robot.jar` is invoked by `make`, whereas an action runs with the workflow's own
token and filesystem access.

## Out of scope

Adding Dependabot. If SHA pins land, keeping them fresh is a separate decision.

## Notes for the agent

The counter-argument is real and worth stating: SHA pins do not float security
patches in, so they need Dependabot or a periodic bump to avoid going stale.
That is a maintenance cost, not a reason the current state is right — the ROBOT
pin took on exactly the same cost deliberately, on the grounds that CI wants the
same one as yesterday.

**Reasonable to close as `wontfix`** for a personal repo. It is filed because
PR #35's thesis was pinning rigor, and leaving the workflow's own dependencies on
floating tags is the kind of asymmetry this repo usually writes down rather than
leaves implicit. If it is declined, record the argument under `## Comments` and
set `type: wontfix` rather than deleting the file.

## Comments
