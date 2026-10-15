# Email — Registration confirmed

*Sent automatically, the moment a registration for one event — or an update
to one — is recorded. Nobody opens this page and fills it in by hand, unlike
every other template in this section, so its placeholders are written in
**square brackets**, not double braces: this page's fields never come from a
speaker record, and `{{ speaker.… }}` would render here as a missing marker,
exactly the failure `toolkit/index.md` warns about. Kept here anyway, in the
same form as every other outbound message, so a board member can read what a
participant receives without opening `tools/convener_ops/journey/confirmation.py`.
`tools/tests/journey/test_confirmation.py` pins this page's two load-bearing
sentences against that module's own constants, so the two cannot quietly
say different things.*

*The room link only ever reaches a participant here: the room is a
permanent account, its link is not
otherwise published, and this e-mail is the one channel it goes out on.*

---

**Subject:** Your registration is confirmed — [the event's title, when known]

Dear [participant's first name],

Your registration for [the event's title] on [the event's date] is
confirmed.

Join here: [the room link]

[the join instructions, when the series has any]

**Put this exact code into the display name you type when you join, and
nowhere else:** [the matching code]

So your display name should read exactly: [your first name] [your surname]
[the matching code] — for example, Ada Lovelace WXYZ-2345.

We compare that name against our attendance record after the seminar to
issue your certificate, so a display name that does not carry this code
means we may not be able to find you in the room. If no code could be
generated for this event, we say so instead, and fall back to matching your
e-mail address and the name on this registration.

---

## Only present when this confirmation replaces an earlier one

This confirms an update to an earlier registration for this event: we
changed the [field or fields that changed, named, never quoted]. If that
was not you, someone else may have used your e-mail address. Please reply
to this message straight away and we will look into it.

*Why this section exists at all: registrations are matched by address, and
our entry point has no shared secret to check — a browser cannot hold one —
so anyone who knows an event id and a participant's address could otherwise
overwrite that participant's name, institution or announce-list preference
without them ever knowing. This paragraph is that participant's one chance
to notice. It names which fields changed, never their old or new values: a
value is worth protecting, a field name is not.*

---

**Data protection.** We hold your name, e-mail address and institution only
for this event, encrypted under a key that exists only for it; the key is
destroyed 90 days after the event, after which the data is permanently
unreadable. It is never published, and it is only ever decrypted
automatically, to record your registration and to issue your certificate.

To see, correct, withdraw or erase your data before then, or for any other
question, reply to this message or write to {{ instance.contact }} —
the same address the registration page itself names for this right.

Best regards,
{{ instance.organisation }} team

---

## Notes for whoever reads this page

- Nothing here is sent by a volunteer. Two steps compose and send it, not
  one: `convener-handle-registration` decrypts and stores the registration, then
  `convener-send-confirmation` — its own step in `.github/workflows/
  registration.yml`, run only once the record has actually landed on the
  branch — composes and delivers this message. Split into two on review:
  the storing step retries on a rejected push, and
  a step that both stored and sent would have sent one confirmation per
  retry. `resend_confirmation` (the `convener-resend-confirmation` command)
  re-sends the same, current message by hand — a certificate in the spam
  folder does not exist — without regenerating the matching
  code: it is a pure function of the event, the address and a secret salt,
  so calling it again reproduces exactly the code the first message
  carried.
- Without `email_transport`'s five secrets configured
  (`declarations/integrations.yml`), nothing here is actually sent: the composed
  message is written to a local file inside the job's own workspace instead,
  never printed — see `tools/convener_ops/journey/confirmation.py`'s module docstring for
  why a message carrying an address and a matching code cannot use the same
  "print it to the job log" fallback `notify.py` uses for a message that
  carries neither.
