import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getFile, putFile, githubStore } from '../src/github/contents';
import { dataEdit, identifier } from '../src/state/decisions';

describe('getFile', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('decodes the base64 content and returns text + sha', async () => {
    const b64 = btoa('speakers: []\n');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ content: b64, sha: 'abc123' }),
      }),
    );
    const out = await getFile('data/speakers.yml', 'tok');
    expect(out).toEqual({ text: 'speakers: []\n', sha: 'abc123' });
  });

  it('handles non-ASCII (accented) content correctly', async () => {
    const original = 'notes: café\n';
    const bytes = new TextEncoder().encode(original);
    let bin = '';
    for (const b of bytes) bin += String.fromCharCode(b);
    const b64 = btoa(bin);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ content: b64, sha: 's' }) }),
    );
    const out = await getFile('data/config.yml', 'tok');
    expect(out.text).toBe(original);
  });
});

describe('putFile', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('encodes text to base64 and posts a PUT with the sha and message', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ content: { sha: 'newsha' } }),
    });
    vi.stubGlobal('fetch', fetchSpy);
    const out = await putFile('data/speakers.yml', 'speakers: []\n', 'oldsha', 'update', 'tok');
    expect(out).toEqual({ content: { sha: 'newsha' } });
    const [, opts] = fetchSpy.mock.calls[0];
    expect(opts.method).toBe('PUT');
    const body = JSON.parse(opts.body as string);
    expect(body.message).toBe('update');
    expect(body.sha).toBe('oldsha');
    expect(atob(body.content)).toBe('speakers: []\n');
  });
});

describe('githubStore', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('read delegates to getFile', async () => {
    const b64 = btoa('speakers: []\n');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ content: b64, sha: 'abc123' }) }),
    );
    const out = await githubStore('tok').read('data/speakers.yml');
    expect(out).toEqual({ text: 'speakers: []\n', sha: 'abc123' });
  });

  it('write delegates to putFile and maps content.sha to sha', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ content: { sha: 'newsha' } }),
    });
    vi.stubGlobal('fetch', fetchSpy);
    const out = await githubStore('tok').write(
      'data/speakers.yml',
      'speakers: []\n',
      'oldsha',
      dataEdit(identifier('spk-001'), { part: 'admin-fields' }),
    );
    expect(out).toEqual({ sha: 'newsha' });
    const [, opts] = fetchSpy.mock.calls[0];
    const body = JSON.parse(opts.body as string);
    expect(body.sha).toBe('oldsha');
    expect(body.message).toBe('data: spk-001 admin edit');
  });
});
