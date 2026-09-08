# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those
roles to where they surface in this repo's tracker (spec files under
`.fmo/specs/`), since a spec on disk carries no GitHub label strings. Nothing
needs creating in GitHub, and no `gh label` call is ever correct here.

| Skill role        | Surfaces in a spec as                                          | Meaning                                   |
| ----------------- | -------------------------------------------------------------- | ----------------------------------------- |
| `needs-triage`    | a fresh spec: `priority` unset or `0`, `acceptance` unreviewed  | Maintainer needs to evaluate this spec    |
| `needs-info`      | an `acceptance` claim with no `witness`, or `touches` unknown    | Waiting on detail before the work can start |
| `ready-for-agent` | `priority` set, `depends_on` clear, every claim has a witness    | Fully specified, ready for an AFK agent   |
| `ready-for-human` | `risk: elevated`, or blocked by an open `depends_on`             | Requires human implementation             |
| `wontfix`         | `type: wontfix`, claims struck through, closed under `## Comments` | Will not be actioned                    |

Each role maps onto a concrete action:

- **`needs-triage`** → read the frontmatter and the acceptance claims; set
  `priority` and `risk`.
- **`needs-info`** → the missing thing is almost always a witness. A claim
  without one is not ready, because nothing would fail if it stopped holding.
- **`ready-for-agent`** → work the spec; tick claims only once their witness
  actually passes.
- **`ready-for-human`** → route to a person, don't drive it unattended.
- **`wontfix`** → record the argument under `## Comments`; leave the file in
  place. A spec that was decided against is worth more on disk than deleted.

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the
corresponding surfacing from this table rather than creating a GitHub label.
