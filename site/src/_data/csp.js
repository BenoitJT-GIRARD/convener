/**
 * This project's Content-Security-Policy for every page Eleventy builds,
 * delivered as a `<meta http-equiv>` in `layout.njk` -- the one mechanism
 * available at all here. GitHub Pages sets no response headers of its own
 * (security audit 2026-08-23): `X-Content-Type-Options`,
 * `Permissions-Policy`, HSTS and COOP/COEP/CORP are categorically
 * unavailable, not merely undone, and `frame-ancestors` is ignored outright
 * when delivered by `<meta>` -- nothing can stop this site being framed.
 * `script-src`, `connect-src`, `object-src` and `form-action` all work by
 * `<meta>`, and are what this file actually emits. See
 * `docs/reference/operations.md`'s own "Content-Security-Policy" section
 * for that boundary written out in full, so nobody mistakes either half of
 * it for an oversight.
 *
 * Each directive below is justified by what this project's own pages
 * actually load (checked by building the real site and reading a real
 * browser's console, not assumed):
 *
 * - `script-src 'self'`: every script this build ever emits is same-origin.
 *   No page under `site/` carries an inline `<script>` at all --
 *   `tools/tests/test_site.py::test_archive_pages_carry_no_script_tag_at_all`
 *   already held the archive pages to that, and the audit's own search
 *   found the same true of every other page; `event.njk`'s JSON-LD block is
 *   `application/ld+json`, which `script-src` does not govern at all. The
 *   two islands (`event.njk`'s `signup.js`, `verify.njk`'s `verify.js`) are
 *   both loaded from this same origin.
 * - `object-src 'none'`: no `<object>`/`<embed>`/`<applet>` anywhere in this
 *   project -- closes a legacy plugin vector at zero cost.
 * - `form-action 'self'`: no page under `site/` submits a `<form>` at all
 *   -- both islands talk to the relay through `fetch()`, never a form
 *   submission. `'self'` costs nothing today and stops an injected `<form>`
 *   from exfiltrating to a foreign origin if one is ever added by mistake.
 * - `connect-src 'self'`, plus the signup relay's own origin when
 *   `VITE_SIGNUP_RELAY_URL` is configured: the registration island
 *   (`app/src/islands/signup/SignupForm.tsx`) posts a registration straight
 *   to that address, from this same document (`event.njk` mounts it). Read
 *   from the identical repository variable `deploy.yml` already forwards
 *   into the *application* build (`app/vite.config.ts`'s own island
 *   entries) -- one configured address, never a second, hand-typed origin
 *   (D-14). An unset relay is D-13's ordinary absence (the form itself
 *   refuses to send, calmly -- see `SignupForm.tsx`'s own `relayUrl`
 *   comment), so `connect-src` simply omits an address nothing will ever
 *   call rather than naming one.
 */

/** `env.VITE_SIGNUP_RELAY_URL`, trimmed, or the empty string -- never
 *  `undefined`, so every caller can treat "configured" as "non-empty"
 *  without a second null check. */
function configuredRelayOrigin(env) {
  return (env.VITE_SIGNUP_RELAY_URL || '').trim();
}

/** The exact `content` attribute value this project's `<meta
 *  http-equiv="Content-Security-Policy">` carries, built from `env`
 *  (ordinarily `process.env`, threaded through as a plain object so a test
 *  can supply one without touching the real process environment) rather
 *  than a hand-typed string -- see this module's own header comment for
 *  why each directive is here and what each one costs. */
function metaContent(env) {
  const relay = configuredRelayOrigin(env);
  const connectSrc = relay ? `'self' ${relay}` : "'self'";
  return [
    "script-src 'self'",
    `connect-src ${connectSrc}`,
    "object-src 'none'",
    "form-action 'self'",
  ].join('; ');
}

module.exports = () => ({ meta: metaContent(process.env) });
module.exports.metaContent = metaContent;
module.exports.configuredRelayOrigin = configuredRelayOrigin;
