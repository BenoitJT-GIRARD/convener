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
 * What a `<meta>` delivery ignores, and what it does not
 * ------------------------------------------------------
 * Exactly three directives, by the specification: `frame-ancestors`,
 * `report-uri` and `sandbox` (CSP Level 3, the section on the `<meta>`
 * element; `Content-Security-Policy-Report-Only` is not deliverable this
 * way at all either). **Every other directive works.**
 *
 * This comment used to read "`script-src`, `connect-src`, `object-src` and
 * `form-action` all work by `<meta>`, and are what this file emits", which
 * stood where the reason for that selection should have been -- and it was
 * not one: `default-src`, `img-src`, `style-src`, `font-src` and
 * `base-uri` work by `<meta>` exactly as well. The four were never the
 * deliverable set; they were the set somebody had considered. The rest
 * went unexamined, and the consequence was not theoretical: with no
 * `default-src` and no `img-src`, an image, a frame, a font, a stylesheet,
 * a media file or a worker could be fetched from *any origin at all*, in
 * both modes -- including the demonstration a stranger drives, where
 * `tests/demo-network.test.tsx` had already written down that a
 * third-party `<img src>` added to a screen was held by nothing. Phase 11
 * examined them.
 *
 * Each directive, and what this bundle actually loads to justify it
 * -----------------------------------------------------------------
 * The whole of what the built document fetches is one module script, one
 * stylesheet, three woff2 faces and one SVG favicon -- all from this
 * project's own published base -- plus whatever the application asks for
 * at run time through `src/net/request.ts`, its one door. Nothing else: no
 * `<img>` in any screen, no `<iframe>`, no `<video>`/`<audio>`, no `data:`
 * URI in the built CSS, no web worker, no manifest.
 *
 * - `default-src 'none'`: everything not named below is refused. The
 *   fallback is the whole point -- naming `img-src` alone would have left
 *   `frame-src`, `media-src`, `worker-src`, `manifest-src` and whatever
 *   the platform adds next wide open, which is the same omission this
 *   policy was just found to be making, one class narrower. A screen that
 *   genuinely needs to load something new fails loudly here rather than
 *   contacting a third party quietly.
 * - `script-src 'self'`: the whole application is one same-origin bundle;
 *   no inline `<script>`, no inline event handler, no `eval` anywhere in it
 *   (confirmed by the audit's own search). Vite's own
 *   `<link rel="modulepreload">` is governed by this directive too.
 * - `style-src 'self'`: one stylesheet, from this same origin, emitted by
 *   the build. No `<style>` block and no `style="..."` attribute in any
 *   source here -- `ProgressBar.tsx`'s own `style={{ width }}` is applied
 *   through the CSSOM by React, which CSP does not govern at all, and a
 *   real Chrome driven over every screen of the built cockpit reports no
 *   violation. That run is how this one was settled rather than argued:
 *   a `style-src` that broke a legitimate stylesheet would be deleted by
 *   whoever met it next, which is worse than never having written it.
 * - `img-src 'self'`: exactly one image is loaded, `favicon.svg`, from
 *   this origin. `Speaker.photo_url` is a link this cockpit deliberately
 *   never renders as an `<img>`; the day a screen does, this directive is
 *   what stops a volunteer's browser announcing itself to whichever host
 *   the portrait sits on.
 * - `font-src 'self'`: the three woff2 faces D-17 chose, self-hosted under
 *   `/fonts/` and preloaded from this document's own `<head>`. That head
 *   once loaded a stylesheet from Google's font CDN;
 *   `tests/no-third-party-fonts.test.ts` is the guard that keeps it from
 *   coming back, and this is the same rule stated to the browser instead
 *   of only to the repository.
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
 * - `base-uri 'none'`: this document carries no `<base>` element, and
 *   `default-src` does not cover this directive -- an injected `<base>`
 *   would silently re-point every relative address the router and the
 *   bundle build, without a single fetch directive noticing.
 * - `object-src 'none'`: no `<object>`/`<embed>`/`<applet>` anywhere in this
 *   project -- closes a legacy plugin vector at zero cost. Redundant under
 *   `default-src 'none'`, and kept: it is the one value here that must stay
 *   `'none'` whatever `default-src` is ever loosened to.
 * - `form-action 'self'`: every form in this bundle (sign-in, a new
 *   speaker) is a React-controlled submit that never navigates the
 *   document; `'self'` is a safe, zero-cost default against the day one
 *   does by mistake. Not covered by `default-src` either.
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
    "default-src 'none'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self'",
    "font-src 'self'",
    `connect-src ${connectSrc}`,
    "base-uri 'none'",
    "object-src 'none'",
    "form-action 'self'",
  ].join('; ');
}
