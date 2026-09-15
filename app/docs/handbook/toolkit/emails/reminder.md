# Email — Reminder

*To the speaker, around T-1 week.*

---

**Subject:** See you on {{ speaker.date }} — {{ instance.short_name }} webinar

Dear {{ speaker.first_name }},

Just a friendly reminder that your talk is coming up on **{{ speaker.when }}**.

**This is where it happens:**

{{ speaker.room }}

Please join about ten minutes early so we can do a quick final check of your
slides and your sound.

A couple of other things:

- The discussion has been warming up on the forum — {{ speaker.forum_thread }} — feel free to have a look.
- Let us know if you would like anything from our side.

We are very much looking forward to it!

Best regards,
{{ host_1.name }}

---

## Notes for the volunteer sending this

- **This is the message that carries the joining details, and the first one
  that does.** Nothing earlier gives them to the speaker: the promotion
  e-mail says they are coming, and says it three weeks out precisely so that
  nobody has to wonder in the meantime.
- **Not in the promotion e-mail, deliberately.** That one is written to be
  reposted — *"anything we post is yours to repost"* — and a room link in a
  message meant for reposting is a room anyone can walk into without
  registering. This series recognises attendance through registration and
  nothing else, so an audience that arrives by a shared link cannot be
  matched, cannot be certified, and is not covered by the data-protection
  record either. Send them the sign-up page; send the room only here.
- `{{ speaker.room }}` is the record's own meeting link, the series-wide
  joining instructions from `instance/data/config.yml`, or both — the same
  composition the registration confirmation uses, so the speaker and the
  audience are never told two different things. An instance whose account is
  one permanent room has the address in the configuration and nothing on the
  record; that is the ordinary case, not a gap.
