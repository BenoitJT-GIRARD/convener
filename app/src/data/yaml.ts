import yaml from 'js-yaml';
import type { Speaker, Config } from './types';

export function parseSpeakers(text: string): Speaker[] {
  const data = yaml.load(text);
  return Array.isArray(data) ? (data as Speaker[]) : [];
}

export function serializeSpeakers(items: Speaker[]): string {
  return yaml.dump(items, { lineWidth: 1000, noRefs: true, sortKeys: false });
}

export function parseConfig(text: string): Config | null {
  const data = yaml.load(text);
  return data && typeof data === 'object' ? (data as Config) : null;
}

export function serializeConfig(cfg: Config): string {
  return yaml.dump(cfg, { lineWidth: 1000, noRefs: true, sortKeys: false });
}

export const SPEAKERS_HEADER =
  '# Speakers (unified schema v2 — see docs/reference/schema.md)\n';
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
