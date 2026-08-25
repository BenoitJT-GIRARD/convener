import { fileURLToPath } from 'node:url';
import { defineConfig, type Plugin } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { cspMetaContent, devCspMetaContent } from './scripts/csp.mjs';
import { exampleInstance } from './scripts/example-instance.mjs';
import { editionPrefix, identity, published } from './scripts/published.mjs';

/**
 * Phase 10, task 2: the address this project is published at, read once
 * from `config/instance.json` -- the instance's own declaration -- rather
 * than typed into this file four times as `base: '/<repository>/app/'`.
 *
 * A build configuration cannot always read what one would like at the
 * moment one would like, so this was checked before being promised rather
 * than assumed: Vite loads this file in Node, bundling it with esbuild
 * first, which is exactly why `./scripts/csp.mjs` above is already
 * imported and called here. `published()` is the same shape -- a plain
 * ESM module doing a `readFileSync` -- so `base` below is genuinely
 * derived, not a literal with a comment claiming a derivation.
 *
 * `define` carries the one value that has to survive into the browser.
 * `src/content/render.ts` builds a public registration link inside a
 * volunteer's browser, where nothing can read a file at all, so the
 * address is substituted into the bundle at build time under
 * `import.meta.env.VITE_PUBLISHED_URL`. Declared for every one of the
 * four configurations below, including the three islands: `vitest` reads
 * the main configuration and each island is built from its own, and a
 * value present in one but not another is exactly the shape that passes
 * a test suite and ships broken.
 */
const PUBLISHED = published();

/**
 * Phase 10, task 3: who runs this series, read from the same declaration
 * and carried into the bundle the same way.
 *
 * `src/content/render.ts` resolves the `{{ instance.* }}` namespace that
 * `docs/toolkit/`'s templates are written in, and the cockpit's own
 * chrome (`components/Layout.tsx`, `auth/Login.tsx`) names the
 * organisation too. All of that runs in a volunteer's browser, where no
 * file can be read, so the identity has to be substituted in at build
 * time exactly as the published address already is.
 *
 * One `define`, holding the whole object as JSON, rather than one per
 * field: Vite's `define` is a textual replacement, and eight of them
 * would be eight things to remember to add to four configurations the
 * next time the vocabulary grows by a word.
 */
const IDENTITY = identity();

/**
 * Phase 11, task 2: the instance the *demonstration* shows, read from
 * `instances/example/` and carried into the bundle the same way again.
 *
 * `src/data/demo.ts` used to be an instance written in code -- five
 * invented speaker records, an invented board, and two promotion channels
 * naming this organisation's own forum and LinkedIn page, compiled into
 * the cockpit so that a duplicate shipped them too. The example instance
 * already existed and was already exercised on every run of the Python
 * suite; this is what makes the cockpit consume it rather than invent a
 * third set of fictional data. See `scripts/example-instance.mjs` for why
 * the two files travel as text and are parsed by the application's own
 * reader, and why they are not published into `dist/` and fetched.
 *
 * Declared for all four configurations along with the two above, for the
 * identical reason: no island references it today, and `define` only ever
 * substitutes a token a bundle actually contains -- but a value present in
 * one configuration and absent from another is exactly the shape that
 * passes a test suite and ships broken.
 */
const EXAMPLE = exampleInstance();

/**
 * Phase 11, task 4: the prefix this instance numbers its editions under,
 * read from the same declaration and carried in the same way.
 *
 * `src/state/agenda.ts::nextEditionCode` composes the next edition code
 * when a volunteer locks a date, and it used to compose it as `MRG-${n}` --
 * the initials of the series that happens to run this repository, in the
 * product's own source, so a duplicate's reading group numbered its
 * sessions `MRG-1`. That code runs in a browser, which can read no file,
 * so the value has to be substituted in at build time exactly as the
 * address and the identity already are.
 *
 * A bare string rather than JSON, unlike the two above: this one is a
 * single value, not a vocabulary that grows by a word.
 */
const EDITION_PREFIX = editionPrefix();

