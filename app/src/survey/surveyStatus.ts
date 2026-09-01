/**
 * `SURVEY_STATUS_FILENAME` and the URL `SurveyForm.tsx` fetches it from --
 * pulled out of `SurveyForm.tsx` itself into this
 * plain, non-component module for the identical reason
 * `src/verify/register.ts` exports `REGISTER_FILENAME` from its own
 * standalone file rather than from whatever component reads it:
 * `SurveyForm.tsx` is a `.tsx` component file, and this project's own
 * `react-refresh/only-export-components` lint rule refuses to let a
 * component file export anything but the component itself (see
 * `SignupForm.tsx::eventPublicKeyUrl`'s own comment for the identical
 * constraint on that sibling form) -- a real constraint, not a style
 * preference: Fast Refresh silently stops preserving component state
 * across an edit to a file that exports non-component values alongside a
 * component.
 *
 * `scripts/survey-status-projection.mjs`'s own `DEST_FILENAME` cannot be
 * imported here directly -- that module reaches into `node:fs`,
 * `node:path` and `node:url`, none of which exist in a browser bundle --
 * so the two sides are pinned equal by a dedicated test
 * (`app/tests/scripts/copy-survey-status.test.ts`) instead, the identical
 * two-sided shape `certificates-projection.mjs::DEST_FILENAME` and
 * `register.ts::REGISTER_FILENAME` already use for `certificates.json`.
 */

// Same idiom as `signup/SignupForm.tsx`'s own `BASE`: the base the app
// itself is served from, so the fetch resolves against the deployed route
// rather than wherever the browser happens to be.
const BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');

/** `scripts/copy-survey-status.mjs`'s own destination -- see that script's
 *  and `survey-status-projection.mjs`'s docstrings for the whole
 *  publish-and-fetch pipeline this closes: a bare JSON array of
 *  the event ids currently open for the survey, derived from
 *  `instance/data/speakers.yml`'s `survey_enabled` field and published outside the
 *  consent gate entirely, because it is an operational fact rather than
 *  programme data.
 *
 * Before this was a pinned, tested constant, `DEST_FILENAME` renaming to
 * something else while this string stayed `'survey-status.json'` (or the
 * reverse) would 404 both the page and the relay with the whole suite
 * still green -- every event reading as closed forever,
 * and nothing turning red anywhere.
 */
export const SURVEY_STATUS_FILENAME = 'survey-status.json';

export function surveyStatusUrl(): string {
  return `${BASE}/${SURVEY_STATUS_FILENAME}`;
}
