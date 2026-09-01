# The published half of each event key

The published public half of each event key: one `<event id>.pub` file per
edition, PEM (`SubjectPublicKeyInfo`), ASCII, the id lower-cased.
`tools/convener_ops/journey/eventkeys.py` generates the pair and writes
only this half. The private half lives as the repository secret
`eventkeys.secret_name` derives — `CONVENER_EVENT_KEY_<ID>`, upper-cased
with `.` and `-` replaced by `_` so the result is a legal Actions secret
name — and is never written to disk.

**This directory holds no key in a fresh clone, and holds none until an
operator generates the first one.** Generating a key is an operator's act,
done once per edition before registration opens, never an automated one —
see *Event registration keys* in `docs/operating/operations.md` for the
procedure. `.gitignore` excludes everything here but `*.pub` and this
file, so the contract survives the directory being empty.

## What each key is for

A registration is hybrid-encrypted under its own event's public key, so
one edition's records can be made unreadable without touching another
edition's — which is what retention does at the end of an event's life.
`docs/engineering/decisions/d-22-key-destruction-not-deletion.md` is why
the key is destroyed rather than the file deleted. One key per event is
the whole of that separation: a single instance-wide key would make every
erasure an erasure of everybody.

`services/signup-relay` reads this directory over the GitHub Contents API
to encrypt a submission at the edge, so a `.pub` file is public data by
construction. Nothing here decrypts anything.

## Naming, and why a key file is never renamed

The file name is the edition code as the event's own public address
spells it (`/events/<event id>/`, D-19), built from
`instance/config.json`'s `edition_prefix`. Written without an example on
purpose: a concrete code here would be this instance's own, in a file the
product owns and every duplicate inherits. That code is a primary key
that has already left the
building: it is in a published address, on every certificate issued for
the event, and inside the secret's own name. So a file here is added and,
at the end of retention, emptied — never renamed.
