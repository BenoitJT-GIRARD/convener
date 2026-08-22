import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

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
 * `base: '/app/'`, deliberately not the main app's own `/example-showcase/app/`
 * below: this bundle runs on a page the *site* serves, whose own templates
 * already address the app's published assets root-relative to the site's
 * own root (`layout.njk`'s `/style.css`, `/fonts/`), not to wherever
 * GitHub Pages ultimately resolves that root to
 * (docs/superpowers/deferred-work.md, entry 11 -- a maintainer's Pages
 * setting, out of scope here). `SignupForm.tsx`'s own key fetch reads this
 * value back through `import.meta.env.BASE_URL`, landing on
 * `/app/keys/events/<id>.pub` -- exactly where `copy-event-keys.mjs`
 * already publishes it inside the app's own `dist/`, unaffected by
 * whichever `base` the *main* app build below uses for its own asset
 * URLs.
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
    base: '/app/',
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
 * `base: '/app/'`, and skipping `copyPublicDir` applies identically here:
 * the consumer is `site/src/verify.njk`, a foreign toolchain with no
 * manifest to read hashed names from, and this bundle runs on a page the
 * *site* serves, whose own templates already address the app's published
 * assets root-relative to the site's own root.
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
    base: '/app/',
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

export default defineConfig(({ mode }) => {
  if (mode === 'island-signup') return islandSignupConfig();
  if (mode === 'island-verify') return islandVerifyConfig();

  return {
    plugins: [react()],
    base: '/example-showcase/app/',
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
        // `islands/signup/SignupForm.tsx` and `SurveyForm.tsx` are UI like
        // every other screen. `islands/verify/VerifyPage.tsx` (moved here
        // from `verify/VerifyPage.tsx` by task 7) is excluded for the same
        // reason; the rest of `verify/` is pure logic (crypto
        // verification, register lookup, published-key loading, display
        // formatting) the phase 4 certificate promise rests on just as
        // directly as `encrypt.ts` does.
        include: [
          'src/state/**',
          'src/data/**',
          'src/github/**',
          'src/auth/**',
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
