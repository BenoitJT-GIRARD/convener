/**
 * Demo mode reaches no host but the one that served it.
 *
 * Demo mode lets somebody drive the cockpit with no GitHub account: the
 * state lives in memory, an edit is applied there, and nothing is written
 * anywhere. Before this file that promise rested on guards written one at
 * a time, in the four places that happened to need one: `DataContext`
 * short-circuits its read and both its writes, `AuthContext` returns
 * before validating a stored token, `useRole` returns before looking a
 * role up, and the sign-in screen is never rendered at all because demo
 * mode already holds a token. Nothing connected the four, and a fifth
 * path added next month would have been held by nothing whatever -- with
 * the failure silent in the worst way: a demonstration quietly talking to
 * GitHub, or quietly writing to it. It is the shape this project keeps
 * finding. The branch invariant was true by thirteen coincidences until
 * something pinned it; the instance boundary by five scattered constants
 * until something pinned that.
 *
 * What is actually held
 * ---------------------
 * Not "in demo mode nothing is requested". That is false today, however
 * plausible it sounds. Five modules in this bundle
 * put a request on the wire, not four, and the fifth -- `content/fetch.ts`,
 * which loads the handbook markdown that ships inside the build -- is
 * behind no guard at all and must not be: those reads are part of the
 * document, carry no credential and change nothing. The last test in this
 * file watches the whole application do exactly that in demo mode, so the
 * claim is written down rather than assumed. The rule that survives being
 * read twice is
 *
 *     in demo mode this cockpit reads only from the origin that served
 *     it, and writes nothing at all.
 *
 * Two clauses come out of that, and they are held in different ways
 * because only one of them is decidable from the text of a program.
 *
 * 1. **One door.** `src/net/request.ts` is the only module in the graph
 *    reachable from `src/main.tsx` that touches a request primitive, and
 *    it applies the rule above. The set of modules swept is *derived*
 *    from the import graph, never listed: a module added tomorrow is in
 *    the sweep because the graph reaches it, and the islands under
 *    `src/islands/` are out of it because the graph does not -- they are
 *    separate bundles from separate entry points on the public site, with
 *    no demo mode to respect.
 *
 * 2. **The door refuses.** `demoRefusal` is exercised directly, and the
 *    whole application is rendered in demo mode against a recording
 *    stand-in for the platform primitive, so what demo mode does on the
 *    wire is written down rather than assumed.
 *
 * What this cannot see -- stated here rather than left to be discovered
 * ---------------------------------------------------------------------
 * - **A module outside the graph.** Anything the walk cannot reach is not
 *   swept. The walk follows relative specifiers only, and the tests below
 *   refuse a specifier it failed to resolve and a dynamic `import()` whose
 *   argument is not a literal, so an unreachable subtree fails loudly
 *   rather than shrinking the sweep in silence. A **bare** specifier is a
 *   different matter: `react-markdown`, `react-router-dom`, `js-yaml` and
 *   the rest are listed by the walk and then not followed. A dependency
 *   that requests something on its own is invisible here, and the only
 *   thing standing in front of it is the `connect-src` of the
 *   Content-Security-Policy (`scripts/csp.mjs`, `tests/csp.test.ts`).
 *
 * - **The primitive under another name.** The patterns below match the
 *   ordinary spellings -- a call, and a reference through `globalThis`,
 *   `window` or `self`. A handle taken through a computed property
 *   (`globalThis['fet' + 'ch']`) is not matched by any of them. `eval` and
 *   `new Function` are not matched either; the policy's `script-src
 *   'self'` is what refuses those, not this file.
 *
 * - **Markup that loads a subresource.** An `<img src={speaker.photo_url}>`
 *   added to a screen would have the browser contact a third party in demo
 *   mode, and no request primitive appears anywhere in the source. The
 *   cockpit renders no such element today. The control for that class is
 *   the policy, not a sweep -- and when this file was written the policy
 *   this application ships had no `default-src` and no `img-src`, so
 *   nothing at all was holding it. That gap was the reason this paragraph
 *   existed, and it is closed: `scripts/csp.mjs` now emits
 *   `default-src 'none'` with `img-src 'self'` beside it, so the browser
 *   refuses that portrait rather than fetching it. This paragraph stays
 *   because the *sweep* still cannot see such an element -- what changed
 *   is that something else can.
 *
 * - **Reachability.** "Unreachable in demo mode" is not something a static
 *   check decides; a call sits behind conditions, callbacks and a router.
 *   That is exactly why the property is held by *ownership* -- one module
 *   makes every request -- rather than by an argument about which of the
 *   others can be reached.
 *
 * - **The future.** Nothing here reads git history or predicts a commit.
 *   It describes the working tree it is run against, and nothing else.
 */
