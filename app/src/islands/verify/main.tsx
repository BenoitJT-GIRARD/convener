import { StrictMode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { VerifyPage } from './VerifyPage';

/**
 * Bootstraps the verification island onto whatever the built verify page
 * provides -- `site/src/verify.njk`'s own `#verify-app` element.
 *
 * Unlike `islands/signup/main.tsx`, this island reads nothing off the
 * mount element itself: `site/src/verify.njk` is one static page for
 * every certificate ever issued, not one page per event the way
 * `event.njk` is (D-19 gives registration and the survey one page per
 * event; a certificate names no event this page could key a per-page
 * address off). What varies between visits is the URL's own fragment, so
 * this file reads that instead -- the replacement for the
 * `react-router-dom` `HashRouter` route (`/verify/:identifier`,
 * `?token=…`) `App.tsx` used to parse this same shape with. `MOUNT_ID` is
 * the exact id `site/src/verify.njk` reserves.
 */
export const MOUNT_ID = 'verify-app';

function safeDecodeURIComponent(value: string): string {
  // A hand-edited or truncated fragment can carry a lone `%` that is not
  // the start of a real percent-encoding -- `decodeURIComponent` throws
  // `URIError` on that rather than returning best-effort text. Falling
  // back to the raw segment keeps this a parsing step, never a page
  // crash: whatever comes out still reaches `VerifyPage`, which already
  // has to handle an identifier that is not shaped like one of ours
  // (`InvalidIdentifierShape`) or a token whose signature does not verify
  // (`NotVerifiable`) -- garbled input is exactly the same shape of
  // "cannot confirm this" either way.
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

/**
 * Pulls `identifier` and `token` out of a URL fragment, the same shape
 * `certificate.verification_url` builds: `#/<identifier>?token=<token>`.
 * Takes the fragment as a plain string -- `location.hash` when called from
 * this file's own bootstrap below -- rather than reading `window.location`
 * itself, so a test can exercise every shape of input directly, with no
 * `window.location` stubbing at all.
 *
 * Both `#` and the leading `/` are optional on the way in: a caller may
 * pass `location.hash` verbatim (which always includes the `#` once a
 * fragment exists) or an already-stripped fragment. An identifier segment
 * is decoded but never validated here -- `VerifyPage` -> `register.ts`'s
 * own `isValidIdentifierShape` is where a malformed identifier is turned
 * into an honest "not a certificate identifier" answer, not this function,
 * which only ever describes what the URL said, never what it means.
 */
export function parseVerificationFragment(hash: string): { identifier?: string; token?: string } {
  const withoutHash = hash.startsWith('#') ? hash.slice(1) : hash;
  const withoutSlash = withoutHash.startsWith('/') ? withoutHash.slice(1) : withoutHash;
  const [rawIdentifier = '', query = ''] = withoutSlash.split('?');
  const identifier = rawIdentifier ? safeDecodeURIComponent(rawIdentifier) : undefined;
  const token = new URLSearchParams(query).get('token') ?? undefined;
  return { identifier, token };
}

const roots = new WeakMap<Element, Root>();

/**
 * Renders `VerifyPage` into `root`, keyed by `identifier` and `token`
 * together.
 *
 * `key={...}` is the exact remount discipline `App.tsx`'s own old
 * `VerifyRoute` gave this component before the extraction (see git
 * history): forcing React to tear the whole component down and recreate
 * it whenever either the identifier or the token changes, rather than
 * reusing the mounted instance with a merely-updated prop. Without it, a
 * stale `sig`/`lookup` state -- briefly describing the *previous*
 * certificate while a new check is still running -- would survive past
 * the point where the fragment it was fetched for stopped matching the
 * one now on screen.
 *
 * Reuses the same `Root` on the same element across calls rather than
 * calling `createRoot` again, which React itself warns against -- the
 * same discipline `islands/signup/main.tsx::mountSignupIsland` keeps, for
 * the same reason: this function is called again on every `hashchange`
 * (see the bootstrap below), not only once at load.
 */
export function mountVerifyIsland(root: Element, identifier?: string, token?: string): void {
  let reactRoot = roots.get(root);
  if (!reactRoot) {
    reactRoot = createRoot(root);
    roots.set(root, reactRoot);
  }
  reactRoot.render(
    <StrictMode>
      <VerifyPage key={`${identifier ?? ''}::${token ?? ''}`} identifier={identifier} token={token} />
    </StrictMode>,
  );
}

const mountEl = document.getElementById(MOUNT_ID);
if (mountEl) {
  const renderFromHash = () => {
    const { identifier, token } = parseVerificationFragment(window.location.hash);
    mountVerifyIsland(mountEl, identifier, token);
  };
  renderFromHash();
  // A visitor who opens a second verification link while this page is
  // already loaded in the same tab -- from browser history, or a second
  // link pasted into the address bar -- changes only the URL's fragment:
  // same origin, same path, so a browser resolves it as a same-document
  // navigation and fires `hashchange` rather than a full reload. Without
  // this listener the mounted instance would keep answering for whichever
  // certificate it last loaded, silently describing the wrong one to
  // whoever is now reading the screen.
  window.addEventListener('hashchange', renderFromHash);
}
