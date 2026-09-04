/**
 * Where the demonstration's own edits live, and how long they live for.
 *
 * A visitor proposes a speaker, votes it through, sends the invitation --
 * and then reloads the page, or opens the cockpit again from the showcase
 * they came from, and every one of those acts is gone. Measured, and the
 * maintainer's own words for it: *it does not look very serious.* The
 * records were held in one React component's state, so they lasted exactly
 * as long as the document did.
 *
 * **The session, and deliberately not longer.** `sessionStorage` is scoped
 * to the tab: it survives a reload, a link followed out to the showcase
 * and back, and the whole of one person's visit, and it is gone when that
 * tab is closed. `localStorage` would survive the browser being shut down
 * and reopened next week, and a demonstration that still holds your edits
 * a week later invites exactly the question this one must never raise --
 * *where is this being kept, and who can read it?* The answer here is: in
 * this tab, until you close it. Nothing is sent anywhere;
 * `src/net/request.ts` refuses every write a demonstration could attempt,
 * and there is no repository to attempt one against.
 *
 * **The store is the document.** What is written is the two files a
 * repository holds -- `speakers.yml` and `config.yml`, serialised by
 * `./yaml.ts`, the very writer a real edit goes through -- and what is
 * read back goes through the very reader a real load goes through. So a
 * blob left behind by an older build, or one somebody has edited by hand
 * in a developer console, fails exactly the way a malformed file fails,
 * and this falls back to the example instance rather than rendering half
 * of it. Storing the parsed objects would have made this module a second
 * definition of the model.
 *
 * Every access is wrapped: a browser in private mode, or one configured to
 * refuse site data, throws on the first `sessionStorage` touch rather than
 * returning null. A demonstration that cannot remember is still a
 * demonstration; one that throws on startup is not.
 */
import {
  parseConfig,
  parseSpeakers,
  serializeConfig,
  serializeSpeakers,
} from './yaml';
import type { Config, Speaker } from './types';

/**
 * The one key, and the reason it carries a number.
 *
 * A blob written by a build whose model has since changed would be read
 * back by `parseSpeakers`, which refuses what no longer matches -- and
 * that refusal is silent here by design (the example is shown instead).
 * The number is what lets a change that *must* discard the old shape say
 * so: raise it, and every tab still holding the old one starts again from
 * the example rather than being quietly emptied.
 */
const KEY = 'convener.demo.session.v1';

interface Stored {
  speakers: string;
  config: string;
}

/** The demonstration's records as this tab has them, or `null` when this
 *  tab has none -- or holds something no longer readable. */
export function readDemoSession(): { speakers: Speaker[]; config: Config } | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const stored = JSON.parse(raw) as Stored;
    return {
      speakers: parseSpeakers(stored.speakers),
      config: parseConfig(stored.config),
    };
  } catch {
    // Unreadable for any reason -- storage refused, JSON malformed, a
    // record that no longer matches the model. The example instance is
    // the answer to all three, and it is the answer this module was
    // written to fall back to.
    return null;
  }
}

/** Keep this tab's demonstration, as the two documents a repository would
 *  hold. */
export function writeDemoSession(speakers: Speaker[], config: Config | null): void {
  if (!config) return;
  try {
    const stored: Stored = {
      speakers: serializeSpeakers(speakers),
      config: serializeConfig(config),
    };
    sessionStorage.setItem(KEY, JSON.stringify(stored));
  } catch {
    /* A demonstration that cannot remember is still a demonstration. */
  }
}

/** Forget it. Called when somebody leaves the demonstration and when they
 *  ask for the example's own records back. */
export function forgetDemoSession(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
