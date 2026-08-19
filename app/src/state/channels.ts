/**
 * Where an event gets announced.
 *
 * The application knew about two places -- a LinkedIn post and a forum
 * announcement -- and the checklist the volunteers actually keep runs to
 * seven: the The Example Collective forum, the TEC LinkedIn page, personal
 * LinkedIn accounts, the TEATIME mailing list, institute newsletters and
 * internal messaging, the RISC newsletter, and printed posters in the
 * institutes.
 *
 * **They are configuration, not a constant.** Whether those are still the
 * right seven cannot be confirmed without asking the collaborators, and
 * nothing in this project may depend on a collaborator's goodwill or
 * availability. So rather than freeze a list nobody here can verify, the list
 * became data: it lives in `data/config.yml`, and a channel is added,
 * renamed or dropped without a line of TypeScript changing. The question
 * stops needing an answer.
 *
 * **`channelsOf` is the only way to reach the list.** No caller rebuilds it,
 * no constant restates it, and there is no default seven anywhere in this
 * repository to fall back on. That is what makes the configuration real
 * rather than decorative: phase 3 already found Python's classification sets
 * bypassed by a hand-written `if`, which left the sets standing as
 * documentation of a rule the code no longer followed.
 *
 * **A list that cannot be read is refused, never silently emptied.**
 * `data/validate.ts` stops the load of a `config.yml` whose `channels` is
 * absent, is not a list, or holds an entry this app cannot read, and names
 * the file, the field and the position; `channelsOf` makes the same refusal
 * for a config that never went through that reader. An *explicitly* empty
 * list is a different fact and is legal: it means nothing is promoted
 * through this app, which is the "absent configuration does nothing" side of
 * the standing pattern rather than the "acts on everything" side. What must
 * not happen is the third case -- a broken list read as an empty one -- which
 * would show a volunteer a promotion phase with no lines in it and no
 * indication that the file, not the plan, is what is missing.
 *
 * Pure: no clock, no state, no reading of `data/` beyond the config handed in.
 */
import { DataShapeError } from '../data/validate';
import type { Channel, Config } from '../data/types';
import type { RunbookItem } from './phases';

/** The one prefix a channel's journey key carries.
 *
 *  It names what the line is about and not when it is done: where the
 *  promotion phase sits in the calendar is a placement decision, and a key
 *  that encoded it would have to be rewritten -- on every stored record --
 *  the day the placement moved. */
const CHANNEL_ITEM_PREFIX = 'promotion/';

/**
 * The channels, read from the config and from nowhere else.
 *
 * Returns a fresh array, so a caller that sorts or splices it cannot reach
 * back into the loaded config.
 *
 * Throws `DataShapeError` for a config whose `channels` is missing or is not
 * a list. That is unreachable through the app's own read path --
 * `data/validate.ts` has already refused such a file, with a better message,
 * before any screen renders -- and it is here for the caller that builds a
 * `Config` some other way: the alternative is returning `[]`, which spells a
 * broken file exactly as it spells a deliberate decision to promote nowhere.
 */
export function channelsOf(config: Config): Channel[] {
  const listed: unknown = (config as { channels?: unknown }).channels;
  if (!Array.isArray(listed)) {
    throw new DataShapeError(
      'data/config.yml: "channels" should be the list of places an event is ' +
        'announced, and this app cannot read it as one. Someone with access ' +
        'to the repository will need to correct it on GitHub.',
    );
  }
  return (listed as readonly Channel[]).map(channel => ({
    key: channel.key,
    label: channel.label,
  }));
}

/**
 * One channel as a line of the journey.
 *
 * A channel is a journey item like any other and needs nothing special: it
 * is a checkbox, its owner is written in `Speaker.checklist` under this key
 * through `state/assignment.ts`, and `isItemDone` reads its tick out of
 * `runbook_progress` exactly as it does for every other checkbox.
 *
 * The label is the channel's own, verbatim. Wrapping it in a sentence
 * written here would put back in TypeScript the one thing this task moved
 * out of it: the words a volunteer reads would stop being editable in the
 * file.
 *
 * The `window` is not the channel's: when the promotion lines fall relative
 * to the event is where the phase places them, so it is `phaseItems` that
 * reads it off the placement and hands it in here. It is carried on the item
 * all the same, rather than worked out again by each screen, because two
 * screens that each derive it are two screens that can disagree -- and did:
 * the record page showed `Forum announcement`, always ticked-able, while the
 * inbox said `Forum announcement (T-14)` and withheld it until T-14.
 */
export function channelItem(channel: Channel, window?: number): RunbookItem {
  return {
    key: `${CHANNEL_ITEM_PREFIX}${channel.key}`,
    form: 'checkbox',
    label: channel.label,
    ...(window === undefined ? {} : { window }),
  };
}
