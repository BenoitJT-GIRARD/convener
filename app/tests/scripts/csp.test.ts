/**
 * `scripts/csp.mjs::cspMetaContent` -- the Content-Security-Policy this
 * project's operators' cockpit ships as a `<meta http-equiv>`.
 * `vite.config.ts`'s own `cspHtmlPlugin` is what
 * actually injects the result into `app/index.html`; this suite holds the
 * pure string-builder to account directly, the same split
 * `copy-fonts.test.ts` and its siblings already use for their own
 * `*-files.mjs` logic.
 *
 * The last public route this document carried (the
 * post-event survey) moved onto its own island on `site/src/survey.njk` --
 * `connect-src` here no longer admits the signup relay's origin at all;
 * see `tools/tests/repository/test_site.py`'s own
 * `test_content_security_policys_connect_src_admits_the_configured_signup_relay`
 * for the policy that page ships under now (built from
 * `site/src/_data/csp.js`, unaffected by this file), and `csp.mjs`'s own
 * module comment for the reasoning.
 */
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { build, createServer } from 'vite';
import { cspMetaContent, devCspMetaContent } from '../../scripts/csp.mjs';

const APP_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const CONFIG_FILE = join(APP_ROOT, 'vite.config.ts');

/** The `content` of the `<meta http-equiv="Content-Security-Policy">` in a
 *  document, as a map of directive name to its source list -- read out of
 *  the real HTML rather than out of the builder, so what is asserted is
 *  what a browser would actually be handed. */
function policyOf(html: string): Map<string, string> {
  const match = html.match(
    /<meta http-equiv="Content-Security-Policy" content="([^"]*)"/,
  );
  expect(match, `no Content-Security-Policy meta in:\n${html.slice(0, 400)}`).not.toBeNull();
  const content = match![1].replaceAll('&#39;', "'");
  return new Map(
    content.split('; ').map((part) => {
      const [name, ...sources] = part.split(' ');
      return [name, sources.join(' ')] as const;
    }),
  );
}

/** Every `<script>` in a document that carries its code inline rather than
 *  fetching it -- the class `script-src 'self'` alone refuses. */
function inlineScripts(html: string): string[] {
  return [...html.matchAll(/<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)<\/script>/g)].map(
    (m) => m[1],
  );
}