const INSTANCE_DEFINE = {
  'import.meta.env.VITE_PUBLISHED_URL': JSON.stringify(PUBLISHED.url),
  'import.meta.env.VITE_INSTANCE_IDENTITY': JSON.stringify(JSON.stringify(IDENTITY)),
  'import.meta.env.VITE_INSTANCE_EDITION_PREFIX': JSON.stringify(EDITION_PREFIX),
  'import.meta.env.VITE_EXAMPLE_INSTANCE': JSON.stringify(JSON.stringify(EXAMPLE)),
};

/**
 * Security audit 2026-08-23, M4: injects this project's Content-Security-
 * Policy as a `<meta http-equiv>` into `app/index.html` at build time --
 * `<meta>` is the only delivery mechanism available at all (GitHub Pages
 * sets no response headers). `scripts/csp.mjs::cspMetaContent` is the one
 * place the policy string itself is built (see that module's own header
 * comment for every directive and why); this plugin only ever calls it
 * and hands the result to Vite's own `transformIndexHtml` tag-injection
 * API, never a string edit of the HTML template -- the same reason
 * `react()` above is a plugin and not a source rewrite. Runs only against
 * the main app build: `islandSignupConfig`/`islandVerifyConfig`/
 * `islandSurveyConfig` below build straight from a `.tsx` entry, with no
 * `index.html` for `transformIndexHtml` to ever see, so this plugin is
 * deliberately not added to any of them.
 *
 * Phase 7 task 5 moved the last public route this document carried
 * (`App.tsx`'s own former `SurveyRoute`, `/survey/:eventId`) onto its own
 * island, mounted on `site/src/survey.njk` instead -- this document is now
 * the operators' cockpit alone, gated on sign-in behind `Shell`. See
 * `scripts/csp.mjs`'s own module comment for what that means for
 * `connect-src`.
 */
function cspHtmlPlugin(): Plugin {
  return {
    name: 'convener-csp-meta',
    // `ctx.server` is set when this hook runs for the development server
    // and absent on a build -- the one fact that tells the two apart from
    // inside the hook, and read here rather than kept as plugin state so
    // that nothing has to stay in step with a `configResolved`.
    //
    // Phase 11: this used to inject the shipped policy in both, and
    // `script-src 'self'` refuses `@vitejs/plugin-react`'s inline React
    // Refresh preamble -- so `npm run dev` served a blank page from the
    // day the policy landed (2026-08-23) until this. `apply: 'build'`
    // would have fixed the page by removing the policy from the only
    // place a violation is actually looked at; see `scripts/csp.mjs`'s own
    // "The development server needs two of these loosened" for why the
    // development server carries a policy of its own instead.
    transformIndexHtml(_html, ctx) {
      return [
        {
          tag: 'meta',
          attrs: {
            'http-equiv': 'Content-Security-Policy',
            content: ctx.server
              ? devCspMetaContent(process.env)
              : cspMetaContent(process.env),
          },
          injectTo: 'head-prepend',
        },
        {
          tag: 'meta',
          attrs: { name: 'referrer', content: 'strict-origin-when-cross-origin' },
          injectTo: 'head-prepend',
        },
      ];
    },
  };
}

