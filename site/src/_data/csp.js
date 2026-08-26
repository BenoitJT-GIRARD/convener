/**
 * This project's Content-Security-Policy for every page Eleventy builds,
 * delivered as a `<meta http-equiv>` in `layout.njk` -- the one mechanism
 * available at all here. GitHub Pages sets no response headers of its
 * own: `X-Content-Type-Options`,
 * `Permissions-Policy`, HSTS and COOP/COEP/CORP are categorically
 * unavailable, not merely undone, and `frame-ancestors` is ignored outright
 * when delivered by `<meta>` -- nothing can stop this site being framed. See
 * `docs/reference/operations.md`'s own "Content-Security-Policy" section
 * for that boundary written out in full, so nobody mistakes either half of
 * it for an oversight.
 *
 * What a `<meta>` delivery ignores, and what it does not
 * ------------------------------------------------------
 * Exactly three directives, by the specification: `frame-ancestors`,
 * `report-uri` and `sandbox` (CSP Level 3, the section on the `<meta>`
 * element). **Every other directive works.** This comment used to say that
 * `script-src`, `connect-src`, `object-src` and `form-action` "all work by
 * `<meta>`, and are what this file actually emits", in the place where the
 * reason for that selection belonged -- and it was not a reason, since
 * `default-src`, `img-src`, `style-src` and `font-src` work by `<meta>`
 * just as well. This policy therefore once admitted an image, a
 * frame, a font, a stylesheet or a media file from *any origin at all*, on
 * every page a stranger loads and on the three that carry an island
 * handling somebody's registration, certificate lookup or survey answer.
 *
 * Each directive below is justified by what this project's own pages
 * actually load (checked by building the real site and reading a real
 * browser's console, not assumed): one stylesheet, three woff2 faces and,
 * on three pages, one island bundle -- all from this same origin. No page
 * this build emits carries an `<img>`, an `<iframe>`, a `<video>` or an
 * `<audio>` element at all.
 *
 * - `default-src 'none'`: everything not named below is refused, so the
 *   classes nobody enumerated (`frame-src`, `media-src`, `worker-src`,
 *   `manifest-src`, and whatever the platform adds next) are closed by the
 *   fallback rather than one at a time as somebody happens to think of
 *   them. That is precisely the failure this policy was making.
 * - `script-src 'self'`: every script this build ever emits is same-origin.
 *   No page under `site/` carries an inline `<script>` at all --
 *   `tools/tests/test_site.py::test_archive_pages_carry_no_script_tag_at_all`
 *   already held the archive pages to that, and a sweep of the rest
 *   found the same true of every other page; `event.njk`'s JSON-LD block is
 *   `application/ld+json`, which `script-src` does not govern at all. The
 *   three islands (`event.njk`'s `signup.js`, `verify.njk`'s `verify.js`,
 *   `survey.njk`'s `survey.js`) are all loaded from
 *   this same origin.
 * - `style-src 'self'`: one stylesheet, `style.css`, from this origin. No
 *   page carries a `<style>` block or a `style="..."` attribute, and the
 *   islands set no inline style either -- a real Chrome driven over every
 *   page this build emits reports no violation, which is how this was
 *   settled rather than argued.
 * - `img-src 'self'`: no page loads an image at present. `'self'` rather
 *   than `'none'` because the browser asks for `/favicon.ico` of its own
 *   accord and because a banner this project publishes itself
 *   (`event.njk`'s own `pageImage`, already same-origin) is the one image
 *   these pages would ever gain. A portrait is not: `public-data`'s own
 *   projection deliberately withholds `photo_url`, and this directive is
 *   what keeps that decision true in the browser as well as in the feed.
 * - `font-src 'self'`: the three woff2 faces D-17 chose, self-hosted and
 *   preloaded from `layout.njk`'s own head. That head once carried two
 *   preconnects and a stylesheet link to Google's font CDN, which handed
 *   every visitor's address to a third party; this states the rule to the
 *   browser as well as to the repository.
 * - `connect-src 'self'`, plus the signup relay's own origin when
 *   `VITE_SIGNUP_RELAY_URL` is configured: the registration island
 *   (`app/src/islands/signup/SignupForm.tsx`) posts a registration to that
 *   address from `event.njk`, and the survey island
 *   (`app/src/islands/survey/SurveyForm.tsx`) posts a
 *   response to that same worker's `/survey` route from `survey.njk` --
 *   two islands, one configured origin, never a second one. Read from the
 *   identical repository variable `deploy.yml` already forwards into the
 *   *application* build (`app/vite.config.ts`'s own island entries) --
 *   one configured address, never a second, hand-typed origin (D-14). An
 *   unset relay is D-13's ordinary absence (either form refuses to send,
 *   calmly -- see `SignupForm.tsx`'s own `relayUrl`/`surveyRelayUrl`
 *   comments), so `connect-src` simply omits an address nothing will ever
 *   call rather than naming one.
 * - `base-uri 'none'`: no page here carries a `<base>` element, and
 *   `default-src` does not cover this directive -- an injected `<base>`
 *   would re-point every relative address on the page, including the ones
 *   the three islands fetch their public keys from, and no fetch directive
 *   would notice.
 * - `object-src 'none'`: no `<object>`/`<embed>`/`<applet>` anywhere in this
 *   project -- closes a legacy plugin vector at zero cost. Redundant under
 *   `default-src 'none'`, and kept: it is the one value here that must stay
 *   `'none'` whatever `default-src` is ever loosened to.
 * - `form-action 'self'`: no page under `site/` submits a `<form>` at all
 *   -- every island talks to the relay through a request, never a form
 *   submission. `'self'` costs nothing today and stops an injected `<form>`
 *   from exfiltrating to a foreign origin if one is ever added by mistake.
 *   Not covered by `default-src` either.
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

module.exports = () => ({ meta: metaContent(process.env) });
module.exports.metaContent = metaContent;
module.exports.configuredRelayOrigin = configuredRelayOrigin;
