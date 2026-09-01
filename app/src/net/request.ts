/**
 * The one door out of the operators' cockpit.
 *
 * Demo mode lets a visitor drive this application with no GitHub account:
 * the state lives in memory, an edit is applied there, and nothing is
 * written anywhere. That promise was true by coincidence rather than by
 * construction -- each module that reached a remote host happened to sit
 * behind a guard written somewhere else, and a module added next month
 * would sit behind none. The failure would have been silent in the worst
 * possible way: a demonstration quietly talking to GitHub, or quietly
 * writing to it.
 *
 * So every outbound request the cockpit makes goes through `request()`
 * below, and `app/tests/net/demo-network.test.tsx` holds that by sweeping the
 * module graph reachable from `src/main.tsx` and refusing a request
 * primitive found anywhere else. The existing guards in `DataContext`,
 * `AuthContext` and `useRole` are untouched and still do the useful work
 * -- they stop the call from being made at all, which is better than
 * refusing it once made. This module is what happens when somebody
 * forgets one.
 *
 * What "reaches no network" honestly means here
 * ---------------------------------------------
 * Not "makes no request". In demo mode the cockpit still reads its own
 * handbook: `content/fetch.ts` loads the markdown pages that ship inside
 * the build, from the address that served the page. Those reads are part
 * of the document, carry no credential and can change nothing. The rule
 * worth holding, and the one enforced below, is
 *
 *     in demo mode this cockpit reads only from the origin that served
 *     it, and writes nothing at all,
 *
 * so a request to any other origin is refused whatever it is for, and a
 * method other than GET or HEAD is refused even to our own origin.
 *
 * The islands under `src/islands/` are built as separate bundles from
 * their own entry points, run on the public site, and have no demo mode
 * to respect. They are outside the graph the sweep walks, and they are
 * outside it because the graph says so -- not because anybody listed
 * them as exceptions.
 */
import { isDemoMode } from '../data/demo';

/** Refusal by the rule above. A distinct class rather than a bare `Error`
 *  so a caller that means to tolerate it can, and so the message that
 *  reaches a console names demo mode as the reason instead of looking
 *  like a network failure. */
export class DemoModeRefused extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DemoModeRefused';
  }
}

/** The methods a static host answers without anything changing. Anything
 *  else is a write as far as this rule is concerned, including the ones
 *  that would merely 405 against GitHub Pages: whether a particular host
 *  happens to refuse it is not the property being held. */
const READ_METHODS = new Set(['GET', 'HEAD']);

/**
 * Why demo mode refuses this request, or `null` if it does not.
 *
 * Pure, and takes the document's own address as an argument rather than
 * reading `location`, so the decision can be exercised for addresses no
 * test environment could be served from.
 */
export function demoRefusal(address: string, method: string, here: string): string | null {
  let origin: string;
  let target: URL;
  try {
    origin = new URL(here).origin;
    target = new URL(address, here);
  } catch {
    return `demo mode refused a request to an address it could not read: ${address}`;
  }

  if (target.origin !== origin) {
    return (
      `demo mode refused a request to ${target.origin}: a demonstration reads ` +
      `only from ${origin}, the address that served it.`
    );
  }

  const verb = method.toUpperCase();
  if (!READ_METHODS.has(verb)) {
    return (
      `demo mode refused a ${verb} to ${target.pathname}: a demonstration ` +
      `changes nothing outside the browser it runs in.`
    );
  }

  return null;
}

/**
 * Make a request.
 *
 * Outside demo mode this is the platform primitive and nothing else --
 * no retry, no base URL, no header of its own. Adding behaviour here
 * would make this module something callers have opinions about, and the
 * reason it exists is that they should have none.
 */
export async function request(address: string, init: RequestInit = {}): Promise<Response> {
  if (isDemoMode()) {
    // `isDemoMode()` is false when there is no `window` at all, so
    // reading `location` inside this branch is safe.
    const refusal = demoRefusal(address, init.method ?? 'GET', window.location.href);
    if (refusal !== null) throw new DemoModeRefused(refusal);
  }
  return fetch(address, init);
}
