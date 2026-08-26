/**
 * Demo mode: the flag that turns it on, and the instance it shows.
 *
 * A visitor with no GitHub account drives the whole cockpit: the state
 * lives in memory, an edit is applied there, and nothing is written
 * anywhere (`net/request.ts` is where that is held, and
 * `tests/demo-network.test.tsx` is what holds it).
 *
 * What it shows is `instances/example/` -- a whole second instance,
 * invented, that the product already ships and that
 * `tools/tests/test_second_instance.py` already lays into this
 * repository's own holes on every run to prove the instance is separable
 * from the code.
 * This module used to hold five speaker records and a governance
 * configuration of its own invention instead, and two of that invention's
 * strings named *this* organisation's forum and its LinkedIn page: an
 * instance written in code, compiled into the cockpit, shipped by every
 * duplicate. Consuming the example rather than inventing a third set of
 * fictional data is what closes that -- and it buys the states the
 * invention never had (a delivered edition whose speaker refused
 * publication, a confirmed record still choosing between dates, a title in
 * a script other than Latin), because the example was chosen to exercise
 * states rather than to be plausible.
 *
 * Parsed by `./yaml.ts`, the reader every real `data/speakers.yml` goes
 * through, so what the demonstration renders is the example instance read
 * exactly the way a repository's own data is read. An example that stopped
 * matching the model stops the demonstration by name rather than rendering
 * half of it.
 *
 * Lazily, and once. Everything in this bundle reaches this module --
 * `net/request.ts` imports the flag, and every module that makes a request
 * imports `net/request.ts` -- so parsing at module scope would parse nine
 * kilobytes of YAML on every start of the cockpit, in the ordinary case
 * where demo mode is off and nothing here is ever read.
 */
import { parseConfig, parseSpeakers } from './yaml';
import type { Config, Speaker } from './types';

const FLAG = 'convener.demo';

export function isDemoMode(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const url = new URL(window.location.href);
    if (url.searchParams.get('demo') === '1' || window.location.hash.includes('demo=1')) {
      localStorage.setItem(FLAG, '1');
      return true;
    }
    return localStorage.getItem(FLAG) === '1';
  } catch {
    return false;
  }
}
export function activateDemoMode(): void {
  try {
    localStorage.setItem(FLAG, '1');
  } catch {
    /* ignore */
  }
}
export function exitDemoMode(): void {
  try {
    localStorage.removeItem(FLAG);
    // Not this product's key: the historical one an earlier build of the
    // instance running this repository wrote, kept for exactly as long as
    // a browser somewhere may still hold it -- see `LEGACY_KEY` in
    // `auth/AuthContext.tsx`, which reads and deletes it on startup.
    localStorage.removeItem('convener.token');
  } catch {
    /* ignore */
  }
}

/**
 * Who the visitor is while they drive the demonstration.
 *
 * A member of the example instance's own board, not a login of this
 * module's invention. Half of what the cockpit does is keyed on who you
 * are -- a ballot counts only from an active member (`state/governance.ts`
 * ::decide), `applyTransition` refuses a login the board does not hold,
 * the inbox is what is waiting for *you* -- so a visitor signed in as
 * somebody the board has never heard of would be shown a cockpit in which
 * none of that works, and would be shown it silently.
 *
 * `example-alba` in particular because she has a hand in every record the
 * example holds: a ballot on each vote (including a recusal with its
 * reason), two leads of her own, an assignment and two hosting slots. No
 * screen renders empty for her, which is the whole point of a
 * demonstration. `tests/demo-instance.test.ts` refuses a login that is not
 * on that board.
 */
export const DEMO_USER = { login: 'example-alba' };

/** The example instance's own two data files, as text, exactly as
 *  `vite.config.ts`'s own `define` put them into this bundle
 *  (`scripts/example-instance.mjs` is what read them). */
interface ExampleInstance {
  config: string;
  speakers: string;
}

function exampleInstance(): ExampleInstance {
  const raw = import.meta.env.VITE_EXAMPLE_INSTANCE as string | undefined;
  if (!raw) {
    throw new Error(
      'VITE_EXAMPLE_INSTANCE is unset: this bundle was built without ' +
        "vite.config.ts's own define, so demo mode has no instance to show " +
        '(see instances/example/)',
    );
  }
  return JSON.parse(raw) as ExampleInstance;
}

let config: Config | null = null;
let speakers: Speaker[] | null = null;

/** The example instance's governance configuration -- its board, its
 *  thresholds and the channels it announces an event through. */
export function demoConfig(): Config {
  config ??= parseConfig(exampleInstance().config);
  return config;
}

/** The example instance's own five records. */
export function demoSpeakers(): Speaker[] {
  speakers ??= parseSpeakers(exampleInstance().speakers);
  return speakers;
}
