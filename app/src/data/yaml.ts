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
