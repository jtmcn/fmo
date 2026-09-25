# Retire terms to tombstones, record redefinitions, and let versions say what changed

ThermalEdge pins FMO terms by digest (`scripts/term_signatures.py`, ADR 0002). A digest
tells a consumer that a term moved. It cannot say that a term was retired, what replaced
it, or since when, and two changes had already happened with no trace in the model:
~~`ksh:expirationTime`~~ was deleted outright when it was split in two, and FM-0010 changed
what `wx:SnowDepth` means under the same IRI. We decided four things, and
`make lineage` (`scripts/lineage.py`) enforces the first two against the prior version.

**A retired term becomes a tombstone, forever.** It keeps its IRI and `rdfs:label`, and
gains `owl:deprecated true`, a `skos:historyNote` saying in which version and why, and
`dcterms:isReplacedBy` for each successor when there is one. It keeps no `rdf:type`, no
`rdfs:domain` or `rdfs:range`, and no class axiom, because each of those would still
type or constrain data written against it. `validate.py` already reads a tombstone as
not declared, so `CONTEXT.md` must stop naming it. No example, export fixture, shape or
query may use one. Tombstones cost a few triples each and are never removed, which is
also what lets the continuity check look only one version back: every IRI declared or
tombstoned at the prior version must be declared or tombstoned now, and by induction
no released IRI goes dark from here on. The one exception is the rename before 0.9.0,
which replaced every term's namespace before anything pinned them and is not
back-filled.

**A term redefined in place carries a `skos:changeNote`** naming the version, the spec,
what the term meant before and what it means now. Redefining in place is allowed, since
the alternative is a rename, which costs every consumer a migration. The note is what
makes the redefinition visible, and it sits in the semantics digest so a pin catches it.

**Versions stay 0.x, with stated rules.** A change that moves any term's signature is a
minor bump: a new axiom, a new range, a reworded definition or scope note, a new term, a
retirement. A change that no signature sees is a patch. A change that makes previously
conformant data invalid, such as FM-0010's disjointness or a rename, also sets
`owl:incompatibleWith` on the prior version. Every version bump touches all four
modules' `owl:versionIRI`, `owl:versionInfo` and `owl:priorVersion`, and the status line
in `README.md`.

**Releases are tagged `vX.Y.Z` on the last `main` commit at that version**, since that
is the version's final state before it was superseded. Versions 0.1.0 to 0.14.0 were
back-filled from history. No check depends on a tag: `make lineage` reads the prior
version from git history, because a stack of unmerged versions has no tags yet. The
tags are for a consumer who wants to check a release out. This does mean the check
needs full history, so CI checks out with `fetch-depth: 0`, and a shallow clone fails
rather than skipping.

## Considered and rejected

- **Opaque numeric IRIs** would let labels change freely, which is the OBO answer to
  this problem. They were rejected for legibility (`docs/design-notes.md`), and
  tombstones are the cheaper complement to readable IRIs rather than a reason to reopen
  that decision.
- **Keeping a tombstone for one minor version, then deleting it.** A consumer that
  skips a release would find nothing at the IRI, and the continuity check would have to
  look back an unbounded distance to know what was ever released.
- **Declaring 1.0.0 now.** Full semver would make every breaking change a major bump
  while the model is still settling. The 0.x rules above, together with
  `owl:incompatibleWith`, carry the information a consumer needs without that.
