# Mailing list / newsletter message — Announce

*For the TEATIME mailing list, an institute's own newsletter or internal
messaging, and the RISC newsletter — the plain-text channels reaching people
who did not ask about this particular talk. Sent around T-14, alongside the
LinkedIn post. Whoever edits an institute's newsletter or sends to a list
does not need workspace access: send them this message once it is filled in,
or paste it into whatever they ask for.*

---

**Subject:** The Example Collective — {{ speaker.title }}

Hello,

The Example Collective's next virtual seminar is {{ speaker.when }}, online and
free to attend.

{{ speaker.name }} ({{ speaker.affiliation }}) will present:

"{{ speaker.title }}"

{{ speaker.abstract }}

Register here: {{ speaker.signup_link }}

Questions can be posted ahead of time on the forum thread: {{ speaker.forum_thread? }}

The Example Collective is a virtual seminar series in behavioural science, held
roughly monthly and open to anyone. Past talks and recordings are at
forum.example.test.

Best regards,
The Example Collective team

---

## Notes for the volunteer sending this

- This is plain text on purpose: most of the places it goes strip
  formatting, or the person forwarding it will paste it into their own
  template. Keep it that way rather than adding markup back in.
- The registration link above is the event's own page, computed from its
  edition code — never type an address in by hand, and never send the
  meeting room link here. The room link only ever reaches a participant
  through the confirmation e-mail (see
  [Registration confirmed](emails/registration-confirmed.md)).
- {{ speaker.forum_thread! }}No forum thread link is included above: none has been opened yet, so open one and add its link before you send this.
