---
id: FM-0005
title: actions are pinned to mutable major tags, not commit SHAs
type: wontfix
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
      STRUCK (wontfix). Every `uses:` names a commit SHA with the version in a
      trailing comment. Declined on 2026-09-10; the argument is under
      `## Comments`.
    witness: .github/workflows/test.yml
  - claim: >-
      The argument for keeping floating tags is written down rather than left
      implicit, so the next reader inherits a decision instead of an accident.
    witness: .fmo/specs/FM-0005-actions-pinned-to-mutable-tags.md
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

**2026-09-10 — declined (`wontfix`).** Investigated the threat model against
this repo rather than in general, and the premise does not hold here.

Blast radius of a compromised action, measured not assumed: the repo is public
and not a fork; **zero** secrets are configured on it and none are referenced in
the workflow; the repository's `default_workflow_permissions` is **already
`read`** with PR approval off; and nothing is published, uploaded or deployed
from CI. A hostile action would get a read-only token on an already-public repo
and no artifact to poison. What is left is runner abuse and a falsified test
verdict, neither of which propagates.

All four actions are first-party `actions/*`. The tag-moving attacks that
motivate SHA-pinning hit *third-party* actions harvesting secrets; compromising
`actions/checkout` means compromising GitHub, which pinning does not save you
from either.

The cost, meanwhile, is real and was demonstrated three weeks ago. On
2026-07-20 `actions/checkout` published v2.8.0, v3.7.0, v4.4.0, v5.1.0, v6.1.0
and v7.0.1 on the same day -- a `node24` runtime migration backported across
every major line. All four actions here now report `using: node24`. A SHA pin
taken before that date would have frozen on `node20` and broken when runners
drop it; the floating `v4` tag absorbed it for nothing. There is no
`dependabot.yml` in this repo, so pins would go stale by default rather than by
neglect.

Revisit if any of the measured facts change -- a secret is added, the workflow
starts publishing something, or a third-party action is introduced. The first
two are the ones that would actually move the answer.

Superseded in substance by **FM-0007**: the actions are 1-3 majors behind, which
is the drift that is really there, and pinning would have frozen it in place.
