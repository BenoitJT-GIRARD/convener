/**
 * The one place a JavaScript or TypeScript source names an instance path.
 *
 * `declarations/boundary.yml` declares which paths belong to the instance.
 * `app/scripts/instance-paths.mjs` turns each of them into a name for the
 * cockpit's build, `app/src/paths.ts` carries the same values into the
 * browser through `vite.config.ts`'s own `define`, and every other module
 * builds the files it touches out of those names. This module holds the
 * third of those three statements: it walks every source the cockpit and
 * the showcase ship and fails on one that writes an instance path out in
 * a string of its own, with the list of paths it refuses read from the
 * declaration at run time.
 *
 * `tools/tests/declaration/test_paths.py` is the same sweep over the Python package,
 * and the rule below is that rule's clause for clause.
 *
 * **Where this lives.** In the cockpit's suite, because the distinction
 * the rule rests on needs a parser for the language it is reading, and
 * `typescript` is already a dependency here. The Python suite can read
 * the declaration and walk the tree, and over `.ts`, `.tsx` and `.mjs` it
 * would be reading them with a regular expression, which cannot tell a
 * JSDoc line from a template literal. The sweep covers `site/` from here
 * for the same reason: this is where a parser for those files is.
 *
 * **What counts as writing a path out.** A string whose value is, or
 * begins with, a declared instance path -- `'instance/data/config.yml'`,
 * `'instance/public-data/registration-routing.json'` -- a string that is a
 * declared directory carrying the slash the declaration writes it with
 * (`'instance/data/'`), and a `join` or `resolve` call that spells one segment by
 * segment: `resolve(root, 'instance', 'keys', 'events')`. Segments are joined the
 * way `resolve` joins them, with
 * leading `.` and `..` dropped, so a path built from a directory above
 * the one the call starts in is caught in the position it occupies.
 *
 * **A bare word is a path only where the code uses it as one.** A word
 * with no separator in it is refused inside a `join` or `resolve` chain
 * and admitted everywhere else. `'data'` and `'keys'` are ordinary words,
 * and a declaration handing over a bare one would need an exemption for
 * each place it means something else. None of the four entries is a bare
 * word today -- every one of them is under `instance/` or under `docs/` --
 * so the clause guards a shape the declaration does not currently have,
 * and it is kept because the declaration is free to hand over a single
 * top-level name again.
 *
 * **A comment or a JSDoc block may name a path, and this sweep leaves it
 * alone.** They are not nodes of the syntax tree, so walking that tree
 * reads code and nothing else. Prose is where the argument for a path
 * lives, and an argument that cannot quote the path it is about is worth
 * less than the duplication it saves. Most of this repository's mentions
 * of an instance path in these directories are prose of that kind.
 *
 * **What this does not cover.** `app/tests/` builds instance paths in
 * fixtures and doubles, `docs/` and the workflows name them in their own
 * languages, and `site/src/*.njk` has a `/data/` route of its own that
 * has nothing to do with this directory. What this fixes is the part of
 * the tree that is one import away from a name.
 */
import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import ts from 'typescript';
import yaml from 'js-yaml';
import { BOUNDARY_PATH, handedFromData } from '../src/settings/declaration';

const ROOT = resolve(__dirname, '..', '..');

/** The trees this sweep reads: every source the cockpit and the showcase
 *  ship, tests aside. */
const SWEPT = [
  'app/src',
  'app/scripts',
  'app/vite.config.ts',
  'site/.eleventy.js',
  'site/scripts',
  'site/src/_data',
];

/** The files allowed to write an instance path out. They are where the
 *  names are. */
const HOMES = new Set([
  'app/src/paths.ts',
  'app/scripts/instance-paths.mjs',
  'app/scripts/instance-paths.d.mts',
]);

const EXTENSIONS = ['.ts', '.tsx', '.mts', '.cts', '.js', '.jsx', '.mjs', '.cjs'];

/** The paths `declarations/boundary.yml` hands to the instance, read now. The
 *  declaration's own list, parsed by the reader that owns its format.
 *  Adding an entry there adds a refusal here on the same commit. */
export function declaredInstancePaths(): string[] {
  const text = readFileSync(resolve(ROOT, BOUNDARY_PATH), 'utf8');
  return handedFromData(yaml.load(text)).map(entry => entry.path);
}

const DECLARED = declaredInstancePaths();

