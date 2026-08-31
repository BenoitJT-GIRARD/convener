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
| [Video-call background](../assets/video-call-background.svg) | SVG, 1920 × 1080 | What the hosts put behind them during the session — see [Hosting](../workflow/3-hosting.md). Nothing to fill in; export it and use it |
| Finished example | — | No example is published here. The one that used to fill this row was a past speaker's own photograph and name, kept without a separate, later consent to use them as a sample — so it has been withdrawn from this kit rather than shipped on the strength of the original invitation alone. Fill in a template yourself and delete this row once you have made one you are happy to show. |

SVG only, and it opens in free software on any machine, with no account and no
licence — which is the whole point: a template you can only edit inside one
company's website is the same problem in a different building.

The background used to be a PNG somebody drew by hand. It said
`THE PLACE TO DISCUSS ANIMAL BEHAVIOUR`, which is not what this series says
about itself anywhere else, and its QR code pointed at a single forum thread
for one 2024 event. Nothing could see either problem: no check in this
repository can read a word inside an image. It is generated from the same two
files the templates are now, so what it says is what the declaration says.

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

The two templates have two groups. Everything in `id="variable"` is yours to
edit for this event; everything in `id="fixed"` is the series identity — the wordmark,
the coloured field and its cream bands, the ribbon, the *what to
expect* block — and stays as it is, so two events in a row look like the same
series.

**Your downloaded copy is yours: change anything in it.** What the paragraph
above is about is the file *in the repository*, and that one is not edited by
hand at all any more. It is generated from the visual identity
(`instance/data/brand.json`) and from this series' own declaration
(`instance/config.json`), so every colour in it is the charter's and every name
in it is this series'. To change one, change one of those two files and run
`uv run python scripts/generate_brand_css.py` from `tools/`; the same
command's `--check` fails the build if a template stops agreeing with them.

That is also how they stopped carrying a palette nobody had chosen. Both files
had drifted onto colours the project measured and rejected in 2026 — including
one line set in the page's own background colour, and therefore invisible in
every poster anybody ever downloaded.

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
- **Video-call background** — export to PNG at 1920 × 1080. Video-call
  applications take a bitmap, never an SVG, so this export is not optional —
  but it is the whole job here, because there is nothing to fill in first. Any
  of the tools above does it in one step: in Inkscape, *File > Export*, width
  1920, *Export As…*. Do it once and keep the PNG; it only changes when the
  series' own name, strapline or address does.

**Why the background is not shipped as a PNG as well.** It would have to be
rendered by a machine, and two machines do not render text identically —
hinting and anti-aliasing differ. A committed PNG could then only be checked
loosely, or checked strictly and fail on somebody else's laptop for a reason
that is not a mistake; and either way nothing in this repository could read
what it said. The SVG is checked exactly, character for character, against
`instance/data/brand.json` and `instance/config.json`. The cost of that is this one
export, and it is a cost worth naming rather than hiding.

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

The direction of travel is for the announcement image and the flyer to be
**generated from the event's own data**, so that a changed date or a changed
registration link means a regenerated image rather than an evening of manual
work. This kit is the fallback that keeps working whatever happens to that:
whoever prefers to work by hand takes these files and owns the result.
