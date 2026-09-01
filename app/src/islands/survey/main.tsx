import { StrictMode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { SurveyForm } from './SurveyForm';

/**
 * Bootstraps the survey island onto whatever the built survey page
 * provides -- `site/src/survey.njk`'s own `#survey-form` element,
 * carrying the event id as a `data-event-id` attribute rather than a
 * route param: the identical contract `islands/signup/main.tsx` already
 * uses for `event.njk`'s `#registration-form`, and for the identical
 * reason -- this island has no router of its own, one static page per
 * event (D-19), not a fragment a script re-parses.
 *
 * `MOUNT_ID` is the exact id `site/src/survey.njk` reserves, and
 * `site/scripts/check-a11y.mjs` drives to its real `ready` state.
 */
export const MOUNT_ID = 'survey-form';

const roots = new WeakMap<Element, Root>();

/**
 * Renders `SurveyForm` into `root`, keyed by the element's own
 * `data-event-id` at the moment of the call.
 *
 * `key={eventId}` is the exact remount discipline
 * `islands/signup/main.tsx::mountSignupIsland` gives its own form, applied
 * here for the identical reason: forcing React to tear the whole
 * component down and recreate it whenever the event id changes, rather
 * than reusing the mounted instance with a merely-updated prop. Without
 * it, a stale `pageState` -- and whatever a participant had already
 * answered -- would survive past the point where the id it was fetched
 * for stopped matching the one now being submitted under.
 *
 * A real page never calls this twice with two different ids: one static
 * page per event means a changed id is a full page load, which already
 * discards everything. This function stays callable more than once
 * anyway -- reusing the same `Root` on the same element rather than
 * calling `createRoot` again, which React itself warns against -- purely
 * so `app/tests/islands/survey-island-mount.test.tsx` can exercise the remount
 * discipline directly, deterministically, without simulating a real
 * navigation.
 */
export function mountSurveyIsland(root: Element): void {
  const eventId = (root as HTMLElement).dataset.eventId || undefined;
  let reactRoot = roots.get(root);
  if (!reactRoot) {
    reactRoot = createRoot(root);
    roots.set(root, reactRoot);
  }
  reactRoot.render(
    <StrictMode>
      <SurveyForm key={eventId} eventId={eventId} />
    </StrictMode>,
  );
}

const mountEl = document.getElementById(MOUNT_ID);
if (mountEl) mountSurveyIsland(mountEl);
