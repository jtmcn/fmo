---
id: FM-0006
title: the two jobs duplicate six steps verbatim -- matrix, or duplication on purpose?
type: decision
priority: 4
depends_on:
  - FM-0005
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
