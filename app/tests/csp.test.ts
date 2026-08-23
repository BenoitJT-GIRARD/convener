/**
 * `scripts/csp.mjs::cspMetaContent` -- the Content-Security-Policy this
 * project's operators' cockpit (and, on the same document, the public
 * survey route) ships as a `<meta http-equiv>` (security audit 2026-08-23,
 * M4). `vite.config.ts`'s own `cspHtmlPlugin` is what actually injects the
 * result into `app/index.html`; this suite holds the pure string-builder
 * to account directly, the same split `copy-fonts.test.ts` and its
 * siblings already use for their own `*-files.mjs` logic.
 */
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { build } from 'vite';
import { cspMetaContent } from '../scripts/csp.mjs';

const APP_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

describe('cspMetaContent', () => {
  it('ships script-src, object-src and form-action unconditionally', () => {
    const content = cspMetaContent({});
    expect(content).toContain("script-src 'self'");
    expect(content).toContain("object-src 'none'");
    expect(content).toContain("form-action 'self'");
  });

  it('admits GitHub\'s own API and nothing else when no relay is configured', () => {
    // D-13: a missing auth proxy or signup relay is an ordinary state --
    // sign-in falls back to a personal access token, the survey form
    // refuses to send, calmly. connect-src must not name an address
    // nothing will ever call.
    const content = cspMetaContent({});
    expect(content).toContain("connect-src 'self' https://api.github.com");
    expect(content).not.toContain('workers.dev');
  });

  it('adds the auth relay\'s own origin once VITE_AUTH_PROXY_URL is configured', () => {
    const content = cspMetaContent({ VITE_AUTH_PROXY_URL: 'https://auth.example.workers.dev' });
    expect(content).toContain(
      "connect-src 'self' https://api.github.com https://auth.example.workers.dev",
    );
  });

  it('adds the signup relay\'s own origin once VITE_SIGNUP_RELAY_URL is configured', () => {
    // The survey form (survey/SurveyForm.tsx), not the registration
    // island -- that one lives on a different document (site/).
    const content = cspMetaContent({
      VITE_SIGNUP_RELAY_URL: 'https://signup.example.workers.dev',
    });
    expect(content).toContain(
      "connect-src 'self' https://api.github.com https://signup.example.workers.dev",
    );
  });

  it('admits both configured origins together, in a stable order', () => {
    const content = cspMetaContent({
      VITE_AUTH_PROXY_URL: 'https://auth.example.workers.dev',
      VITE_SIGNUP_RELAY_URL: 'https://signup.example.workers.dev',
    });
    expect(content).toBe(
      "script-src 'self'; " +
        "connect-src 'self' https://api.github.com https://auth.example.workers.dev " +
        "https://signup.example.workers.dev; " +
        "object-src 'none'; " +
        "form-action 'self'",
    );
  });

  it('treats a blank environment value the same as an absent one', () => {
    const content = cspMetaContent({ VITE_AUTH_PROXY_URL: '   ', VITE_SIGNUP_RELAY_URL: '' });
    expect(content).toContain("connect-src 'self' https://api.github.com;");
  });

  it('never carries a directive a <meta> delivery ignores', () => {
    // Closing the class, not just today's instance: this fails the
    // moment any of these tokens appears in the policy this project
    // ships, regardless of which directive introduces it or why.
    const content = cspMetaContent({
      VITE_AUTH_PROXY_URL: 'https://auth.example.workers.dev',
      VITE_SIGNUP_RELAY_URL: 'https://signup.example.workers.dev',
    });
    for (const directive of ['frame-ancestors', 'report-uri', 'report-to', 'sandbox']) {
      expect(content).not.toContain(directive);
    }
  });
});

describe('the real built app/dist/index.html', () => {
  // A unit test on cspMetaContent proves the string-builder is right; it
  // says nothing about whether vite.config.ts actually wires it in.
  // `cspHtmlPlugin` is what does that -- this runs the real production
  // build (the same one `npm run build` runs, to a throwaway directory
  // rather than app/dist itself) and reads the artefact it writes,
  // exactly the way tools/tests/test_site.py proves the site's own CSP
  // against the real built HTML rather than only against a template
  // string. No network: `vite build` here reads only this checkout's own
  // already-installed dependencies.
  it('carries the Content-Security-Policy meta tag, injected as early as possible', async () => {
    const outDir = mkdtempSync(join(tmpdir(), 'convener-app-csp-build-'));
    try {
      await build({
        root: APP_ROOT,
        configFile: join(APP_ROOT, 'vite.config.ts'),
        logLevel: 'silent',
        build: { outDir, write: true, emptyOutDir: true },
      });
      const html = readFileSync(join(outDir, 'index.html'), 'utf8');
      const cspAt = html.indexOf('Content-Security-Policy');
      const charsetAt = html.indexOf('charset=');
      const scriptAt = html.indexOf('<script');
      expect(cspAt, html).toBeGreaterThan(-1);
      // Order matters, not just presence: a <meta> CSP only governs what
      // the parser reaches *after* it -- placed later than the app's own
      // <script>/<link rel=stylesheet>, it would protect nothing real.
      expect(cspAt, html).toBeLessThan(scriptAt);
      expect(cspAt, html).toBeLessThan(charsetAt);
    } finally {
      rmSync(outDir, { recursive: true, force: true });
    }
  }, 30_000);
});
