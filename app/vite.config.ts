import { fileURLToPath } from 'node:url';
import { defineConfig, type Plugin } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { cspMetaContent, devCspMetaContent } from './scripts/csp.mjs';
import { exampleInstance } from './scripts/example-instance.mjs';
import { exampleSettings } from './scripts/example-settings.mjs';
import { instancePaths } from './scripts/instance-paths.mjs';
import { notice } from './scripts/notice.mjs';
import {
  editionPrefix,
  identity,
  published,
  unconfigured,
} from './scripts/published.mjs';

/**
 * The address this project is published at, read once
 * from `instance/config.json` -- the instance's own declaration -- rather
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
 * Who runs this series, read from the same declaration
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
 * The instance the *demonstration* shows, read from
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
 * The prefix this instance numbers its editions under,
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
/**
 * The six declarations the settings screen reads, for the
 * demonstration only.
 *
 * Signed in, that screen reads `config/` and the drain's workflow straight
 * out of the repository through the Contents API. A demonstration has no
 * repository and may read nothing but the origin that served it
 * (`src/net/request.ts`), so the example instance's four `config/` files
 * and the product's two travel in the bundle instead -- as text, parsed by
 * the application's own reader, exactly as `EXAMPLE` above carries the
 * example's data.
 *
 * Declared for all four configurations along with the rest, for the same
 * reason: no island references it and `define` only substitutes a token a
 * bundle actually contains, but a value present in one configuration and
 * absent from another is the shape that passes a test suite and ships
 * broken.
 */
const EXAMPLE_SETTINGS = exampleSettings();

const EDITION_PREFIX = editionPrefix();

/**
 * Where this instance's own files sit, read from `config/boundary.yml`
 * and carried into the bundle the same way everything above it is.
 *
 * `src/data/DataContext.tsx` asks GitHub for the speaker and config
 * records, `src/settings/form.ts` says of each declared path why it is
 * not a form, and both run in a volunteer's browser, where no file can be
 * read. `src/paths.ts` is what reads the value back.
 *
 * Declared for all four configurations along with the rest, for the same
 * reason: no island references it and `define` only substitutes a token a
 * bundle actually contains, but a value present in one configuration and
 * absent from another is the shape that passes a test suite and ships
 * broken.
 */
const INSTANCE_PATHS = instancePaths();

/**
 * Which of this instance's declared values are still
 * the ones the product ships in `instances/example/instance/config.json`,
 * carried into the bundle the same way as everything above it.
 *
 * Empty for an instance somebody has configured, and the names of the
 * offending keys for one nobody has. `src/components/UnconfiguredBanner.
 * tsx` prints them above the sign-in screen and above the cockpit itself,
 * because the first thing anybody does with a template is deploy it
 * before configuring it -- and a cockpit built from somebody else's
 * declaration is a cockpit whose masthead names the wrong organisation
 * while every check stays green.
 *
 * Declared for all four configurations along with the rest, for the same
 * reason: no island references it and `define` only substitutes a token a
 * bundle actually contains, but a value present in one configuration and
 * absent from another is the shape that passes a test suite and ships
 * broken.
 *
 * JSON rather than the bare string `VITE_INSTANCE_EDITION_PREFIX` is,
 * and for a reason that is the whole point of the warning: the ordinary
 * answer here is *empty*, so a bundle built without this define would be
 * indistinguishable from a configured instance and the banner would go
 * quiet exactly when the build was broken. `'[]'` is a value; an absent
 * define is not, and `src/instance.ts` throws on it (D-25).
 */
const UNCONFIGURED = unconfigured();

/**
 * What this *product* says about itself, read from `NOTICE.json` at the
 * repository root and carried into every bundle the same way everything
 * above it is.
 *
 * `components/Layout.tsx` displays it in the cockpit's footer, and it has to
 * be a define for the reason the identity is one: that footer renders in a
 * volunteer's browser, which can read no file.
 *
 * Its own constant rather than a seventh key of `INSTANCE_DEFINE`, and the
 * separation is the whole point. Everything in that object is the
 * instance's -- a duplicate edits `instance/config.json` before its first
 * build and every one of those values changes. Nothing here changes, in any
 * duplicate, ever: it names the software, its author, its licence and the
 * absence of a warranty. Section 5 of that licence is what obliges a
 * modified version to keep displaying it, and a notice filed among an
 * instance's own settings is a notice somebody eventually edits.
 */
const NOTICE = notice();

const PRODUCT_DEFINE = {
  'import.meta.env.VITE_PRODUCT_NOTICE': JSON.stringify(JSON.stringify(NOTICE)),
};

