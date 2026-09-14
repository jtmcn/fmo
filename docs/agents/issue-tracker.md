# Issue tracker: FMO spec files

Work for this repo is tracked as spec files, not GitHub issues. A spec is
`.fmo/specs/FM-NNNN-<slug>.md` — the `<slug>` is a short kebab-case phrase, and
`FM-` matches the `fm:` namespace prefix the ontology already uses.

GitHub Issues on `jtmcn/fmo` are no longer the tracker. The six specs that open
this directory were migrated from issues #21, #22 and #36-39, each of which was
closed with a pointer to its spec file. Pull requests still go through GitHub;
only the work items moved.

## Conventions

- **One spec per file**: `.fmo/specs/FM-NNNN-<slug>.md`, numbered from the
  highest existing `FM-` id + 1, counting `done/` -- an id is never reused.
- **Frontmatter** (YAML between `---` fences, required): `id`, `title`, `type`,
  `priority`, `depends_on`, `touches`, `forbidden`, `risk`, `acceptance`. No
  field is optional. Nothing parses them today — the discipline is the point,
  and a field left blank is a decision nobody made rather than one made and
  written down.
- **Body**: headings `## Context`, `## Problem`, `## Out of scope`, and
  `## Notes for the agent`. `## Comments` at the bottom, appended to over time,
  is where conversation goes.
- **Dependencies**: `depends_on` lists blocking spec ids (e.g. `[FM-0003]`). A
  spec is unblocked when every id it lists is done.
- **Triage state** is read from the frontmatter — `priority`, `depends_on`,
  `risk` and `type` — not from a label string. See `triage-labels.md`.
- **Done** means the file has moved to `.fmo/specs/done/`, in the commit that
  lands the work, as saffron's specs do. A `wontfix` spec stays where it is, so
  `done/` holds only work that happened. The `FM-` id is the stable handle; the
  path changes when a spec lands.

## Acceptance claims carry a witness

Each entry under `acceptance` is a `claim` and a `witness`:

```yaml
acceptance:
  - claim: >-
      Every reasoner target skips rather than fails when ROBOT does not run.
    witness: make validate-negative
```

The `witness` names the thing that would fail if the claim stopped holding — a
make target, a check function, a test name, or the file whose content is the
claim. It is the same requirement the checks themselves are built on: this repo
already refuses a check that traversed nothing (`coverage()`), an empty SPARQL
result, and a validator check without a negative test. A claim nothing can
falsify is the spec-level version of the vacuous pass, and is the one thing a
spec must not contain.

Where a claim is about a defect, prefer a witness that fails *today* — the
negative test that does not exist yet is better named than assumed.

## A spec that introduces a term names its `CONTEXT.md` entry

`CONTEXT.md` is the controlled vocabulary: which word to use for what, and which
not to. A spec that will name something new says so in `## Notes for the agent`,
naming the entry it needs, so the term and the code that uses it do not arrive
in separate weeks. Inventing vocabulary while implementing against it is how a
word comes to mean whatever the implementation needed.

## When a skill says "publish to the issue tracker"

Create the next `FM-` spec file under `.fmo/specs/`.

## When a skill says "fetch the relevant ticket"

Read the referenced `.fmo/specs/FM-NNNN-<slug>.md`, resolving from the `FM-` id
or the number the user passed.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a spec file; research and one-off records
live alongside it.

- **Map**: a spec holding the Notes / Decisions-so-far / Fog body.
- **Child ticket**: another `FM-` spec, with `depends_on` naming the map.
- **Blocking**: `depends_on`. A ticket is unblocked when every id it lists is
  done.
- **Frontier**: scan `.fmo/specs/*.md`, which excludes `done/`, for specs that
  are not `wontfix`, unblocked and unclaimed; lowest `priority` number first,
  then lowest id.
- **Claim**: add `claimed_by:` to the frontmatter and save before any work.
- **Resolve**: confirm every claim's witness passes, append the outcome under
  `## Comments`, `git mv` the spec into `done/`, and add a context pointer to
  the map's Decisions-so-far.
