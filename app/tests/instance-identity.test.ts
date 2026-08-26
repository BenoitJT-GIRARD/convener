/**
 * Whose series this is, and whether anything still assumes it is this one.
 *
 * Phase 10, task 3. A hundred and fifty-six occurrences across sixty-six
 * files -- `docs/` (its own specs and plans aside), `site/src/`,
 * `app/src/`, `tools/convener_ops/` and the two publishing workflows -- wrote
 * one instance's `organisation`, `short_name`, `forum_host` or `contact`
 * out in full, in prose the product ships: the e-mail a
 * speaker is invited with, the certificate a participant is sent, the
 * masthead of the cockpit, the handbook a volunteer reads. They read
 * `{{ instance.* }}` now, resolved from `config/instance.json` -- one
 * declaration, read by Python for the jobs that send, by the two builds for
 * what they emit, and injected into this bundle by `vite.config.ts`'s own
 * `define` because this code runs in a browser that can read no file.
 *
 * A test that only rendered *this* instance's identity would prove nothing:
 * every assertion would pass just as well if the values were still typed
 * into the templates. So everything below renders with a **second,
 * manifestly invented instance** and refuses anything of the first --
 * which is the shape task 5 will apply to a whole build, made here against
 * the one surface that is finished today.
 *
 * The copied handbook is checked separately and on purpose. `copy-handbook`
 * publishes the registry's own files into `public/handbook/`, from where
 * they reach a volunteer's browser -- so a page that still named this
 * organisation would reach a duplicate's volunteers verbatim, whatever the
 * repository's own sources said. It is also why the substitution happens at
 * *render* time and not at copy time: `tools/convener_ops/announce.py` reads the
 * identical files straight out of `docs/`, and its own docstring rests on
 * that being "provably the file an operator's browser fetches too, not a
 * second copy of it". Resolving on copy would have made it a second copy.
 */
import { readFileSync } from 'node:fs';
import { ONE_INSTANCE } from './one-instance';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { copyHandbook, walkAll } from '../scripts/handbook-registry.mjs';
import { walk } from '../scripts/handbook-files.mjs';
import { filledSpeaker as invented } from './data-doubles';

const ROOT = resolve(__dirname, '../..');
const DOCS = resolve(ROOT, 'docs');
const REGISTRY_SOURCE = readFileSync(
  resolve(__dirname, '../src/content/registry.ts'),
  'utf-8',
);

/** This instance, read from the one file that declares it -- never retyped
 *  here, or this suite would pass on the day somebody changed the
 *  declaration and forgot a template. */
const DECLARED = JSON.parse(
  readFileSync(resolve(ROOT, 'config/instance.json'), 'utf-8'),
).identity as Record<string, string>;

/** A second instance. Manifestly synthetic -- no real organisation, no real
 *  address, an `.test` TLD reserved by RFC 2606 precisely so that nothing
 *  here can be mistaken for somebody's real forum. */
const SECOND = {
  organisation: 'The Example Collective',
  short_name: 'TEC',
  series: 'Monthly Reading Group',
  tagline: 'A made-up series, for a test.',
  forum: 'https://forum.example.test',
  forum_host: 'forum.example.test',
  contact: 'hello@example.test',
  proposal_form: 'https://forms.example.test/propose',
  repository: 'example-collective/reading-group',
};

/** Everything of this instance that must not survive a render under the
 *  second one. The forum's host is a substring of its URL, so the URL is
 *  covered by it; the repository carries the organisation's name, likewise. */
const FIRST_INSTANCE_VALUES = [
  DECLARED.organisation,
  DECLARED.contact,
  DECLARED.forum_host ?? new URL(DECLARED.forum).host,
];

/** Load the renderer with a given identity in the bundle. `src/instance.ts`
 *  parses the define once and caches it, exactly as a real bundle does, so
 *  the module registry has to be reset rather than the cache poked at. */
async function rendererWith(identity: Record<string, string> | null) {
  vi.resetModules();
  if (identity === null) vi.stubEnv('VITE_INSTANCE_IDENTITY', '');
  else vi.stubEnv('VITE_INSTANCE_IDENTITY', JSON.stringify(identity));
  return import('../src/content/render');
}

let servedPages: string[];
beforeAll(async () => {
  servedPages = (await walk(DOCS))
    .map((p: string) => p.split('\\').join('/'))
    .filter((p: string) => p.endsWith('.md'));
});