const INSTANCE_DEFINE = {
  'import.meta.env.VITE_PUBLISHED_URL': JSON.stringify(PUBLISHED.url),
  'import.meta.env.VITE_INSTANCE_IDENTITY': JSON.stringify(JSON.stringify(IDENTITY)),
  'import.meta.env.VITE_INSTANCE_EDITION_PREFIX': JSON.stringify(EDITION_PREFIX),
  'import.meta.env.VITE_EXAMPLE_INSTANCE': JSON.stringify(JSON.stringify(EXAMPLE)),
  'import.meta.env.VITE_EXAMPLE_SETTINGS': JSON.stringify(JSON.stringify(EXAMPLE_SETTINGS)),
  'import.meta.env.VITE_INSTANCE_UNCONFIGURED': JSON.stringify(JSON.stringify(UNCONFIGURED)),
  'import.meta.env.VITE_INSTANCE_PATHS': JSON.stringify(JSON.stringify(INSTANCE_PATHS)),
};

/** What every one of the four configurations below substitutes. Both halves,
 *  always: a value present in one configuration and absent from another is
 *  exactly the shape that passes a test suite and ships broken, and that
 *  applies to the notice as much as to the address. */
const DEFINE = { ...PRODUCT_DEFINE, ...INSTANCE_DEFINE };

/**
 * Injects this project's Content-Security-
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
 * The last public route this document carried
 * (`App.tsx`'s own former `SurveyRoute`, `/survey/:eventId`) moved onto its
 * own island, mounted on `site/src/survey.njk` instead -- this document is now
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
    // This used to inject the shipped policy in both, and
    // `script-src 'self'` refuses `@vitejs/plugin-react`'s inline React
    // Refresh preamble -- so `npm run dev` served a blank page from the
    // day the policy landed until this. `apply: 'build'`
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
 * `mode === 'island-signup'` builds the registration island as its
 * own, separate artefact -- islands are built in the cockpit and
 * published as a compiled artefact, exactly like the application, not as a
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
 * uses. This used to read `'/app/'`, deliberately
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
 * deployment. It is now literally one value:
 * `PUBLISHED.appBase`, derived from `instance/config.json`.
 * `SignupForm.tsx`'s own key fetch reads it back through
 * `import.meta.env.BASE_URL`, landing on
 * `<app base>instance/keys/events/<id>.pub` -- exactly where `copy-event-keys.mjs`
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
    define: DEFINE,
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
 * `mode === 'island-verify'` builds the certificate-verification
 * island the same way `islandSignupConfig` above builds the registration
 * one -- its own, separate artefact, picked apart at the command
 * line by `npm run build`'s third `vite build` call. Everything
 * `islandSignupConfig`'s own comment explains about fixed output names,
 * `base: PUBLISHED.appBase`, and skipping `copyPublicDir` applies
 * identically here: the consumer is `site/src/verify.njk`, a foreign
 * toolchain with no manifest to read hashed names from, and this bundle
 * runs on a page the *site* serves. `register.ts` and `publicKeys.ts`
 * read this same `base` back through `import.meta.env.BASE_URL`, landing
 * on `<app base>certificates.json` and `<app base>instance/keys/signing/index.json`
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
    define: DEFINE,
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
 * `mode === 'island-survey'` builds the post-event
 * survey island the same way `islandSignupConfig`/`islandVerifyConfig`
 * above build their own -- its own, separate artefact, picked apart
 * at the command line by `npm run build`'s fourth `vite build` call.
 * Everything `islandSignupConfig`'s own comment explains about fixed
 * output names, `base: PUBLISHED.appBase`, and skipping `copyPublicDir`
 * applies identically here: the consumer is `site/src/survey.njk`, a
 * foreign toolchain with no manifest to read hashed names from, and this
 * bundle runs on a page the *site* serves. `SurveyForm.tsx` reads this
 * same `base` back through `import.meta.env.BASE_URL`, landing on
 * `<app base>instance/keys/events/<id>.pub` and `<app base>survey-status.json` --
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
    define: DEFINE,
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
    define: DEFINE,
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
        // crypto the encryption promise rests on (the survey intake makes
        // the same promise a second time for a second page), while
        // `islands/signup/SignupForm.tsx`, `islands/verify/VerifyPage.tsx`
        // and
        // `islands/survey/SurveyForm.tsx` are all excluded for
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
          // The one door out of this bundle. Pure logic
          // the demo-mode promise rests on, exactly as directly as
          // `verify/register.ts` rests on the certificate promise.
          'src/net/**',
          // The bounds a settings field refuses on, the
          // reader of the boundary declaration, and the surgical edit that
          // keeps a config file's own argument for itself. Pure logic a
          // promise rests on, in the same class -- a bound computed
          // differently here from the one the scheduled job enforces is
          // the whole defect that screen exists to prevent.
          'src/settings/**',
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
