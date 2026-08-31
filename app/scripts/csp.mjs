/**
 * This project's Content-Security-Policy for `app/index.html` -- the
 * operators' cockpit, every route under the app's own published base, gated on
 * sign-in behind `App.tsx`'s own `Shell`. Injected into the built HTML by
 * `vite.config.ts`'s own `cspHtmlPlugin`, via `transformIndexHtml` --
 * `<meta http-equiv>` is the only mechanism available at all: GitHub Pages
 * sets no response headers of its own.
 * `X-Content-Type-Options`, `Permissions-Policy`, HSTS and COOP/COEP/CORP
 * are categorically unavailable, not merely undone, and `frame-ancestors`
 * is ignored outright when delivered by `<meta>` -- see
 * `docs/operating/operations.md`'s own "Content-Security-Policy" section
 * for that boundary written out in full.
 *
 * The last public route this document carried
 * (`/survey/:eventId`, the post-event survey) moved onto its own island, mounted
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
 * third-party `<img src>` added to a screen was held by nothing. That gap
 * is closed.
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
 *   (confirmed by search, not assumed). Vite's own
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
 *
 * The development server needs two of these loosened, and only two
 * ---------------------------------------------------------------------
 * `transformIndexHtml` runs on the development server as well as on a
 * build, so this same policy was being injected into the document `npm
 * run dev` serves -- and `script-src 'self'` refuses
 * `@vitejs/plugin-react`'s own React Refresh preamble, which is an
 * *inline* module script the plugin writes into the head. The console
 * said so in as many words ("Executing inline script violates the
 * following Content Security Policy directive 'script-src 'self''"), the
 * plugin then said "@vitejs/plugin-react can't detect preamble", and the
 * page rendered nothing at all. Since the 2026-08-23 audit added the
 * policy, `npm run dev` has served a blank page. The shipped artefact was
 * never affected, which is why it went unnoticed.
 *
 * The obvious remedy is `apply: 'build'` on the plugin, and it does work.
 * It is also the wrong one: it takes the policy out of the one
 * environment where a violation is *seen*. A developer who adds an
 * `<img src="https://third-party.example/...">` to a screen would watch
 * it load in development and have it refused in production, where nobody
 * is reading a console -- which is the exact class of defect this policy
 * exists to catch (`tests/demo-network.test.tsx` had already written down
 * that a third-party `<img>` was held by nothing). So the development server carries a policy of its own,
 * derived from the shipped one by `devCspMetaContent` below rather than
 * written out a second time, loosening exactly the directives Vite's own
 * development server requires and no others -- so `img-src`, `font-src`,
 * `connect-src`, `default-src`, `base-uri`, `object-src` and
 * `form-action` all still bite while a developer is looking.
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

/**
 * What the development server has to be admitted that the published
 * document does not, directive by directive, with the thing that needs it
 * named beside each. Nothing here reaches a built artefact: `vite.config.
 * ts`'s own `cspHtmlPlugin` reads it only when `transformIndexHtml` is
 * called with a `server` in its context, and `app/tests/csp.test.ts`
 * asserts on the real built HTML that it did not.
 *
 * - `script-src 'unsafe-inline'`: `@vitejs/plugin-react`'s React Refresh
 *   preamble, an inline module script the plugin injects into every
 *   served document. A hash would be narrower and was rejected: the
 *   preamble's text contains this build's own base path, so the hash
 *   would change with `instance/config.json` and again with any version
 *   bump of the plugin, and the failure it produces -- a blank page with
 *   one console line -- is exactly the one this is fixing.
 * - `style-src 'unsafe-inline'`: in development Vite serves each CSS
 *   import as a module that injects a `<style>` element at run time,
 *   rather than as the one built stylesheet the published document links.
 *
 * `connect-src` is deliberately *not* here, and that was checked rather
 * than assumed: the hot-reload socket is `ws://` on the same host, which
 * `'self'` already matches (CSP Level 3), and a browser driven at the
 * real development server logs `[vite] connected.` under the policy
 * above.
 */
const DEVELOPMENT_ONLY = {
  'script-src': "'unsafe-inline'",
  'style-src': "'unsafe-inline'",
};

/**
 * The policy the development server's own document carries: the shipped
 * one, with `DEVELOPMENT_ONLY`'s additions folded into the directives it
 * names.
 *
 * Derived from `cspMetaContent` rather than written out again, for the
 * reason this project derives everything else: a second list would be a
 * second policy, free to stop agreeing with the one that ships the day
 * somebody adds a directive to only one of them.
 */
export function devCspMetaContent(env) {
  return cspMetaContent(env)
    .split('; ')
    .map((directive) => {
      const name = directive.split(' ')[0];
      const extra = DEVELOPMENT_ONLY[name];
      return extra ? `${directive} ${extra}` : directive;
    })
    .join('; ');
}