beforeEach(() => {
  vi.unstubAllEnvs();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

function page(relative: string): string {
  return readFileSync(resolve(DOCS, relative), 'utf-8');
}

describe('the substitution vocabulary names the instance', () => {
  it('resolves every instance token to the identity the bundle was built with', async () => {
    const { substitute } = await rendererWith(SECOND);
    const out = substitute(
      'Organisation: {{ instance.organisation }}\n' +
        'Short: {{ instance.short_name }}\n' +
        'Series: {{ instance.series }}\n' +
        'Forum: {{ instance.forum }} ({{ instance.forum_host }})\n' +
        'Contact: {{ instance.contact }}\n',
      {},
    );
    expect(out).toContain('Organisation: The Example Collective');
    expect(out).toContain('Short: TEC');
    expect(out).toContain('Series: Monthly Reading Group');
    expect(out).toContain('Forum: https://forum.example.test (forum.example.test)');
    expect(out).toContain('Contact: hello@example.test');
  });

  it('resolves it with no speaker in hand, the way the Templates screen renders', async () => {
    // The organisation's name is not a field of any record: a volunteer
    // reading a template to decide whether to send it must see whose name
    // is on it, exactly as they see the consent sentence a host reads out.
    const { substituteWithoutSpeaker } = await rendererWith(SECOND);
    expect(substituteWithoutSpeaker('for {{ instance.organisation }} team')).toBe(
      'for The Example Collective team',
    );
  });

  it('leaves a token it does not have alone rather than swallowing it', async () => {
    const { substituteWithoutSpeaker } = await rendererWith(SECOND);
    expect(substituteWithoutSpeaker('{{ instance.invented }}')).toBe(
      '{{ instance.invented }}',
    );
  });

  it('refuses to render at all when the bundle was built without the identity', async () => {
    // Not a default, and not an ordinary state: a bundle with no define is a
    // broken build, and the alternative to throwing is the word "undefined"
    // in the sign-off of an e-mail to a speaker.
    const { substitute } = await rendererWith(null);
    expect(() => substitute('{{ instance.organisation }}', {})).toThrow(
      /VITE_INSTANCE_IDENTITY/,
    );
  });
});

describe('a second instance renders nothing of the first', () => {
  it('walks a tree with the toolkit in it, so an empty walk cannot pass', () => {
    expect(servedPages).toContain('toolkit/emails/invitation.md');
    expect(servedPages.length).toBeGreaterThan(30);
  });

  it.skipIf(ONE_INSTANCE)('leaves no page carrying this organisation once another one is declared', async () => {
    const { substitute } = await rendererWith(SECOND);
    const offending: string[] = [];
    for (const relative of servedPages) {
      const out = substitute(page(relative), { speaker: invented(), today: '2026-11-12' });
      for (const value of FIRST_INSTANCE_VALUES) {
        if (out.includes(value)) offending.push(`${relative}: ${value}`);
      }
    }
    expect(offending).toEqual([]);
  });

  it('leaves no unresolved marker on any page under the second identity', async () => {
    const { substitute } = await rendererWith(SECOND);
    const broken = servedPages.filter(relative => {
      const out = substitute(page(relative), { speaker: invented(), today: '2026-11-12' });
      return /«missing: [\w.]/.test(out) || out.includes('[object Object]');
    });
    expect(broken).toEqual([]);
  });

  it('actually says the second instance somewhere, so the sweep is not vacuous', async () => {
    const { substitute } = await rendererWith(SECOND);
    const naming = servedPages.filter(relative =>
      substitute(page(relative), { speaker: invented(), today: '2026-11-12' }).includes(
        SECOND.organisation,
      ),
    );
    expect(naming.length).toBeGreaterThan(15);
  });
});

describe('the handbook copied into the built bundle', () => {
  let dst: string;

  beforeEach(async () => {
    dst = await mkdtemp(join(tmpdir(), 'handbook-identity-'));
  });

  afterEach(async () => {
    await rm(dst, { recursive: true, force: true });
  });

  it.skipIf(ONE_INSTANCE)('carries the second instance once rendered, and nothing of the first', async () => {
    // The real copy step, into a scratch destination -- what actually lands
    // in `public/handbook/` and is served to a volunteer's browser.
    const { files } = await copyHandbook({
      docsDir: DOCS,
      registrySource: REGISTRY_SOURCE,
      dst,
    });
    const copied = (await walkAll(dst)).filter((p: string) => p.endsWith('.md'));
    expect(copied.length).toBeGreaterThan(30);
    expect(files).toContain('toolkit/emails/invitation.md');

    const { substitute } = await rendererWith(SECOND);
    const offending: string[] = [];
    let naming = 0;
    for (const relative of copied) {
      const raw = await readFile(join(dst, relative), 'utf-8');
      // The copied file is the source file, byte for byte: the substitution
      // happens on render, which is what keeps `announce.py` and this
      // renderer reading one artefact rather than two.
      expect(raw).toBe(page(relative));
      const out = substitute(raw, { speaker: invented(), today: '2026-11-12' });
      for (const value of FIRST_INSTANCE_VALUES) {
        if (out.includes(value)) offending.push(`${relative}: ${value}`);
      }
      if (out.includes(SECOND.organisation)) naming += 1;
    }
    expect(offending).toEqual([]);
    expect(naming).toBeGreaterThan(15);
  });
});