import { readFileSync, existsSync, statSync } from 'node:fs';
import { dirname, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { App } from '../../src/App';
import { DemoModeRefused, demoRefusal, request } from '../../src/net/request';

const APP_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const SRC = resolve(APP_ROOT, 'src');

/** Where the cockpit starts. `index.html` names this file and nothing
 *  else; the three island bundles name their own entry points in
 *  `vite.config.ts`, which is why they are not here. */
const ENTRY = 'main.tsx';

/** The one module allowed to touch a request primitive. A rule about a
 *  single owner has to name its owner somewhere -- what matters is that
 *  the set of modules *checked against* it is derived from the tree and
 *  not written down. */
const DOOR = 'net/request.ts';

// ------------------------------------------------------------------ //
// The graph
// ------------------------------------------------------------------ //

/** `import`/`export … from '…'`, including the side-effect form with no
 *  clause at all (`import './index.css'`) and the literal dynamic form.
 *  The clause is matched without quotes or parentheses in it so it can
 *  never run past the end of one statement into the next. */
const SPECIFIER =
  /(?:^|[\s;{}()=,])(?:import|export)\s*(?:[^'"()]*?\sfrom\s*)?['"]([^'"]+)['"]|\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)/gm;

/** A dynamic import whose argument is *not* a literal: the walk cannot
 *  follow it, so it must never appear rather than be waved through. */
const COMPUTED_IMPORT = /\bimport\s*\(\s*(?!['"])/g;

interface Graph {
  /** Every module the entry point reaches, relative to `src/`, `/`-joined,
   *  with the text it was read from -- read once here because the sweep is
   *  run sixty-odd times over the same tree below to prove that it bites. */
  texts: Map<string, string>;
  /** The same keys, sorted, for assertions that read as a list. */
  modules: string[];
  /** Relative specifiers that resolved to no file: a hole in the walk. */
  unresolved: Array<{ from: string; specifier: string }>;
  /** Dynamic imports the walk could not follow. */
  computed: string[];
  /** Bare specifiers, recorded and deliberately not followed. */
  external: string[];
}

function asModule(file: string): string {
  return relative(SRC, file).split(sep).join('/');
}

function resolveSpecifier(fromFile: string, specifier: string): string | null {
  const base = resolve(dirname(fromFile), specifier);
  const candidates = [
    base,
    `${base}.ts`,
    `${base}.tsx`,
    resolve(base, 'index.ts'),
    resolve(base, 'index.tsx'),
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
  }
  return null;
}

function walk(): Graph {
  const seen = new Map<string, string>();
  const unresolved: Array<{ from: string; specifier: string }> = [];
  const computed: string[] = [];
  const external = new Set<string>();
  const pending = [resolve(SRC, ENTRY)];

  while (pending.length > 0) {
    const file = pending.pop()!;
    const module = asModule(file);
    if (seen.has(module)) continue;
    const text = readFileSync(file, 'utf8');
    seen.set(module, text);
    if (!/\.(ts|tsx)$/.test(file)) continue;

    COMPUTED_IMPORT.lastIndex = 0;
    if (COMPUTED_IMPORT.test(text)) computed.push(module);

    SPECIFIER.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = SPECIFIER.exec(text)) !== null) {
      const specifier = match[1] ?? match[2];
      if (!specifier.startsWith('.')) {
        external.add(specifier);
        continue;
      }
      const target = resolveSpecifier(file, specifier);
      if (target === null) unresolved.push({ from: module, specifier });
      else pending.push(target);
    }
  }

  return {
    texts: seen,
    modules: [...seen.keys()].sort(),
    unresolved,
    computed,
    external: [...external].sort(),
  };
}

// ------------------------------------------------------------------ //
// The sweep
// ------------------------------------------------------------------ //

/**
 * The spellings that put a request on the wire.
 *
 * Nothing is stripped before these are applied -- not comments, not
 * string literals. A tokeniser that mishandles one apostrophe in one line
 * of JSX turns this sweep silently blind, which is precisely the failure
 * it exists to prevent; `no-third-party-fonts.test.ts` already paid for
 * that lesson once, on its own tree. The cost of the trade is that a
 * comment which needs to name the primitive spells it without its
 * parentheses. That is a word; a blind sweep is the whole file.
 */
const PRIMITIVES: ReadonlyArray<{ name: string; pattern: RegExp }> = [
  { name: 'a call to fetch', pattern: /\bfetch\s*\(/ },
  { name: 'a handle on fetch', pattern: /\b(?:globalThis|window|self)\s*\.\s*fetch\b/ },
  { name: 'XMLHttpRequest', pattern: /\bXMLHttpRequest\b/ },
  { name: 'WebSocket', pattern: /\bWebSocket\b/ },
  { name: 'EventSource', pattern: /\bEventSource\b/ },
  { name: 'sendBeacon', pattern: /\bsendBeacon\b/ },
  { name: 'a worker', pattern: /\b(?:new\s+Worker|SharedWorker|serviceWorker)\b/ },
];

interface Reach {
  module: string;
  primitive: string;
}

/** Every module in the graph that touches a request primitive, the door
 *  included -- the caller decides what to do about the door, so that the
 *  sweep can also be asked whether it sees the door at all. */
function modulesThatReachTheNetwork(texts: Map<string, string>): Reach[] {
  const found: Reach[] = [];
  for (const [module, text] of texts) {
    for (const { name, pattern } of PRIMITIVES) {
      if (pattern.test(text)) found.push({ module, primitive: name });
    }
  }
  return found.sort((a, b) => a.module.localeCompare(b.module));
}

const graph = walk();
const source = graph.texts;

// ------------------------------------------------------------------ //
// The graph is the one this sweep believes it is
// ------------------------------------------------------------------ //

describe("the cockpit's module graph", () => {
  it('reaches the modules whose network behaviour this phase is about', () => {
    // Membership, never the whole list: restating the list would make
    // the sweep below a second copy of it. These nine are asserted
    // because a walk that missed any one of them would leave the sweep
    // green for the wrong reason -- the five modules that really do put a
    // request on the wire, the two entry points that reach them, the
    // module the flag itself lives in, and the door.
    for (const module of [
      ENTRY,
      'App.tsx',
      'auth/api.ts',
      'auth/role.ts',
      'auth/device.ts',
      'github/client.ts',
      'content/fetch.ts',
      'data/demo.ts',
      DOOR,
    ]) {
      expect(graph.modules, `${module} is not in the graph`).toContain(module);
    }
  });

  it('leaves no relative import unresolved and no dynamic import unfollowed', () => {
    // A hole in the walk shrinks the sweep in silence. Both of these
    // failing loudly is what keeps "no offender found" from meaning
    // "nothing was looked at".
    expect(graph.unresolved).toEqual([]);
    expect(graph.computed).toEqual([]);
  });

  it('does not reach the islands, because they are built from their own entry points', () => {
    // Not an exemption: `vite.config.ts` builds `src/islands/*/main.tsx`
    // as three separate bundles for three public pages that have no demo
    // mode. They are outside this rule because the graph puts them
    // outside it, and the day the cockpit imports one, it is inside.
    expect(graph.modules.filter(m => m.startsWith('islands/'))).toEqual([]);
  });

  it('records the dependencies it does not follow', () => {
    // Named so the gap is on the record: a package that requests
    // something of its own accord is invisible to the sweep, and the
    // Content-Security-Policy is what stands in front of it.
    expect(graph.external).toContain('react');
    expect(graph.external.every(s => !s.startsWith('.'))).toBe(true);
  });
});

// ------------------------------------------------------------------ //
// Clause 1 -- one door
// ------------------------------------------------------------------ //

describe('one module reaches the network for the whole cockpit', () => {
  it('finds a request primitive nowhere but the door', () => {
    const trespassers = modulesThatReachTheNetwork(source).filter(r => r.module !== DOOR);
    expect(
      trespassers,
      `Every outbound request in the cockpit goes through src/${DOOR}, which is ` +
        'where demo mode is enforced -- import `request` from there instead. If ' +
        'the line above is a comment, spell the primitive without its parentheses.',
    ).toEqual([]);
  });

  it('finds one in the door itself', () => {
    // Non-vacuity against real production text rather than a fixture:
    // if the patterns had rotted, this is the assertion that notices.
    const atTheDoor = modulesThatReachTheNetwork(source).filter(r => r.module === DOOR);
    expect(atTheDoor.map(r => r.primitive)).toContain('a call to fetch');
  });

  it('would catch a request planted in any module of the graph', () => {
    // The sharpest form of non-vacuity available here. Not "the pattern
    // matches a string I wrote": the real sweep is run once per module,
    // over the real tree, with that one module's text carrying an added
    // call -- so a module the sweep somehow skipped shows up by name.
    const blind: string[] = [];
    for (const module of graph.modules) {
      if (module === DOOR) continue;
      const planted = new Map(source);
      planted.set(module, `${source.get(module)!}\nawait fetch('https://api.github.com/user');\n`);
      const caught = modulesThatReachTheNetwork(planted).some(r => r.module === module);
      if (!caught) blind.push(module);
    }
    expect(blind).toEqual([]);
    expect(graph.modules.length).toBeGreaterThan(40);
  });

  it('looks for no spelling it cannot find', () => {
    // A pattern that matches nothing is a line of the table nobody would
    // ever notice was dead.
    const samples: Record<string, string> = {
      'a call to fetch': "await fetch('/x');",
      'a handle on fetch': 'const go = globalThis.fetch;',
      XMLHttpRequest: 'const x = new XMLHttpRequest();',
      WebSocket: "const s = new WebSocket('wss://example.org');",
      EventSource: "const e = new EventSource('/stream');",
      sendBeacon: "navigator.sendBeacon('/log', '1');",
      'a worker': "const w = new Worker('/w.js');",
    };
    for (const { name, pattern } of PRIMITIVES) {
      expect(samples[name], `no sample for ${name}`).toBeDefined();
      expect(pattern.test(samples[name]), `${name} matches nothing`).toBe(true);
    }
  });

  it('does not fire on the names the cockpit legitimately uses', () => {
    // The mirror of the test above. A sweep that flagged `fetchContent`
    // or `fetchState` would be a sweep somebody disables.
    const innocent = [
      'const text = await fetchContent(key, token);',
      'setS(await fetchState(token));',
      'import { fetchContent } from "./fetch";',
      '// Nothing to fetch yet: auth is still resolving a stored credential.',
    ].join('\n');
    expect(modulesThatReachTheNetwork(new Map([['sample.ts', innocent]]))).toEqual([]);
  });
});

// ------------------------------------------------------------------ //
// Clause 2 -- the door refuses
// ------------------------------------------------------------------ //

const HERE = 'https://example.org/cockpit/app/';

describe('demoRefusal', () => {
  it('lets a read of the origin that served the page through', () => {
    expect(demoRefusal('/cockpit/app/docs/handbook/start-here/index.md', 'GET', HERE)).toBeNull();
    expect(demoRefusal('docs/handbook/start-here/index.md', 'HEAD', HERE)).toBeNull();
    expect(demoRefusal('https://example.org/elsewhere', 'get', HERE)).toBeNull();
  });

  it('refuses any other origin, whatever the method', () => {
    expect(demoRefusal('https://api.github.com/user', 'GET', HERE)).toContain(
      'https://api.github.com',
    );
    expect(demoRefusal('https://auth.example.workers.dev/login/device/code', 'POST', HERE))
      // The relay is refused for being another origin, before the method
      // is ever considered.
      .toContain('https://auth.example.workers.dev');
  });

  it('refuses a write even to the origin that served the page', () => {
    expect(demoRefusal('/cockpit/app/anything', 'PUT', HERE)).toContain('refused a PUT');
    expect(demoRefusal('/cockpit/app/anything', 'post', HERE)).toContain('refused a POST');
  });

  it('refuses an address it cannot read, rather than guessing at it', () => {
    expect(demoRefusal('http://[', 'GET', HERE)).toContain('could not read');
    expect(demoRefusal('/fine', 'GET', 'not an address')).toContain('could not read');
  });
});

describe('request', () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    localStorage.clear();
  });

  it('is the platform primitive and nothing else when demo mode is off', async () => {
    const seen: Array<[string, string | undefined]> = [];
    vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
      seen.push([url, init?.method]);
      return Promise.resolve(new Response('ok', { status: 200 }));
    });
    const response = await request('https://api.github.com/user', { method: 'GET' });
    expect(await response.text()).toBe('ok');
    expect(seen).toEqual([['https://api.github.com/user', 'GET']]);
  });

  it('never reaches the primitive at all for a refused request', async () => {
    localStorage.setItem('convener.demo', '1');
    let called = 0;
    vi.stubGlobal('fetch', () => {
      called += 1;
      return Promise.resolve(new Response('', { status: 200 }));
    });
    await expect(request('https://api.github.com/user')).rejects.toBeInstanceOf(DemoModeRefused);
    await expect(request('/docs/handbook/x.md', { method: 'PUT' })).rejects.toBeInstanceOf(
      DemoModeRefused,
    );
    expect(called).toBe(0);
  });

  it('still reads the page it was served from, in demo mode', async () => {
    localStorage.setItem('convener.demo', '1');
    vi.stubGlobal('fetch', () => Promise.resolve(new Response('# page', { status: 200 })));
    const response = await request('/docs/handbook/start-here/index.md');
    expect(await response.text()).toBe('# page');
  });
});

