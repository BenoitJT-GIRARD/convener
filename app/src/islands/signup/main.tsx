import { StrictMode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { SignupForm } from './SignupForm';

/**
 * Bootstraps the registration island onto whatever the built event page
 * provides -- `site/src/event.njk`'s own `#registration-form` element,
 * carrying the event id as a `data-event-id` attribute rather than a route
 * param: this island has no router of its own, one static page per event
 * (D-19), not a fragment a script re-parses.
 *
 * `MOUNT_ID` is deliberately the same id `tools/tests/test_site.py::
 * test_the_notice_precedes_the_reserved_place_for_the_registration_form`
 * already pins against the built page -- this is that reserved place.
 */
export const MOUNT_ID = 'registration-form';

const roots = new WeakMap<Element, Root>();

/**
 * Renders `SignupForm` into `root`, keyed by the element's own
 * `data-event-id` at the moment of the call.
 *
 * `key={eventId}` is the exact remount discipline `app/src/App.tsx` used
 * to give the operators'-app version of this route (`SignupRoute`, before
 * this extraction -- see git history): forcing React to tear the whole
 * component down and recreate it whenever the event id changes, rather
 * than reusing the mounted instance with a merely-updated prop. Without
 * it, a stale `keyState` -- and whatever the participant had already
 * typed -- would survive past the point where the id it was fetched for
 * stopped matching the one now being submitted under.
 *
 * A real page never calls this twice with two different ids: one static
 * page per event means a changed id is a full page load, which already
 * discards everything. This function stays callable more than once
 * anyway -- reusing the same `Root` on the same element rather than
 * calling `createRoot` again, which React itself warns against -- purely
 * so `app/tests/signup-island-mount.test.tsx` can exercise the remount
 * discipline directly, deterministically, without simulating a real
 * navigation.
 */
export function mountSignupIsland(root: Element): void {
  const eventId = (root as HTMLElement).dataset.eventId || undefined;
  let reactRoot = roots.get(root);
  if (!reactRoot) {
    reactRoot = createRoot(root);
    roots.set(root, reactRoot);
  }
  reactRoot.render(
    <StrictMode>
      <SignupForm key={eventId} eventId={eventId} />
    </StrictMode>,
  );
}

const mountEl = document.getElementById(MOUNT_ID);
if (mountEl) mountSignupIsland(mountEl);