describe('cspMetaContent', () => {
  it('ships script-src, object-src and form-action unconditionally', () => {
    const content = cspMetaContent({});
    expect(content).toContain("script-src 'self'");
    expect(content).toContain("object-src 'none'");
    expect(content).toContain("form-action 'self'");
  });

  it('leaves no class of subresource to the browser\'s own default', () => {
    // A real defect, found late: four directives, not one of them a
    // fallback, so an image, a frame, a font, a stylesheet, a media file
    // or a worker was admitted from any origin at all -- on a document
    // whose demonstration a stranger drives. Held as a property of the
    // policy rather than as a list of nine expected strings: what matters
    // is that nothing is left to the browser's own default, which is
    // "allow", and that nothing but `connect-src` names a host.
    const directives = new Map(
      cspMetaContent({}).split('; ').map(part => {
        const [name, ...sources] = part.split(' ');
        return [name, sources.join(' ')] as const;
      }),
    );
    expect(directives.get('default-src')).toBe("'none'");
    for (const name of ['script-src', 'style-src', 'img-src', 'font-src']) {
      expect(directives.get(name), `${name} is not named`).toBe("'self'");
    }
    // Neither of these two falls back to `default-src`, so neither is
    // covered by it however strict it is.
    expect(directives.get('base-uri')).toBe("'none'");
    expect(directives.get('form-action')).toBe("'self'");
    for (const [name, sources] of directives) {
      if (name === 'connect-src') continue;
      expect(sources, `${name} admits ${sources}`).toMatch(/^'(self|none)'$/);
    }
  });

  it('admits GitHub\'s own API and nothing else when no relay is configured', () => {
    // D-13: a missing auth proxy is an ordinary state -- sign-in falls
    // back to a personal access token. connect-src must not name an
    // address nothing will ever call.
    const content = cspMetaContent({});
    expect(content).toContain("connect-src 'self' https://api.github.com");
    expect(content).not.toContain('workers.dev');
  });

  it('adds the auth relay\'s own origin once VITE_AUTH_PROXY_URL is configured', () => {
    const content = cspMetaContent({ VITE_AUTH_PROXY_URL: 'https://auth.example.workers.dev' });
    expect(content).toBe(
      "default-src 'none'; " +
        "script-src 'self'; " +
        "style-src 'self'; " +
        "img-src 'self'; " +
        "font-src 'self'; " +
        "connect-src 'self' https://api.github.com https://auth.example.workers.dev; " +
        "base-uri 'none'; " +
        "object-src 'none'; " +
        "form-action 'self'",
    );
  });

  it('never admits the signup relay\'s origin, configured or not', () => {
    // The post-event survey (`islands/survey/SurveyForm.tsx`, the one caller
    // this bundle ever had for VITE_SIGNUP_RELAY_URL) moved onto its own
    // island on site/src/survey.njk -- nothing left in this document
    // posts to the signup relay, so this variable must never reach this
    // policy's connect-src at all, configured or not.
    const content = cspMetaContent({
      VITE_AUTH_PROXY_URL: 'https://auth.example.workers.dev',
      VITE_SIGNUP_RELAY_URL: 'https://signup.example.workers.dev',
    });
    expect(content).not.toContain('signup.example.workers.dev');
    expect(content).toBe(
      "default-src 'none'; " +
        "script-src 'self'; " +
        "style-src 'self'; " +
        "img-src 'self'; " +
        "font-src 'self'; " +
        "connect-src 'self' https://api.github.com https://auth.example.workers.dev; " +
        "base-uri 'none'; " +
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

describe('devCspMetaContent', () => {
  // `transformIndexHtml` runs on the development server too, so
  // the shipped policy was being injected there -- and `script-src 'self'`
  // refuses `@vitejs/plugin-react`'s inline React Refresh preamble, so
  // `npm run dev` served a blank page from the day the policy landed. See
  // `scripts/csp.mjs`'s own comment for why the development server carries
  // a policy of its own rather than none at all.
  it('loosens exactly two directives, and only by admitting inline', () => {
    const env = { VITE_AUTH_PROXY_URL: 'https://auth.example.workers.dev' };
    const shipped = new Map(
      cspMetaContent(env).split('; ').map((part) => {
        const [name, ...sources] = part.split(' ');
        return [name, sources.join(' ')] as const;
      }),
    );
    const development = new Map(
      devCspMetaContent(env).split('; ').map((part) => {
        const [name, ...sources] = part.split(' ');
        return [name, sources.join(' ')] as const;
      }),
    );
    expect([...development.keys()]).toEqual([...shipped.keys()]);
    const loosened: string[] = [];
    for (const [name, sources] of development) {
      if (sources === shipped.get(name)) continue;
      loosened.push(name);
      expect(sources).toBe(`${shipped.get(name)} 'unsafe-inline'`);
    }
    expect(loosened).toEqual(['script-src', 'style-src']);
  });

  it('still refuses a third party everywhere the shipped policy does', () => {
    // The whole reason this exists rather than `apply: 'build'`: a
    // developer who adds a third-party image or an external script must
    // meet the refusal in the one place a violation is actually read.
    const development = new Map(
      devCspMetaContent({}).split('; ').map((part) => {
        const [name, ...sources] = part.split(' ');
        return [name, sources.join(' ')] as const;
      }),
    );
    expect(development.get('default-src')).toBe("'none'");
    for (const name of ['img-src', 'font-src']) {
      expect(development.get(name), `${name} is loosened`).toBe("'self'");
    }
    // `'unsafe-inline'` admits inline code; it never admits a host, so an
    // external script is refused in development exactly as it ships.
    expect(development.get('script-src')).toBe("'self' 'unsafe-inline'");
    expect(development.get('connect-src')).toBe("'self' https://api.github.com");
  });

  it('is never what the shipped policy is', () => {
    expect(cspMetaContent({})).not.toContain('unsafe');
  });
});

describe('the real development document', () => {
  // The property that actually broke, asserted on the real, committed
  // `vite.config.ts` driven by Vite's own development server rather than
  // on the string-builder: *this document's own policy admits the
  // scripts this document contains*. A unit test on `devCspMetaContent`
  // cannot see the preamble at all -- it is another plugin's injection
  // into the same HTML, which is exactly why nobody noticed.
  //
  // `middlewareMode` so no HTTP server is started at all: this is Vite's
  // own transform pipeline, run in process, and no test here may open a
  // socket to anywhere. `hmr` is left on and given `port: 0` rather than
  // turned off, and that is not incidental -- `@vitejs/plugin-react`
  // injects the preamble only when hot reloading is enabled, so `hmr:
  // false` here would make this test pass by removing the very thing it
  // exists to check (tried first, and it did). `port: 0` lets the
  // operating system pick the hot-reload socket's own port instead of the
  // fixed 24678 a runner might already have busy, and `server.close()`
  // takes it down again.
  it("admits every inline script the react plugin injects into it", async () => {
    const server = await createServer({
      root: APP_ROOT,
      configFile: CONFIG_FILE,
      logLevel: 'silent',
      server: { middlewareMode: true, hmr: { port: 0 } },
    });
    let html: string;
    try {
      html = await server.transformIndexHtml(
        '/index.html',
        readFileSync(join(APP_ROOT, 'index.html'), 'utf8'),
      );
    } finally {
      await server.close();
    }
    const inline = inlineScripts(html);
    expect(inline.length, html).toBeGreaterThan(0);
    expect(inline.join('\n')).toContain('injectIntoGlobalHook');
    const policy = policyOf(html);
    expect(policy.get('script-src'), 'the preamble would be refused').toContain(
      "'unsafe-inline'",
    );
    // Loosened, not absent: the directives that catch a third party are
    // the reason the development server carries a policy at all.
    expect(policy.get('img-src')).toBe("'self'");
    expect(policy.get('default-src')).toBe("'none'");
  }, 30_000);
});

describe('the real built app/dist/index.html', () => {
  // A unit test on cspMetaContent proves the string-builder is right; it
  // says nothing about whether vite.config.ts actually wires it in.
  // `cspHtmlPlugin` is what does that -- this runs the real production
  // build (the same one `npm run build` runs, to a throwaway directory
  // rather than app/dist itself) and reads the artefact it writes,
  // exactly the way tools/tests/repository/test_site.py proves the site's own CSP
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
      // The development server's own relaxations must not have
      // followed the plugin into a build. Asserted on the artefact and on
      // both halves of the reason it is safe there -- the policy names no
      // `'unsafe-inline'`, and the document carries no inline script for
      // one to have been needed by.
      expect(policyOf(html).get('script-src')).toBe("'self'");
      expect(inlineScripts(html)).toEqual([]);
    } finally {
      rmSync(outDir, { recursive: true, force: true });
    }
  }, 30_000);
});
