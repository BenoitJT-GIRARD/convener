import { describe, it, expect, beforeEach } from 'vitest';
import { fetchContent, invalidateContent } from '../src/content/fetch';
import { substitute } from '../src/content/render';

beforeEach(() => {
  invalidateContent();
});

describe('fetchContent', () => {
  it('returns missing marker for unknown key', async () => {
    const out = await fetchContent('unknown/key', 'tok');
    expect(out).toMatch(/Missing/);
  });

  it('returns demo placeholder when no token', async () => {
    const out = await fetchContent('toolkit/emails/invitation', null);
    expect(out).toMatch(/demo/);
  });
});

describe('substitute', () => {
  it('replaces {{ speaker.name }}', () => {
    const out = substitute('Dear {{ speaker.name }},', { speaker: { name: 'Mei' } as any });
    expect(out).toMatch(/Dear Mei/);
  });

  it('handles missing path with explicit token', () => {
    expect(substitute('Hi {{unknown.path}}', {})).toMatch(/«missing: unknown.path»/);
  });

  it('leaves text without templates untouched', () => {
    expect(substitute('no templates here', {})).toBe('no templates here');
  });
});