/** The declared instance path `value` writes out, if it writes one. */
function offence(value: string, asPath: boolean): string | null {
  const normalised = value.replace(/\\/g, '/');
  const written = normalised.replace(/\/+$/, '');
  if (written === '') return null;
  for (const declared of DECLARED) {
    if (normalised === declared) return declared;
    const name = declared.replace(/\/+$/, '');
    if (written === name && (asPath || name.includes('/'))) return declared;
    if (declared.endsWith('/') && written.startsWith(`${name}/`)) return declared;
  }
  return null;
}

type Textual = ts.StringLiteralLike | ts.TemplateLiteralLikeNode | ts.JsxText;

/** Whether `node` carries text the code itself holds. */
function textual(node: ts.Node): node is Textual {
  return (
    ts.isStringLiteral(node) ||
    ts.isNoSubstitutionTemplateLiteral(node) ||
    ts.isTemplateHead(node) ||
    ts.isTemplateMiddle(node) ||
    ts.isTemplateTail(node) ||
    ts.isJsxText(node)
  );
}

/** A `join` or `resolve` call, whichever way its module was imported. */
function pathCall(node: ts.Node): ts.CallExpression | null {
  if (!ts.isCallExpression(node)) return null;
  const callee = node.expression;
  let name: string | null = null;
  if (ts.isIdentifier(callee)) name = callee.text;
  else if (ts.isPropertyAccessExpression(callee) && ts.isIdentifier(callee.name)) {
    name = callee.name.text;
  }
  return name === 'join' || name === 'resolve' ? node : null;
}

/**
 * The run of string arguments a path call ends in.
 *
 * A call rooted in something this cannot read -- a variable, another
 * call -- contributes the segments to its right, which is the suffix a
 * path joined onto it would end in.
 */
function trailingSegments(call: ts.CallExpression): ts.StringLiteralLike[] {
  const found: ts.StringLiteralLike[] = [];
  for (let index = call.arguments.length - 1; index >= 0; index -= 1) {
    const argument = call.arguments[index];
    if (ts.isStringLiteral(argument) || ts.isNoSubstitutionTemplateLiteral(argument)) {
      found.unshift(argument);
    } else break;
  }
  return found;
}

/** What those segments spell, relative to the repository. */
function spelled(segments: readonly string[]): string {
  const parts = segments.flatMap(segment => segment.split('/')).filter(part => part !== '');
  while (parts.length > 0 && (parts[0] === '.' || parts[0] === '..')) parts.shift();
  return parts.join('/');
}

function walk(node: ts.Node, visit: (node: ts.Node) => void): void {
  visit(node);
  ts.forEachChild(node, child => {
    walk(child, visit);
  });
}

function scriptKind(name: string): ts.ScriptKind {
  if (name.endsWith('.tsx') || name.endsWith('.jsx')) return ts.ScriptKind.TSX;
  if (name.endsWith('.js') || name.endsWith('.mjs') || name.endsWith('.cjs')) {
    return ts.ScriptKind.JS;
  }
  return ts.ScriptKind.TS;
}

/** Every instance path one source's *code* writes out: the line, the text
 *  as it is written, and the declared path it spells. */
export function offencesIn(name: string, source: string): [number, string, string][] {
  const tree = ts.createSourceFile(name, source, ts.ScriptTarget.Latest, true, scriptKind(name));
  const lineOf = (node: ts.Node): number =>
    tree.getLineAndCharacterOfPosition(node.getStart(tree)).line + 1;

  const found: [number, string, string][] = [];
  const accounted = new Set<ts.Node>();
  const usedAsPath = new Set<ts.Node>();

  walk(tree, node => {
    const call = pathCall(node);
    if (call === null) return;
    for (const argument of call.arguments) {
      if (ts.isStringLiteral(argument) || ts.isNoSubstitutionTemplateLiteral(argument)) {
        usedAsPath.add(argument);
      }
    }
    const segments = trailingSegments(call);
    if (segments.length < 2) return;
    for (const segment of segments) accounted.add(segment);
    const written = spelled(segments.map(segment => segment.text));
    const declared = offence(written, true);
    if (declared !== null) found.push([lineOf(call), written, declared]);
  });

  walk(tree, node => {
    if (!textual(node) || accounted.has(node)) return;
    const value = ts.isJsxText(node) ? node.text.trim() : node.text;
    const declared = offence(value, usedAsPath.has(node));
    if (declared !== null) found.push([lineOf(node), value, declared]);
  });

  return found.sort((first, second) => first[0] - second[0]);
}

