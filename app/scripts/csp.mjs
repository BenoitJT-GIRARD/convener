/**
 * This project's Content-Security-Policy for `app/index.html` -- the
 * operators' cockpit, every route under the app's own published base, gated on
 * sign-in behind `App.tsx`'s own `Shell`. Injected into the built HTML by
 * `vite.config.ts`'s own `cspHtmlPlugin`, via `transformIndexHtml` --
 * `<meta http-equiv>` is the only mechanism available at all: GitHub Pages
 * sets no response headers of its own (security audit 2026-08-23).
 * `X-Content-Type-Options`, `Permissions-Policy`, HSTS and COOP/COEP/CORP
 * are categorically unavailable, not merely undone, and `frame-ancestors`
 * is ignored outright when delivered by `<meta>` -- see
 * `docs/reference/operations.md`'s own "Content-Security-Policy" section
 * for that boundary written out in full.
 *
 * Phase 7 task 5 moved the last public route this document carried
 * (`/survey/:eventId`, the post-event survey) onto its own island, mounted
 * on `site/src/survey.njk` instead -- see that page's own
 * `site/src/_data/csp.js` for the policy it now ships under. This
 * document's own `connect-src` dropped the signup relay's origin as a
 * direct consequence: nothing left in this bundle posts to it.
 *
 * `script-src`, `connect-src`, `object-src` and `form-action` all work by
 * `<meta>`, and are what this file emits -- each justified by what this
 * bundle actually loads:
 *
 * - `script-src 'self'`: the whole application is one same-origin bundle;
 *   no inline `<script>`, no inline event handler, no `eval` anywhere in it
 *   (confirmed by the audit's own search).
 * - `object-src 'none'`: no `<object>`/`<embed>`/`<applet>` anywhere in this
 *   project -- closes a legacy plugin vector at zero cost.
 * - `form-action 'self'`: every form in this bundle (sign-in, a new
 *   speaker) is a React-controlled submit that never navigates the
 *   document; `'self'` is a safe, zero-cost default against the day one
 *   does by mistake.
 * - `connect-src`: `'self'` (this project's own content and public-data
 *   fetches) plus two origins this bundle calls by design, each admitted
 *   only when the build that reaches it is actually configured to call it
 *   (D-13 -- an unset one is an ordinary state this policy must not name an
 *   address for):
 *     - `https://api.github.com` -- the device sign-in flow
 *       (`auth/device.ts`, when a proxy is configured) and every read/write
 *       against this repository's own Contents API
 *       (`github/client.ts`, `auth/api.ts`, `auth/role.ts`) the cockpit
 *       makes directly from the browser. Always present: a personal-access-
 *       token sign-in reaches it even with no relay configured at all.
 *     - the auth relay's own origin (`VITE_AUTH_PROXY_URL`) --
 *       `auth/device.ts`'s device-flow exchange, when a relay is
 *       configured (D-13: sign-in otherwise falls back to a personal
 *       access token, which never calls it).
 */

const GITHUB_API_ORIGIN = 'https://api.github.com';

/** `value`, trimmed, or the empty string -- never `undefined`/`null`, so
 *  every caller can treat "configured" as "non-empty" without a second
 *  null check. */
function configured(value) {
  return (value || '').trim();
}

/** The exact `content` attribute value this project's `<meta
 *  http-equiv="Content-Security-Policy">` carries, built from `env`
 *  (ordinarily `process.env`, threaded through as a plain object so a test
 *  can supply one without touching the real process environment) rather
 *  than a hand-typed string -- see this module's own header comment for
 *  why each directive is here and what each one costs. */
export function cspMetaContent(env) {
  const authProxy = configured(env.VITE_AUTH_PROXY_URL);
  const connectSrc = ["'self'", GITHUB_API_ORIGIN, authProxy].filter(Boolean).join(' ');
  return [
    "script-src 'self'",
    `connect-src ${connectSrc}`,
    "object-src 'none'",
    "form-action 'self'",
  ].join('; ');
}
