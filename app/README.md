# Reserved — Chantier B (the dynamic layer)

This folder is intentionally empty.

It is reserved for **Chantier B**: a friendly, low-barrier interface for non-technical volunteers, built on top of the Git data in [`../data/`](../data/). It will let people track invitations, follow each webinar's progress visually, and run polls — without ever seeing raw GitHub or YAML.

Chantier B will be designed in its own specification, later, once Chantier A (this handbook + data model) is in use.

**Guiding principle:** the data lives in Git as the source of truth; any UI built here is a *replaceable projection* of it. If the dynamic layer is ever retired, the data — and the workflow — survive untouched.
