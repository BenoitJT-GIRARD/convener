# Contacts

Who you write to, and how. The short version is that it is the team, and only the team.

## No outside contact is in the loop any more

Running a webinar used to depend on two people who were not volunteers of the series: one opened a meeting room on a university account, another put the recording on a channel that belonged to somebody else. Both were generous about it, and neither should have been asked. A series that cannot hold its session because a colleague is on leave, and cannot find its own recordings because they live under another name, is a series that does not control the two things it exists to produce.

So both dependencies were removed rather than documented better. What used to be a favour is now an account the organisation holds:

| It used to be | It is now |
|---|---|
| Asking a contact at another institute to open the meeting room and start the recording | A meeting platform the organisation holds itself, with a manual fallback for the day nothing else works — see `docs/operating/operations.md` ("Meeting platform") |
| Sending the recording to someone else's channel to be uploaded | A video channel on the organisation's own account, which is also what makes the Board's publication gate real — see `docs/operating/operations.md` ("Video channel") |

Neither of those pages names a person, and that is the point: they name a credential the Board can hand on. If you find a page that still tells you to email somebody outside the team, that page is out of date — fix it, and say so in the thread.

## Reaching the Editorial Board

There is no Board mailbox to write to, and that is a choice rather than an omission: a shared address is one more account to hold, to watch, and to lose. The Board is reached through this repository instead.

- **For anything about one speaker or one session** — say it on that record, in the workspace. It is where whoever picks the question up will already be looking.
- **For anything else** — open an issue here, or comment on the standing *Board notifications* thread, and mention the editorial-board team. GitHub sends the email; that is the whole mechanism, and it is the same path the nightly digest takes.

Address the team, never one volunteer. The channel has to keep working on the day any one person stops reading their notifications, and a message addressed to a name does not. Which thread and which team handle are set up once, per repository, and written down in `docs/operating/operations.md` ("Board notifications").

If you are not on GitHub, ask any volunteer to open it for you. Nothing here requires that the person with the question is the person who types it.

## The organising team

The series is run by its Editorial Board; between them, its members hold the accounts described above.

**Who sits on it is not kept on this page** — not the Board of today, and not the one that started the series. It is the `board` list in `instance/data/config.yml`, and the Board screen in the workspace shows it. A list of names typed here would be a second answer to that question, and a second answer is one that is eventually wrong — quietly, and in the place a newcomer happens to read first.

Two rules, one reason. The one above is about whom a message is addressed to; this one is about where a fact is kept. Neither makes an exception for the names that feel permanent, and a founding board is the clearest case there is: it is the list that looks safest to type, and the one nobody ever comes back to check.

If that list is in a temporary state — an identifier that is not yet a GitHub login, a seat declared and not filled — the file itself is the only thing that says so, and `convener-validate` is what reports it. What such a state costs while it stands, and the change that ends it, are in `docs/operating/operations.md` ("Deferred governance configuration").

What each of the four roles does is in [Roles](roles.md); what the Board itself is for is in [The Editorial Board](governance/editorial-board.md).