// ------------------------------------------------------------------ //
// And what the whole application actually does on the wire
// ------------------------------------------------------------------ //

describe('the cockpit rendered in demo mode', () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('convener.demo', '1');
  });
  afterEach(() => {
    localStorage.clear();
    window.location.hash = '';
  });

  it('requests its own handbook and nothing else', async () => {
    const asked: string[] = [];
    vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
      asked.push(`${(init?.method ?? 'GET').toUpperCase()} ${url}`);
      return Promise.resolve(new Response('# demo\n', { status: 200 }));
    });

    // The handbook route, because it is the one screen in the cockpit
    // that loads anything at all in demo mode -- rendering the default
    // route would produce an empty list of requests and prove nothing.
    window.location.hash = '#/handbook';
    render(<App />);
    await waitFor(() => expect(asked.length).toBeGreaterThan(0));

    const origin = new URL(window.location.href).origin;
    for (const call of asked) {
      const [method, url] = call.split(' ');
      expect(method, call).toBe('GET');
      expect(new URL(url, window.location.href).origin, call).toBe(origin);
    }
    // Non-vacuity for this test in particular: the assertions above are
    // satisfied by an empty list, so the list is pinned to the one thing
    // demo mode really does ask for.
    expect(asked.some(c => c.includes('/docs/handbook/'))).toBe(true);
  });
});
