# Visual kit

Every event needs an announcement image and a flyer. **The source files are in
this repository.** Download one, open it in whatever tool you already use, on
your own account, and export the image yourself. Nobody has to unlock anything
for you, and nobody is waiting on you either.

This is deliberate. The templates used to live inside one person's account on a
design tool: whoever held that account was the only one who could change a date,
and everyone else queued behind them. A file in the repository has no owner to
wait for.

## The files

| File | Format | What it is |
| --- | --- | --- |
| [Announcement image](../assets/announcement-template.svg) | SVG, 1200 × 1200 | Square image for the forum post and the LinkedIn post |
| [Flyer](../assets/flyer-template.svg) | SVG, A4 portrait | For printing, and for attaching to an invitation email |
| [Video-call background](../assets/zoom-background.png) | PNG, 1920 × 1080 | What the hosts put behind them during the session — see [Hosting](../workflow/3-hosting.md) |
| Finished example | — | No example is published here. The one that used to fill this row was a past speaker's own photograph and name, kept without a separate, later consent to use them as a sample — so it has been withdrawn from this kit rather than shipped on the strength of the original invitation alone. Fill in a template yourself and delete this row once you have made one you are happy to show. |

SVG and PNG only. Both open in free software, on any machine, with no account
and no licence — which is the whole point: a template you can only edit inside
one company's website is the same problem in a different building.

## Opening one

Any of these works, and none of them costs anything:

- **[Inkscape](https://inkscape.org)** — free, installs on Windows, macOS and
  Linux, works offline. The safe default if you have no preference.
- **Figma, Illustrator, Affinity Designer** — if you already have one open, it
  will import the SVG happily.
- **A text editor** — an SVG is text. Open it, change the words between the
  tags, and view the result by dragging the file into a browser. This is the
  fastest way to fix a typo.

## What to change, and what not to

Each file has two groups. Everything in `id="variable"` is yours to edit for
this event; everything in `id="fixed"` is the series identity — the wordmark,
the turquoise and cream bands, the decorative loops, the *what to expect*
block — and stays as it is, so two events in a row look like the same series.

The variable parts are written as the same placeholders the message templates
use, so you can copy the values straight out of the event page in the app:

- `{{speaker.title}}` — the talk title
- `{{speaker.date}}` and `{{speaker.time}}` — written out the way you would say
  them aloud, with the time zone
- `{{speaker.name}}` and `{{speaker.affiliation}}` — under the photo
- `{{speaker.edition_code}}` — on the flyer only

Two things are placeholders you replace with an image rather than with words:
the **speaker photo** (a grey square in a tilted white frame — import the photo
and send it behind the frame) and the **QR code** for the registration link
(a dashed square — generate the code from the registration link and drop it on
top). Neither blocks you: left as they are, they read as unfinished rather than
as broken.

SVG does not wrap text. A long title has to be split across the lines already
there, by hand — the second and third lines are empty and waiting.

## Fonts

The series uses **Archivo**, which is free under the SIL Open Font Licence and
downloadable from Google Fonts. Install it and the export matches the app
exactly. If it is not installed, the templates fall back to Segoe UI or Arial:
the layout still holds, the letterforms are simply not ours.

## Exporting

- **Announcement image** — export to PNG at 1200 × 1200. That is the size the
  forum and LinkedIn want.
- **Flyer** — export to PDF for printing, or to PNG at 300 dpi to attach to an
  email.

Export a copy; **do not overwrite the template**. The file in the repository is
the one the next person starts from.

## When you need each one

- **Announcement image** — when promotion starts, three weeks before the event:
  it goes on the [forum announcement](forum-post-announce.md) and the
  [LinkedIn post](linkedin-post.md).
- **Flyer** — alongside the announcement, and attached to the
  [invitation](emails/invitation.md) if a lab asks for something to circulate.
- **Video-call background** — applied by both hosts at the technical check,
  fifteen minutes before the session starts.

## A note on where this is going

The plan of record is for the announcement image and the flyer to be
**generated from the event's own data**, so that a changed date or a changed
registration link means a regenerated image rather than an evening of manual
work. This kit is the fallback that keeps working whatever happens to that:
whoever prefers to work by hand takes these files and owns the result.
