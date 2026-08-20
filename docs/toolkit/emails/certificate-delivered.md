# Email — Certificate delivered

*Sent automatically, once per eligible attendee, carrying the certificate of
attendance itself as an attachment (phase 4 task 14) — never a second copy of
[Certificate of attendance](../certificate.md) kept anywhere once this
message has gone out. Nobody opens this page and fills it in by hand, unlike
every other template in this section, so its placeholders are written in
**square brackets**, not double braces, the same convention
[Registration confirmed](registration-confirmed.md) uses for the same
reason. Kept here anyway, so a board member can read what a participant
receives without opening `tools/convener_ops/delivery.py`.
`tools/tests/test_delivery.py` pins this page's subject line against that
module's own composed message, so the two cannot quietly say different
things.*

*Spec §7 is categorical on how a certificate reaches its holder: by e-mail,
and a document naming a person is never deposited in a repository. This
message is the one place in the whole phase that carries the certificate —
a self-contained HTML page with an inline QR code — outside our own
systems, and the certificate is never written to disk here, or anywhere,
before it is attached and sent.*

---

**Subject:** Your certificate of attendance — [the event's title, when known]

Dear [participant's first name],

Attached is your certificate of attendance for [the event's title], as a
self-contained web page you can open in any browser — print it, or use your
browser's own "print to PDF" if you would rather keep a PDF copy.

Identifier: [the certificate's identifier]

Best regards,
The Example Collective team

---

## Notes for whoever reads this page

- **What the attachment is.** The document
  [Certificate of attendance](../certificate.md) describes — one
  self-contained HTML file, with the certificate's own machine-readable
  verification code drawn inline as SVG, never a separate image or a PDF
  built with a binary toolchain. It carries the same signed token whether
  this is the first send or the tenth: the identifier and the token never
  change between a first delivery and a later resend of the same
  certificate.
- **Nothing here is sent by a volunteer, and nothing here is kept.**
  `.github/workflows/issue-certificates.yml` delivers every eligible
  attendee's certificate as a step immediately after issuing it
  (`convener-deliver-certificates`); `.github/workflows/deliver-certificate.yml`
  re-sends one named certificate by hand
  (`convener-deliver-certificate`, keyed by the certificate's own public
  identifier, never by an address). Neither ever writes the rendered
  document to a file, an artefact, or a job log — a delivery that fails is
  reported as a count, never stashed, and recovered by re-running the
  command: the same identifier, the same signed token, the same document,
  reproduced rather than regenerated.
- **A resend is bounded by how long the registration it reads still
  exists.** The certificate itself verifies forever — the register's own
  state is what a verifier checks, and revocation never touches the
  signature. But redelivering it needs the address to send it to, which
  lives only in `data/events/<id>/registrations.enc`; once task 15's
  retention sweep destroys that event's key, 90 days after the event, a
  certificate already issued can still be verified by anyone who holds it,
  but can never be delivered again by us.
- **An unconfigured mailbox degrades differently here than it does for the
  registration confirmation above.** Neither one prints an address or a
  code, but the confirmation falls back to a `.gitignore`d file a
  volunteer can open and paste from by hand; this message has no such
  fallback at all — every attempt is folded into a bare sent/not-sent
  count, and nothing more, because keeping even a private local copy of a
  signed certificate is the one thing spec §7 rules out. See
  `tools/convener_ops/delivery.py`'s module docstring for the full argument.
