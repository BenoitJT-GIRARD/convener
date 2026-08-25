# LinkedIn post — Announce

*Published around T-4 weeks.*

**The app writes the post; a person publishes it.** Open the event in the workspace and this template comes back filled in from the record — name, affiliation, title, date, time, forum thread — ready to copy. What the app never does is post it. There is no LinkedIn robot behind this page and none is planned: publishing through LinkedIn's own interface would mean an application review and a page administration token to look after, which is a great deal of standing setup for a task two volunteers a month already do in a minute. So the last step is yours — read it, paste it, post it.

One thing is not filled in for you, on purpose: the sentence saying why this talk is worth an hour of somebody's Thursday. Nothing in the record holds that sentence, and a generated stand-in for it would be obvious to every reader. The registration link, by contrast, *is* filled in for you — computed from the event's own `edition_code`, never typed by hand — and it is the signup page's near-namesake, not the room's: the room's own permanent link never otherwise leaves the confirmation e-mail (see [Registration confirmed](emails/registration-confirmed.md)).

---

🔬 Next in the **{{ instance.organisation }} {{ instance.series }}**!

We are hosting **{{ speaker.name }}** ({{ speaker.affiliation }}) for a talk on:

**{{ speaker.title }}**

🗓 {{ speaker.when }} · 💻 Online, free — registration required

[One line, in your own words, on why this talk matters. Written by hand — the record holds no such sentence.]

Register here 👉 {{ speaker.signup_link }}
Join the discussion on {{ instance.organisation }} 👉 {{ speaker.forum_thread? }}

\#BehaviouralScience #Neuroscience #Webinar #OpenScience

---

## Notes for the volunteer posting this

- {{ speaker.forum_thread! }}No forum thread link is included above: none has been opened yet, so open one and add its link before you post.
