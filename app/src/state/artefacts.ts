/**
 * Where the thing a line asks somebody to confirm actually is.
 *
 * Several lines of the scheduled runbook ask an operator to have something
 * in hand -- the images and the drafted texts, the room link, the three
 * announcements whose templates this repository already fills in, and every
 * promotion channel's own post -- and the repository already knows where
 * each one is. It said none of it: *Visuals + flyer made* was a tick with
 * no path beside it, so confirming it meant knowing to open the Actions
 * tab, find the right run and download an artefact, and nothing anywhere
 * told anybody that. A ten-second confirmation became a search, which is
 * how a box gets ticked without the file being looked at.
 *
 * What this is not: a second telling of how the images are made. `docs/
 * handbook/toolkit/visual-kit.md` is that page, and the T-30 line hands it
 * over. What is here is the coordinates -- a workflow, an artefact name, a
 * filename under this event's own id -- because a path is state, which is
 * what a screen carries (`docs/engineering/content-rules.md` §2).
 *
 * Nothing here reaches the network. The images are not fetched, the run is
 * not looked up, and no claim is made that a particular run succeeded: what
 * a line can honestly say is *what the file is called and which workflow
 * writes it*, and -- for a record with no edition code yet -- that there is
 * no event id for it to be written under. `app/tests/state/artefacts.test.
 * ts` reads the workflow and the two commands and fails when a name here
 * stops matching one there.
 */
import type { Config, Speaker } from '../data/types';
import { repositoryUrl } from '../instance';
import { eventIdOf } from './agenda';
import { CHANNEL_ITEM_PREFIX } from './channels';
import { itemByKey, type RunbookItem } from './phases';

/** The workflow that renders a scheduled edition's images and texts. Its
 *  filename is its address on GitHub, so this one string is both. */
const WORKFLOW = 'visuals-production.yml';

/** What a record with no edition code is told, by every line whose files
 *  are named under an event id. The workflow renders scheduled editions and
 *  names each directory after the event id, which is the edition code
 *  lower-cased (D-19); a record without one has no directory in the
 *  download at all, and saying so is the honest answer -- the alternative
 *  is a path that resolves to nothing. */
const NO_EDITION =
  'This record has no edition code yet, so nothing is rendered for it — ' +
  'locking a date is what gives it one.';

/** The name that workflow uploads them under, in one artefact per run. */
const ARTEFACT = 'announcement-visuals';

/** How long GitHub keeps that artefact, from the workflow's own
 *  `retention-days`. Printed because a run older than this has nothing
 *  left to download, which is the one way the address below stops
 *  answering. */
const RETENTION_DAYS = 90;

/** Where the one format that is committed lands, from the same workflow's
 *  own "Sync and commit the share banner" step. */
const BANNER_DIR = 'site/src/banners/';

/** The images, from `tools/convener_ops/publication/formats.py::FORMATS`,
 *  each with what it is for. */
const IMAGES: readonly { file: string; what: string }[] = [
  { file: 'square.png', what: 'the announcement image, for the forum and the network post' },
  { file: 'print.png', what: 'the flyer, A4 at 300 dpi, for printing and putting up' },
  { file: 'banner.png', what: 'the link preview, also committed to the repository' },
];

/** The drafted texts, from `tools/convener_ops/cli/publication.py::
 *  render_announcements`, which writes one per channel for a scheduled
 *  edition. */
const TEXTS: readonly { file: string; what: string }[] = [
  { file: 'forum.md', what: 'the forum announcement' },
  { file: 'network.md', what: 'the professional-network post' },
  { file: 'mailing-list.md', what: 'the mailing-list and newsletter message' },
];

/** One thing a line asks for, and where it is. `href` is absent for a file
 *  inside a download nobody can address directly. */
export interface Located {
  what: string;
  where: string;
  href?: string;
}

/**
 * Where the things one line asks for are, or the sentence saying why there
 * is nothing to reach yet.
 *
 * `found` and `pending` are never both empty: a line this answers for
 * either has coordinates or has a reason it has none.
 *
 * `from` is the download the files inside it come out of, and is `null` for
 * anything already in hand. It carries the workflow's own address so that a
 * volunteer who has never opened the Actions tab has one link to follow
 * rather than a tab to learn.
 */
export interface Whereabouts {
  from: { label: string; href: string } | null;
  found: Located[];
  pending: string | null;
}

/** The workflow's own page on GitHub, where its runs and their artefacts
 *  are. The repository is the instance's, from its own declaration. */
export function visualsWorkflowUrl(): string {
  return `${repositoryUrl()}/actions/workflows/${WORKFLOW}`;
}

/** One file of the download, named under this event's own directory. */
function inDownload(eventId: string, file: string, what: string): Located {
  return { what, where: `${eventId}/${file}` };
}

/** The images and the drafted texts for this record. */
function visuals(speaker: Speaker): Whereabouts {
  const from = {
    label: `${ARTEFACT}, in Visuals production · kept ${RETENTION_DAYS} days`,
    href: visualsWorkflowUrl(),
  };
  if (!speaker.edition_code) return { from, found: [], pending: NO_EDITION };
  const eventId = eventIdOf(speaker.edition_code);
  return {
    from,
    found: [
      ...IMAGES.map(image => inDownload(eventId, image.file, image.what)),
      ...TEXTS.map(text => inDownload(eventId, text.file, text.what)),
      {
        what: 'the link preview again, committed rather than downloaded',
        where: `${BANNER_DIR}${eventId}.png`,
        href: `${repositoryUrl()}/blob/main/${BANNER_DIR}${eventId}.png`,
      },
    ],
    pending: null,
  };
}

