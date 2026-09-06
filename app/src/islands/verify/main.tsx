import { StrictMode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { VerifyPage } from './VerifyPage';
import { parseVerificationFragment } from '../../verify/address';

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

/**
 * Re-exported, not defined here. `VerifyPage`'s hand-entry form reads the
 * same shape out of an address somebody pasted off a printed
 * certificate, and no component can import this module: importing it runs
 * the bootstrap at the foot of this file, which mounts an island onto
 * whatever `#verify-app` the importing document happens to hold. So the
 * function moved to `app/src/verify/address.ts`, beside the other pure
 * verification modules, and this line keeps every import path that
 * already named it here.
 */
export { parseVerificationFragment };

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
