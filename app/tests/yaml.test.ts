import { describe, it, expect } from 'vitest';
import { parseSpeakers, parseEvents, serializeSpeakers } from '../src/data/yaml';

const YAML_SPK = `
- id: spk-001
  name: Alice
  status: lead
  owner: ''
  email: a@x
  affiliation: Lab
  country: FR
  topic: behaviour
  source: form
  proposed_by: ''
  links: []
  selection: { votes_for: [], decided_on: '' }
  next_action: ''
  next_action_date: ''
  event_id: ''
  notes: ''
`;

describe('yaml', () => {
  it('parses a speaker list', () => {
    const out = parseSpeakers(YAML_SPK);
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe('spk-001');
    expect(out[0].status).toBe('lead');
  });

  it('round-trips speakers (parse → serialize → parse equals)', () => {
    const a = parseSpeakers(YAML_SPK);
    const dumped = serializeSpeakers(a);
    const b = parseSpeakers(dumped);
    expect(b).toEqual(a);
  });

  it('parses an empty events list', () => {
    expect(parseEvents('')).toEqual([]);
  });
});
