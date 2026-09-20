---
id: FM-0006
title: the two jobs duplicate six steps verbatim -- matrix, or duplication on purpose?
type: decision
priority: 4
claimed_by: joel
depends_on:
  - FM-0007
touches:
  - .github/workflows/test.yml
  - CLAUDE.md
forbidden:
  - src/**
  - scripts/**
  - examples/**
risk: low
acceptance:
  - claim: >-
      The duplication is either removed or defended. Whichever way it goes, the
      reasoning sits in CLAUDE.md's CI section next to the workflow's other
      arguments -- the current state is neither, which is the one state that
      drifts.
    witness: CLAUDE.md
---

Migrated from GitHub issue #39. Found in review of PR #35.

## Context

The two jobs in `.github/workflows/test.yml` share six steps verbatim: checkout,
setup-python, install poetry, cache venv, `poetry install`, and
cache/fetch/verify robot.jar. They differ in exactly two places — `full` adds
`setup-java`, `no-reasoner` adds the stub-PATH step — plus their closing
assertions, which are genuinely different and should stay so.

## Problem

This is a decision, not a defect, and both answers are defensible.

**Matrix**: a `strategy.matrix` over `reasoner: [jdk, stub]` with `if:` guards on
the two differing steps gives one copy of the shared setup, so a change to it
cannot land in one job and not the other. The failure mode being avoided is real
and this repo has hit its analogue repeatedly — `scripts/reasoner.py` exists
because two copies of the "is there a reasoner" question drifted, and
`scripts/ledger.py` exists because three copies of one set of invariants did.

**Duplication**: with only two cases, two explicit job bodies read
straightforwardly, whereas a matrix with two `if:`-guarded steps hides the
difference that is the entire point of having two jobs. The asymmetry between
them is the subject, and a matrix makes it a conditional rather than a heading.

## Out of scope

The assertions themselves. They differ for good reason and stay separate under
either answer.

## Notes for the agent

Filed so the answer is deliberate rather than inherited. Landing "keep the
duplication" with the argument written into CLAUDE.md satisfies this spec as
fully as landing the matrix does.

## Comments

**2026-09-19 — decided: keep the duplication, and say so.** The argument is in
CLAUDE.md's CI section, next to the workflow's other arguments, which is what
this spec asked for either way.

The premise moved between filing and deciding. `## Context` above says the jobs
share six steps verbatim and differ in exactly two places; since FM-0004 that is
no longer true. `full` saves both caches and `no-reasoner` restores them, so the
two cache steps differ by *action*, not by presence.

That is what settles it. `uses:` takes no expression — the one key besides `id`
where contexts are unavailable, confirmed against the contexts reference rather
than assumed — so a matrix cannot parameterise `actions/cache` against
`actions/cache/restore`. Each cache step would exist twice under `if:` guards:
eight guarded steps to share six. Worse, `Fetch robot.jar` would have to read
`steps.robot_save.outputs.cache-hit != 'true' && steps.robot_restore.outputs.cache-hit != 'true'`,
which is correct only because a skipped step's output is empty — one boolean
spanning "said no" and "said nothing", the exact shape of the ROBOT `--version`
detection bug this repo fixed in PR #29.

A composite action for the shared setup was considered and dropped: the split
cache steps sit in the middle of the sequence, so only two steps would move, in
exchange for a file and a layer of indirection.

The drift argument is not dismissed — it is why `scripts/reasoner.py` and
`scripts/ledger.py` exist. It is outweighed here at two cases, and CLAUDE.md
names what would overturn it: a third environment, or the save/restore split
going away.
