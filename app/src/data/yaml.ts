import yaml from 'js-yaml';
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
 * indented it by two, and `data/speakers.yml` on disk is in PyYAML's shape.
 * `tools/tests/fixtures/speakers-from-app.yml` pins the agreement byte for
 * byte, from both sides.
 */
const DUMP = { lineWidth: 1000, noRefs: true, sortKeys: false, noArrayIndent: true };

export function parseSpeakers(text: string): Speaker[] {
  const data = yaml.load(text);
  return Array.isArray(data) ? (data as Speaker[]) : [];
}

export function serializeSpeakers(items: Speaker[]): string {
  return yaml.dump(items, DUMP);
}

export function parseConfig(text: string): Config | null {
  const data = yaml.load(text);
  return data && typeof data === 'object' ? (data as Config) : null;
}

export function serializeConfig(cfg: Config): string {
  return yaml.dump(cfg, DUMP);
}

export const SPEAKERS_HEADER =
  '# Speakers (unified schema v3 — see docs/reference/schema.md)\n';
export const CONFIG_HEADER = '# Repo-wide config for the Convener app\n';

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
