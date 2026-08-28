import yaml from 'js-yaml';
import { readConfig, readSpeakers } from './validate';
import type { Speaker, Config } from './types';

/**
 * The one set of dump options this app writes YAML with, chosen so that the
 * bytes match what `tools/convener_ops/cli.py::_dump` writes for the same data.
 *
 * The two languages write the same two files -- the browser on every save,
 * the scheduled jobs on every sweep -- so a difference in *formatting* is a
 * difference in the file, and every alternating write would rewrite lines
 * neither side meant to touch. `noArrayIndent` is the one that mattered:
 * PyYAML puts a block sequence at its parent key's indentation, js-yaml
 * indented it by two, and `instance/data/speakers.yml` on disk is in PyYAML's shape.
 * `tools/tests/fixtures/speakers-from-app.yml` pins the agreement byte for
 * byte, from both sides.
 */
const DUMP = { lineWidth: 1000, noRefs: true, sortKeys: false, noArrayIndent: true };

/**
 * Read `instance/data/speakers.yml`.
 *
 * Every field is checked against the model on the way in (`./validate.ts`);
 * a file that does not match stops the read with a `DataShapeError` naming
 * the file and the field, rather than being cast into a `Speaker[]` the
 * screens will then read `undefined` out of.
 */
export function parseSpeakers(text: string): Speaker[] {
  return readSpeakers(yaml.load(text));
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
  return readConfig(yaml.load(text));
}

export function serializeConfig(cfg: Config): string {
  return yaml.dump(cfg, DUMP);
}

export const SPEAKERS_HEADER =
  '# Speakers (unified schema v6 — see docs/reference/schema.md)\n';
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