/**
 * The room link and whatever else joining it takes.
 *
 * Both halves are already in this cockpit: the link is the record's own
 * `zoom_link` and the instructions are one value for the whole series in
 * the configuration, which is exactly the pair
 * `tools/convener_ops/journey/platform.py::ManualPlatform.get_room` reads
 * and hands to the confirmation e-mail. No token decides this and none ever
 * did -- D-06 means the account *is* the permanent room, so
 * `PlatformFCC.get_room` reads the same two sources rather than the API.
 * What decides it is whether the record carries a link.
 *
 * It goes no further than this screen. The room link reaches a registered
 * participant by e-mail and reaches no public page at all
 * (`docs/handbook/toolkit/emails/registration-confirmed.md`, and
 * `.github/workflows/publish-showcase.yml`'s own refusal to publish a build
 * carrying one).
 */
function room(speaker: Speaker, config: Config | null): Whereabouts {
  if (!speaker.zoom_link) {
    return {
      from: null,
      found: [],
      pending:
        'No room link is on this record yet. It is the record’s own zoom_link, ' +
        'set on this page under Admin override, and the confirmation e-mail ' +
        'sends whatever is there.',
    };
  }
  const instructions = config?.instructions ?? '';
  return {
    from: null,
    found: [
      {
        what: 'the room, as the confirmation e-mail gives it; it is on no public page',
        where: speaker.zoom_link,
        href: speaker.zoom_link,
      },
      ...(instructions === ''
        ? []
        : [{ what: 'joining it, for the whole series', where: instructions }]),
    ],
    pending: null,
  };
}

/** The line whose subject is the generated images and texts. */
const VISUALS_KEY = 'scheduled/T-30/visuals';

/**
 * The three lines that hand a volunteer a template the same run has already
 * filled in for this event.
 *
 * Each of them opens a page of `docs/handbook/toolkit/` to copy and
 * complete by hand, and `tools/convener_ops/publication/announce.py` renders
 * that very page from the record on every change to it. Nothing said so, so
 * the drafted text sat in a download nobody was told about while somebody
 * retyped it. `page` is the toolkit file both sides name, and
 * `app/tests/state/artefacts.test.ts` holds the three of them against the
 * runbook, the renderer and the command that writes them out.
 */
const DRAFTED: readonly { key: string; file: string; page: string }[] = [
  { key: 'scheduled/T-21/linkedin', file: 'network.md', page: 'linkedin-post' },
  {
    key: 'scheduled/T-21/mailing-list',
    file: 'mailing-list.md',
    page: 'mailing-list-announce',
  },
  {
    key: 'scheduled/T-7/forum-announce',
    file: 'forum.md',
    page: 'forum-post-announce',
  },
];

/** The line that asks the organiser to have the room link. */
const ROOM_KEY = 'scheduled/T-14/zoom-link';

/**
 * A promotion line posts one of the files the T-30 line already names, so
 * it points at that line rather than restating the list under all seven of
 * them: a block repeated on every row is a block a reader learns to skip.
 * The line is named by reading its own label, so a reword there cannot
 * leave this pointing at a heading nobody sees.
 */
function promotion(): Whereabouts {
  const named = itemByKey(VISUALS_KEY);
  return {
    from: null,
    found: [
      {
        what: `the image and the drafted text for this event, on “${named?.label ?? VISUALS_KEY}” above`,
        where: `in the ${ARTEFACT} download`,
      },
    ],
    pending: null,
  };
}

/**
 * The one drafted text this line's own template was rendered into.
 *
 * The images stay on the T-30 line: a volunteer publishing one post needs
 * the text for it and the picture beside it, and repeating all seven paths
 * under three more ticks is a block a reader learns to skip.
 */
function draftedText(speaker: Speaker, file: string): Whereabouts {
  const from = {
    label: `${ARTEFACT}, in Visuals production · kept ${RETENTION_DAYS} days`,
    href: visualsWorkflowUrl(),
  };
  if (!speaker.edition_code) return { from, found: [], pending: NO_EDITION };
  return {
    from,
    found: [
      {
        what: 'this page’s own template, already filled in from the record',
        where: `${eventIdOf(speaker.edition_code)}/${file}`,
      },
    ],
    pending: null,
  };
}

/**
 * Where this line's own artefact is, or `null` for a line that asks for
 * nothing anybody has to go and fetch.
 *
 * Keyed on the journey's own keys, which are the product's. A promotion
 * line's key is the instance's channel key with one prefix in front of it,
 * so it is matched on the prefix -- a series that announces its events in
 * seven places and one that announces them in two both reach the same
 * answer, and neither has to know what a poster is.
 */
export function whereabouts(
  item: RunbookItem,
  speaker: Speaker,
  config: Config | null,
): Whereabouts | null {
  if (item.key === VISUALS_KEY) return visuals(speaker);
  if (item.key === ROOM_KEY) return room(speaker, config);
  const drafted = DRAFTED.find(one => one.key === item.key);
  if (drafted !== undefined) return draftedText(speaker, drafted.file);
  if (item.key.startsWith(CHANNEL_ITEM_PREFIX)) return promotion();
  return null;
}

/** What the download is called, which workflow writes it and how long
 *  GitHub keeps it. Exported for `app/tests/state/artefacts.test.ts`, which
 *  reads the workflow itself and fails when a name here stops matching the
 *  one there. */
export const DOWNLOAD = {
  artefact: ARTEFACT,
  workflow: WORKFLOW,
  retentionDays: RETENTION_DAYS,
  bannerDir: BANNER_DIR,
  images: IMAGES.map(image => image.file),
  texts: TEXTS.map(text => text.file),
  drafted: DRAFTED,
} as const;