/**
 * Task 6: `mode === 'island-signup'` builds the registration island as its
 * own, separate artefact -- P-2 ("islands are built in the cockpit ... and
 * published as a compiled artefact, exactly like the application"), not a
 * second entry folded into the operators' app's own SPA bundle. `npm run
 * build`'s own two `vite build` invocations pick this apart at the
 * command line (`--mode island-signup`), the one lever this file exposes
 * for it, so nothing about `package.json`'s existing `build` script order
 * changes beyond appending the second call.
 *
 * Fixed, unhashed output names (`entryFileNames`/`assetFileNames`): the
 * consumer is `site/src/event.njk`, a Nunjucks template compiled by a
 * wholly separate toolchain (Eleventy) with no manifest to read this
 * build's hashed names from -- the same reason a widget bundle meant for
 * a foreign page conventionally ships under a name that does not change
 * build to build.
 *
 * `base: PUBLISHED.appBase`, the *same* value the main app build below
 * uses -- Fix round 4 correction: this used to read `'/app/'`, deliberately
 * distinct from the main app's own base, on the reasoning that this bundle
 * runs on a page the *site* serves, whose own templates already addressed
 * the app's published assets root-relative to the site's own root
 * (`layout.njk`'s `/style.css`, `/fonts/`). That reasoning assumed the
 * site's own root-relative links already landed at wherever GitHub Pages
 * resolves this project's published root to -- which they did not: there
 * is no CNAME and no custom domain, so that root is one path segment below
 * the domain root a bare `/foo` actually addresses. That gap is the whole
 * of the defect `site/.eleventy.js`'s own `pathPrefix` and every
 * template's `| url` filter call now close -- it was not a fact particular
 * to this island, just uncaught here for the identical reason it was
 * uncaught everywhere else: every screenshot pass served the built site at
 * a bare localhost root, where the gap does not exist to see.
 *
 * With the site now prefix-aware, both this island and the main app
 * publish to, and are addressed from, the exact same place (the published
 * repository's own `app/` subtree, `deploy.yml`'s own push step) -- so
 * both now share the one value that actually describes it, rather than two
 * that happened to agree only by not yet having been tested against a real
 * deployment. Phase 10 task 2 made that literally one value:
 * `PUBLISHED.appBase`, derived from `config/instance.json`.
 * `SignupForm.tsx`'s own key fetch reads it back through
 * `import.meta.env.BASE_URL`, landing on
 * `<app base>keys/events/<id>.pub` -- exactly where `copy-event-keys.mjs`
 * already publishes it inside the app's own `dist/`.
 *
 * No CSS import from this entry (`main.tsx` imports no stylesheet): the
 * island's own class names are plain, semantic strings styled by
 * `site/src/style.css`, which the event page already loads -- see
 * `SignupForm.tsx`'s own module comment for why pulling in the app's
 * Tailwind build here, complete with its `@tailwind base` reset, would
 * leak page-wide rather than stay scoped to this component's own subtree.
 * `copyPublicDir: false`: the main app build below already publishes
 * `public/` (handbook pages, signing keys, fonts, certificates.json...)
 * inside its own `dist/` -- this island needs none of it a second time.
 */
function islandSignupConfig() {
  return {
    plugins: [react()],
    base: PUBLISHED.appBase,
    define: INSTANCE_DEFINE,
    build: {
      outDir: 'dist/islands/signup',
      emptyOutDir: true,
      copyPublicDir: false,
      cssCodeSplit: false,
      rollupOptions: {
        input: fileURLToPath(new URL('./src/islands/signup/main.tsx', import.meta.url)),
        output: {
          format: 'es' as const,
          entryFileNames: 'signup.js',
          chunkFileNames: 'signup-[name].js',
          assetFileNames: 'signup.[ext]',
        },
      },
    },
  };
}

/**
 * Task 7: `mode === 'island-verify'` builds the certificate-verification
 * island the same way `islandSignupConfig` above builds the registration
 * one -- its own, separate artefact (P-2), picked apart at the command
 * line by `npm run build`'s third `vite build` call. Everything
 * `islandSignupConfig`'s own comment explains about fixed output names,
 * `base: PUBLISHED.appBase`, and skipping `copyPublicDir` applies
 * identically here: the consumer is `site/src/verify.njk`, a foreign
 * toolchain with no manifest to read hashed names from, and this bundle
 * runs on a page the *site* serves. `register.ts` and `publicKeys.ts`
 * read this same `base` back through `import.meta.env.BASE_URL`, landing
 * on `<app base>certificates.json` and `<app base>keys/signing/index.json`
 * -- exactly where the main app build's own `scripts/copy-certificates.mjs`
 * and `copy-signing-keys.mjs` publish them inside `dist/`.
 *
 * No CSS import from this entry either, for the identical reason
 * `islandSignupConfig`'s own comment gives: the island's class names are
 * plain, semantic strings (`verify__panel`, ...) styled by
 * `site/src/style.css`, which the verify page already loads -- see
 * `VerifyPage.tsx`'s own module comment.
 */
function islandVerifyConfig() {
  return {
    plugins: [react()],
    base: PUBLISHED.appBase,
    define: INSTANCE_DEFINE,
    build: {
      outDir: 'dist/islands/verify',
      emptyOutDir: true,
      copyPublicDir: false,
      cssCodeSplit: false,
      rollupOptions: {
        input: fileURLToPath(new URL('./src/islands/verify/main.tsx', import.meta.url)),
        output: {
          format: 'es' as const,
          entryFileNames: 'verify.js',
          chunkFileNames: 'verify-[name].js',
          assetFileNames: 'verify.[ext]',
        },
      },
    },
  };
}

