import * as yaml from 'js-yaml';
import { readConfig, readSpeakers } from './validate';
import type { Speaker, Config } from './types';

/**
 * The one set of dump options this app writes YAML with, chosen so that the
 * bytes match what `tools/convener_ops/cli/store.py::dump` writes for the same data.
 *
 * The two languages write the same two files -- the browser on every save,
 * the scheduled jobs on every sweep -- so a difference in *formatting* is a
 * difference in the file, and every alternating write would rewrite lines
 * neither side meant to touch. `seqNoIndent` is the one that mattered:
 * PyYAML puts a block sequence at its parent key's indentation, js-yaml
 * indented it by two, and `instance/data/speakers.yml` on disk is in PyYAML's shape.
 * `tools/tests/fixtures/speakers-from-app.yml` pins the agreement byte for
 * byte, from both sides. js-yaml 4 spelled the same option `noArrayIndent`,
 * and 5 ignores that spelling in silence rather than refusing it -- the
 * fixture is what would have caught the rename, and did.
 */
const DUMP = { lineWidth: 1000, noRefs: true, sortKeys: false, seqNoIndent: true };

/**
 * Whether a file holds no document at all: blank lines, comment lines, and
 * nothing else.
 *
 * A line whose first non-space character is `#` is a comment, and a file of
 * those is a file somebody has started and not filled in -- the header
 * `withSpeakersHeader` writes, on its own, is exactly that. Anything else
 * on any line makes this a document, including `---` and `null`, which are
 * both a document whose content is nothing.
 */
function holdsNoDocument(text: string): boolean {
  return text
    .split('\n')
    .every(line => line.trim() === '' || line.trimStart().startsWith('#'));
}

/**
 * Read one YAML document, where a file with nothing in it is no document.
 *
 * js-yaml 4 returned `undefined` for such a file; 5 raises `YAMLException`
 * instead. This repository had already answered that question for its own
 * files, in the two readers below: `readSpeakers` reads no document as no
 * speakers, "that is where the repository starts", and `readConfig` refuses
 * it by naming the file and what it wanted. An exception raised before
 * either of them is handed a value replaces both answers with one sentence
 * about a parser, and it replaces the first one with a stop -- a duplicate
 * whose `instance/data/speakers.yml` is still empty could not open the
 * cockpit at all.
 *
 * So the decision stays in the readers that made it and this hands them the
 * value they were written against. Every other refusal passes through
 * untouched: a tab in the indentation, or a duplicated key, is a malformed
 * file rather than an empty one, and `tests/data/yaml.test.ts` reads the
 * table of both kinds back out of js-yaml itself.
 */
export function loadDocument(text: string): unknown {
  return holdsNoDocument(text) ? undefined : yaml.load(text);
}

/**
 * Read `instance/data/speakers.yml`.
 *
 * Every field is checked against the model on the way in (`./validate.ts`);
 * a file that does not match stops the read with a `DataShapeError` naming
 * the file and the field, rather than being cast into a `Speaker[]` the
 * screens will then read `undefined` out of.
 */
export function parseSpeakers(text: string): Speaker[] {
  return readSpeakers(loadDocument(text));
}

export function serializeSpeakers(items: Speaker[]): string {
  return yaml.dump(items, DUMP);
}

/**
 * Read `instance/data/config.yml`.
 *
 * Throws rather than returning `null` for a file it cannot read: the caller
 * used to substitute a constant default, which meant a malformed config
 * showed the board a governance model nobody had adopted.
 */
export function parseConfig(text: string): Config {
  return readConfig(loadDocument(text));
}

export function serializeConfig(cfg: Config): string {
  return yaml.dump(cfg, DUMP);
}

export const SPEAKERS_HEADER =
  '# Speakers (unified schema v6 — see docs/engineering/schema.md)\n';
export const CONFIG_HEADER = '# Repo-wide config for the convener app\n';

export function withSpeakersHeader(body: string): string {
  return SPEAKERS_HEADER + body;
}

export function withConfigHeader(body: string): string {
  return CONFIG_HEADER + body;
}

/** YAML parsing ignores comments, but stripping keeps round-trip tests honest. */
export function stripHeader(text: string): string {
  return text.replace(/^#[^\n]*\n/, '');
}
