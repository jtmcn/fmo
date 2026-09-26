---
id: FM-0011
title: terms are deleted or redefined in place, and no version records what it replaced
type: feature
priority: 1
depends_on: []
touches:
  - src/core.ttl
  - src/weather.ttl
  - src/kalshi.ttl
  - src/fmo.ttl
  - scripts/lineage.py
  - scripts/test_lineage.py
  - Makefile
  - .github/workflows/test.yml
  - docs/adr/0003-retiring-and-redefining-terms.md
  - CLAUDE.md
  - CONTEXT.md
  - README.md
  - docs/design-notes.md
forbidden:
  - src/imports/**
  - shapes/thermaledge-export.ttl
  - shapes/thermaledge-export.pin.json
risk: elevated
claimed_by: claude
acceptance:
  - claim: >-
      Each module's owl:Ontology header names the version before this one in
      owl:priorVersion, read from git history. Every released version on main
      has a vX.Y.Z tag.
    witness: make lineage, with negative tests in scripts/test_lineage.py; git tag -l 'v*'
  - claim: >-
      A minted IRI present at the previous release tag is either still declared
      at HEAD or carries owl:deprecated true and dcterms:isReplacedBy.
    witness: make lineage, with a negative test in scripts/test_lineage.py that deletes a term
  - claim: >-
      No example, shape or query uses a deprecated term.
    witness: make lineage, with negative tests in scripts/test_lineage.py for a CURIE and a full IRI
  - claim: >-
      ksh:expirationTime exists as a tombstone pointing at
      ksh:expectedExpirationTime and ksh:latestExpirationTime.
    witness: src/kalshi.ttl
  - claim: >-
      wx:SnowDepth and wx:TotalSnowfall each carry a skos:changeNote naming
      0.14.0 and FM-0010, stating what the term meant before.
    witness: src/weather.ttl, reviewed
  - claim: >-
      The rules for retiring a term, redefining one in place, and which change
      bumps which version component are written down.
    witness: docs/adr/0003-retiring-and-redefining-terms.md
---

## Context

ThermalEdge pins FMO terms by `semantics_sha256` (`scripts/term_signatures.py`,
ADR 0002). The digest tells a consumer that a term's commitments moved. Nothing
in the ontology tells it why, since when, or what to use instead.

`scripts/validate.py:113` already anticipates a retirement that leaves a
tombstone (`owl:deprecated` plus the old label). None has ever been written.

## Problem

Two changes have already happened with no trace in the model:

- **Deleted outright.** Commit 610db84 split `ksh:expirationTime` into
  `ksh:expectedExpirationTime` and `ksh:latestExpirationTime` and removed the
  original. A consumer that used it finds nothing at that IRI and no pointer.
- **Redefined in place.** FM-0010 (0.13.0 → 0.14.0) moved `wx:SnowDepth` from
  under `wx:PrecipitationDepth` to disjoint with it, and changed its bearer to
  `wx:SnowCover`. Same IRI, minor bump. Data typed under the old reading is now
  inconsistent. The explanation lives only in the commit message and
  `docs/design-notes.md`.

Around this:

- There are no git tags, so "0.13.0" cannot be checked out except by reading
  the log. `owl:versionIRI` is deliberately non-resolving, so nothing else
  holds a prior version either.
- No module header has `owl:priorVersion` or `owl:incompatibleWith`.
- Nothing defines when a change is patch, minor or major. FM-0010's change of
  meaning went out as a minor bump.

## Out of scope

- Registering w3id redirects or switching to opaque IDs. Both were rejected in
  `docs/design-notes.md`, and tombstones complement readable IRIs rather than
  reopening that.
- The `wtl:` → `fm:` rename (624a20a). It predates any pin and is not worth
  backfilling.
- A CHANGELOG file. Tags plus `priorVersion` plus per-term notes may be enough;
  decide in the ADR.

## Notes for the agent

- Tag the existing releases retroactively where the version-bump commits are
  identifiable (`git log -S 'owl:versionInfo "0.'`). At minimum tag `v0.14.0`
  on HEAD so the new check has a baseline.
- The IRI-continuity check needs the previous tag's modules. `git show
  <tag>:src/kalshi.ttl` into rdflib avoids a checkout. It is population
  `schema`, so `coverage(always=True)`, and `make meta` must still pass.
- Use `dcterms:isReplacedBy`, not IAO's replacement property; IAO is not
  imported.
- A tombstone should keep `rdfs:label` and gain `owl:deprecated true`,
  `dcterms:isReplacedBy`, and a `skos:historyNote` with the version and reason.
  It must not keep its `rdfs:domain`/`rdfs:range`, or it still types data.
- Check how `check_documentation`, `check_bfo_grounding` and
  `term_signatures.py` treat a deprecated term before adding one; each may need
  to skip it. `term_signatures.py` should probably emit a deprecated marker
  rather than drop the term.
- Extend the CLAUDE.md "Version bumps touch all four modules" bullet with
  `owl:priorVersion` and the tag.
- The recorded premise "the ontology has no downstream consumers" (README
  Layout, `docs/design-notes.md` Rejected alternatives) is contradicted by
  ThermalEdge's pins. Restate it precisely — no consumer dereferences the IRIs
  over HTTP — so the rejections it supports stay true.
- New vocabulary: **tombstone**, **retire**, **redefine in place**. Add
  `CONTEXT.md` §4 entries in the same change.

## Comments

**2026-09-25 — resolved in 0.18.0.** Decisions, made by the maintainer:
- Versions stay 0.x, with stated rules.
- Tags are back-filled from history.
- Tombstones stay forever.

All three are written up in `docs/adr/0003-retiring-and-redefining-terms.md`.

The checks live in a new `scripts/lineage.py` (`make lineage`), not in
`validate.py`, which moves three witnesses. Continuity and `priorVersion` need
git history, and `validate.py`'s negative-test harness copies the tree without
`.git`. `lineage.audit()` is a pure function over two graphs and the scanned
file texts, so `scripts/test_lineage.py` feeds it mutations directly: 11
defects, a prefix that must not match, and two empty-population guards.

The prior version comes from history, not from a tag. This stack's own
versions (0.15–0.17) have no tags until they merge, and a check that needed
one would fail on every stacked branch. So tags are for consumers, and CI
checks out with `fetch-depth: 0`.

- **Tags:** `v0.1.0` to `v0.14.0` are pushed. Each sits on the last `main`
  commit at that version, found by reading `owl:versionInfo` at every
  first-parent commit; no commit ever showed two versions across modules.
- **`ksh:expirationTime`:** now a tombstone, retired in 0.7.0 (the first
  release after the split), replaced by both successors.
  `dcterms:isReplacedBy` is declared an annotation property, as
  `skos:closeMatch` is, because its object is an IRI.
- **Change notes:** `wx:SnowDepth` and `wx:TotalSnowfall` carry
  `skos:changeNote`s for 0.14.0.
- **The consumer premise:** restated in `README.md`, `docs/design-notes.md`
  and the `core.ttl` header as "one consumer, which pins and never
  dereferences".

Follow-up, not done: `term_signatures.py` still omits a tombstone rather than
emitting a retired entry with its replacements. That changes the output format
ThermalEdge parses, so it should be agreed with ThermalEdge first.
