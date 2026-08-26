# Handbook content

These markdown files are the source of truth for handbook content. They
are no longer built into a separate static site — the React app fetches
them at runtime via the GitHub API and renders them inline (at the point
of action for templates, in the Handbook tab for long-form reading).

Why they are rendered that way rather than built into a site of their
own is `docs/decisions/d-18-static-pages-with-islands.md`.

Layout:

- `start-here/`  — overview, glossary, first-webinar
- `roles.md`     — team roles
- `workflow/`    — phase-specific instructions (sourcing, preparation, hosting, after)
- `toolkit/`     — email and post templates
- `governance/`  — editorial line, board, selection criteria, decision log
- `reference/`   — the workspace, tools, contacts, standing up, operations, schema

`reference/standing-up.md` is generated from `STANDING-UP.yml` and is the
one page here written for somebody who does not have an instance yet.
