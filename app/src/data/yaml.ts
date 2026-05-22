import yaml from 'js-yaml';
import type { Speaker, VwsEvent } from './types';

export function parseSpeakers(text: string): Speaker[] {
  const data = yaml.load(text);
  return Array.isArray(data) ? (data as Speaker[]) : [];
}
export function parseEvents(text: string): VwsEvent[] {
  const data = yaml.load(text);
  return Array.isArray(data) ? (data as VwsEvent[]) : [];
}
export function serializeSpeakers(items: Speaker[]): string {
  return yaml.dump(items, { lineWidth: 1000, noRefs: true, sortKeys: false });
}
export function serializeEvents(items: VwsEvent[]): string {
  return yaml.dump(items, { lineWidth: 1000, noRefs: true, sortKeys: false });
}