/**
 * Task 5 (phase 7): `mode === 'island-survey'` builds the post-event
 * survey island the same way `islandSignupConfig`/`islandVerifyConfig`
 * above build their own -- its own, separate artefact (P-2), picked apart
 * at the command line by `npm run build`'s fourth `vite build` call.
 * Everything `islandSignupConfig`'s own comment explains about fixed
 * output names, `base: PUBLISHED.appBase`, and skipping `copyPublicDir`
 * applies identically here: the consumer is `site/src/survey.njk`, a
 * foreign toolchain with no manifest to read hashed names from, and this
 * bundle runs on a page the *site* serves. `SurveyForm.tsx` reads this
 * same `base` back through `import.meta.env.BASE_URL`, landing on
 * `<app base>keys/events/<id>.pub` and `<app base>survey-status.json` --
 * exactly where the main app build's own `copy-event-keys.mjs` and
 * `copy-survey-status.mjs` publish them inside `dist/`.
 *
 * No CSS import from this entry either, for the identical reason
 * `islandSignupConfig`'s own comment gives: the island's class names are
 * plain, semantic strings (`survey-form__field`, ...) styled by
 * `site/src/style.css`, which the survey page already loads -- see
 * `SurveyForm.tsx`'s own module comment.
 */
function islandSurveyConfig() {
  return {
    plugins: [react()],
    base: PUBLISHED.appBase,
    define: INSTANCE_DEFINE,
    build: {
      outDir: 'dist/islands/survey',
      emptyOutDir: true,
      copyPublicDir: false,
      cssCodeSplit: false,
      rollupOptions: {
        input: fileURLToPath(new URL('./src/islands/survey/main.tsx', import.meta.url)),
        output: {
          format: 'es' as const,
          entryFileNames: 'survey.js',
          chunkFileNames: 'survey-[name].js',
          assetFileNames: 'survey.[ext]',
        },
      },
    },
  };
}

export default defineConfig(({ mode }) => {
  if (mode === 'island-signup') return islandSignupConfig();
  if (mode === 'island-verify') return islandVerifyConfig();
  if (mode === 'island-survey') return islandSurveyConfig();

  return {
    plugins: [react(), cspHtmlPlugin()],
    base: PUBLISHED.appBase,
    define: INSTANCE_DEFINE,
    build: { outDir: 'dist' },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./tests/setup.ts'],
      coverage: {
        provider: 'v8',
        reporter: ['text', 'lcov'],
        // Pure logic only. UI components are covered by behaviour, not by a
        // percentage — a threshold there buys assertions nobody reads.
        // `signup/encrypt.ts` and `survey/encrypt.ts` are the two files named
        // individually rather than their whole directories: each is pure
        // crypto the phase 4 promise rests on (task 16's own survey intake is
        // the same promise, made a second time for a second page), while
        // `islands/signup/SignupForm.tsx`, `islands/verify/VerifyPage.tsx`
        // (moved here from `verify/VerifyPage.tsx` by task 7) and
        // `islands/survey/SurveyForm.tsx` (moved here from
        // `survey/SurveyForm.tsx` by phase 7 task 5) are all excluded for
        // the same reason -- UI like every other screen; the rest of
        // `verify/` and `survey/` is pure logic (crypto, register lookup,
        // published-key loading, display formatting, the survey-status
        // fetch address) each phase's own promise rests on just as
        // directly as `encrypt.ts` does.
        include: [
          'src/state/**',
          'src/data/**',
          'src/github/**',
          'src/auth/**',
          // Phase 11 task 1: the one door out of this bundle. Pure logic
          // the demo-mode promise rests on, exactly as directly as
          // `verify/register.ts` rests on the certificate promise.
          'src/net/**',
          'src/signup/encrypt.ts',
          'src/survey/encrypt.ts',
          'src/verify/verify.ts',
          'src/verify/format.ts',
          'src/verify/register.ts',
          'src/verify/publicKeys.ts',
        ],
        exclude: ['src/data/demo.ts'],
        thresholds: { lines: 90, functions: 90, branches: 85, statements: 90 },
      },
    },
  };
});