function sourcesUnder(relative: string): string[] {
  const full = resolve(ROOT, relative);
  if (!statSync(full).isDirectory()) return [relative];
  const found: string[] = [];
  for (const entry of readdirSync(full, { withFileTypes: true })) {
    if (entry.isDirectory()) found.push(...sourcesUnder(join(relative, entry.name)));
    else if (EXTENSIONS.some(extension => entry.name.endsWith(extension))) {
      found.push(join(relative, entry.name));
    }
  }
  return found;
}

/** Every source this sweep reads, with its text. */
export function swept(): [string, string][] {
  return SWEPT.flatMap(sourcesUnder)
    .map(name => name.split('\\').join('/'))
    .filter(name => !HOMES.has(name))
    .sort()
    .map(name => [name, readFileSync(resolve(ROOT, name), 'utf8')]);
}

describe('the sweep is real', () => {
  it('reads every tree it claims to read', () => {
    const read = swept().map(([name]) => name);

    expect(read.filter(name => name.startsWith('app/src/')).length).toBeGreaterThan(50);
    expect(read.filter(name => name.startsWith('app/scripts/')).length).toBeGreaterThan(10);
    expect(read).toContain('app/vite.config.ts');
    expect(read).toContain('site/.eleventy.js');
    expect(read).toContain('site/scripts/published.cjs');
    expect(read).toContain('site/src/_data/banners.js');
  });

  it('reads a declaration long enough to refuse something', () => {
    expect(DECLARED.length).toBeGreaterThanOrEqual(4);
  });

  it('reads the declaration itself, not a list typed here', () => {
    expect(DECLARED).toEqual(
      handedFromData(
        yaml.load(readFileSync(resolve(ROOT, BOUNDARY_PATH), 'utf8')),
      ).map(entry => entry.path),
    );
  });
});

describe('an instance path is named once', () => {
  it('is written out by no source the cockpit or the showcase ships', () => {
    const written = swept().flatMap(([name, source]) =>
      offencesIn(name, source).map(
        ([line, value, declared]) => `${name}:${line}: '${value}' writes out ${declared}`,
      ),
    );

    expect(
      written,
      'these write out a path declarations/boundary.yml hands to the instance, which ' +
        'app/scripts/instance-paths.mjs and app/src/paths.ts already name from ' +
        `that declaration:\n${written.join('\n')}`,
    ).toEqual([]);
  });
});

const REFUSED = [
  "const PATH = 'instance/data/config.yml';",
  "getFile('instance/data/speakers.yml', token);",
  "const SRC = resolve(__dirname, '..', '..', 'instance', 'keys', 'events');",
  "const OUT = join(root, 'instance', 'public-data', 'certificates-public.json');",
  "const REGISTER = 'docs/handbook/governance/register.md';",
  "const EVENTS = resolve(root, 'instance', 'data');",
  "throw new Error('instance/data/queue-ledger.yml holds no usable handled list');",
  'const url = `instance/data/events/${eventId}/registrations.enc`;',
  'const label = <code>instance/data/speakers.yml</code>;',
  "if (path === 'instance/data/') return why;",
  "if (path === 'instance/public-data/') return why;",
];

const ADMITTED = [
  'const fields = payload.data?.fields;',
  "const wrapped = payload['data'];",
  "const DOMAIN = 'data';",
  'getFile(speakersFile(), token);',
  "const SRC = resolve(ROOT, keysDir(), 'events');",
  "const DST = resolve(__dirname, '..', 'public', 'keys', 'events');",
  'const url = `${BASE}/keys/events/${eventId}.pub`;',
  "import { useData } from '../data/DataContext';",
  "const DEMO = `instances/example/${dataDir()}`;",
  "const permalink = '/data/';",
  "const BUDGET = 'instance/actions-budget.yml';",
  "const DECLARATION = path.join(__dirname, '..', '..', 'instance', 'config.json');",
  'throw new Error(`${configFile()} holds no usable channel list`);',
  '/** instance/data/config.yml is the board configuration. */\nconst settled = 1;',
  '// instance/data/speakers.yml is read through the Contents API.\nconst records = 2;',
];

describe('the rule bites', () => {
  it.each(REFUSED)('refuses %s', source => {
    expect(offencesIn('sample.tsx', source)).not.toEqual([]);
  });
});

describe('the rule leaves a lookalike alone', () => {
  it.each(ADMITTED)('admits %s', source => {
    expect(offencesIn('sample.tsx', source)).toEqual([]);
  });
});
