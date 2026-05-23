import { describe, it, expect, beforeEach, vi } from 'vitest';
import { fetchContent, invalidateContent } from '../src/content/fetch';
import { substitute } from '../src/content/render';

beforeEach(() => {
  invalidateContent();
  vi.unstubAllGlobals();
});

describe('fetchContent', () => {
  it('returns missing marker for unknown key', async () => {
    const out = await fetchContent('unknown/key', null);
    expect(out).toMatch(/Missing/);
  });

  it('fetches markdown from /<base>/handbook/<file>', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      text: async () => '# Hello from invitation.md',
    });
    vi.stubGlobal('fetch', fetchSpy);
    const out = await fetchContent('toolkit/emails/invitation', null);
    expect(out).toBe('# Hello from invitation.md');
    expect(fetchSpy.mock.calls[0][0]).toMatch(/handbook\/toolkit\/emails\/invitation\.md$/);
  });

  it('throws on non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    await expect(fetchContent('handbook/overview', null)).rejects.toThrow(/Content fetch failed/);
  });

  it('caches subsequent calls', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, text: async () => 'cached body' });
    vi.stubGlobal('fetch', fetchSpy);
    await fetchContent('handbook/glossary', null);
    await fetchContent('handbook/glossary', null);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
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
