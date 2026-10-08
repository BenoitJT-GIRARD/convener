# Architecture decisions

Why this system is shaped the way it is: twenty-nine decisions, each one a
short record of the decision itself, what was rejected, and what it costs.
Governance rules (who votes, what the bar is, what happens if nobody acts)
are documented separately in [the Board's rules](../../handbook/governance/board-rules.md)
— this index is about the software's own architecture, not who decides what
inside it.

A record's **status** is `Accepted` unless stated otherwise. A status can
change without touching any other record — that is the point of one file per
decision rather than one long register.

## Storing and protecting data

| Decision | Answers the question |
|---|---|
| [D-01 — The repository is the source of truth; no database](d-01-repository-of-record.md) | Why is there no database anywhere in this system? |
| [D-02 — Participant data: encrypted per event, key destroyed on schedule](d-02-participant-data-encryption.md) | How can registration data live in a git repository without being a standing privacy risk? |
| [D-22 — Destroying the key makes data unreadable; deleting the file does not](d-22-key-destruction-not-deletion.md) | What actually happens when a registration's retention period ends? |
| [D-23 — One independent envelope per record, and its byte boundaries matter](d-23-encrypted-record-envelope.md) | Why is each participant's data its own encrypted object instead of one file per event? |
| [D-24 — An operator command names a thing, never a person](d-24-operator-commands-name-things.md) | Why do administrative commands take a certificate ID instead of someone's email address? |

## Identity, access and writes

| Decision | Answers the question |
|---|---|
| [D-03 — Authentication: a GitHub App and the device flow](d-03-github-app-device-flow.md) | How does a volunteer sign in, and why not a personal access token? |
| [D-04 — Concurrent writes are handled explicitly](d-04-concurrent-writes.md) | What stops two people editing the same record from silently overwriting each other? |
| [D-19 — An event's identifier is its edition code, lower-cased](d-19-event-identifier.md) | Where does an event's ID come from, and why is there only one rule for it? |
| [D-28 — The architect owns the organisation; a Board member writes the repository](d-28-architect-and-board-permissions.md) | Who actually holds GitHub access, and how does it change hands? |

## The meeting platform and registration

| Decision | Answers the question |
|---|---|
| [D-05 — The meeting platform sits behind an interface](d-05-meeting-platform-abstraction.md) | Why isn't the video-conferencing vendor called directly from application code? |
| [D-06 — Registration belongs to the organisation; the meeting vendor supplies only the room](d-06-registration-ownership.md) | Why does the organisation run its own registration form instead of using the meeting vendor's? |

## Communication

| Decision | Answers the question |
|---|---|
| [D-07 — Two separate email channels, for two separate needs](d-07-email-channels.md) | How does outbound email actually get sent, and why through a personal-looking mailbox? |
| [D-09 — LinkedIn publication stays manual](d-09-no-linkedin-automation.md) | Why doesn't the system post to LinkedIn automatically? |
| [D-10 — The video channel belongs to the organisation](d-10-youtube-channel-ownership.md) | Who owns the account recordings are published to? |
| [D-12 — No automatic transcription or summarisation](d-12-no-automatic-transcription.md) | Why is there no auto-generated session summary? |

## Visual identity and the public surface

| Decision | Answers the question |
|---|---|
| [D-08 — Announcement visuals are generated, not hand-drawn](d-08-visuals-generated-in-ci.md) | Why are flyers and announcement images generated instead of designed by hand each time? |
| [D-15 — A private instance, a public product](d-15-publication-topology.md) | Which repositories are there, which of them are public, and what may a public one hold? |
| [D-16 — The visual identity has one source of fact, and it is the original artwork](d-16-brand-source-of-truth.md) | Where do the organisation's colours and type actually come from? |
| [D-17 — Typography: one free, self-hosted family in place of two licensed ones](d-17-typography-substitution.md) | Why does the site use a different typeface from the original design? |
| [D-18 — Static public pages, interactivity in islands](d-18-static-pages-with-islands.md) | Why is the showcase a static site rather than part of the application? |

## Configuration and the language boundary

| Decision | Answers the question |
|---|---|
| [D-11 — Every account belongs to the organisation, held in a shared vault](d-11-organisation-accounts-and-vault.md) | Whose name is on the organisation's external accounts? |
| [D-13 — Every integration is optional, and absence is a normal state](d-13-deferred-configuration.md) | What happens when an external account hasn't been set up yet? |
| [D-14 — The boundary between the two languages is the schema, not the rule](d-14-language-boundary.md) | Why does this project use both Python and TypeScript, and how do the two stay in step? |

## Certificates

| Decision | Answers the question |
|---|---|
| [D-20 — A certificate transports the exact bytes it signs](d-20-certificate-wire-format.md) | How does a certificate's signature actually get verified? |
| [D-21 — A certificate's lifecycle](d-21-certificate-lifecycle.md) | What happens when a certificate needs to be corrected? |

## The licence and the name

| Decision | Answers the question |
|---|---|
| [D-29 — The licence is the AGPL; the name is not licensed at all](d-29-licence-and-attribution.md) | What may somebody else do with this software, and what may they not call the result? |

## Verification discipline

| Decision | Answers the question |
|---|---|
| [D-25 — A control that cannot fail loudly is not a control](d-25-loud-failure.md) | Why does every automated check in this project carry a test for its own failure mode? |
| [D-26 — Verify the shape that will actually be deployed, never a convenient local one](d-26-verify-deployed-shape.md) | Why can't a build be verified by opening it from a local folder? |
| [D-27 — A comparison against a reference only means something if the engine that produced it is pinned](d-27-pin-the-render-engine.md) | Why is a full browser download pinned into one CI job just to compare two images? |
