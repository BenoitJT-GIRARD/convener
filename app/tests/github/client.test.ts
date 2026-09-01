import { describe, it, expect, vi, beforeEach } from 'vitest';
import { gh, GitHubError } from '../../src/github/client';
import { instanceIdentity } from '../../src/instance';

describe('gh', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('resolves with the parsed JSON body on success', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ hello: 'world' }),
    });
    vi.stubGlobal('fetch', fetchSpy);
    const out = await gh('/contents/foo.yml', { token: 'tok', method: 'GET' });
    expect(out).toEqual({ hello: 'world' });
    const [url, opts] = fetchSpy.mock.calls[0];
    // The declared repository, not this one's name: `client.ts` composes
    // the address from `instanceIdentity().repository`, so a literal here
    // would pin the test to whoever happens to run this repository today.
    expect(url).toBe(
      `https://api.github.com/repos/${instanceIdentity().repository}/contents/foo.yml`,
    );
    expect(opts.headers.Authorization).toBe('Bearer tok');
  });

  it('merges caller-supplied headers with the defaults', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal('fetch', fetchSpy);
    await gh('/x', { token: 'tok', method: 'PUT', headers: { 'Content-Type': 'application/json' } });
    const [, opts] = fetchSpy.mock.calls[0];
    expect(opts.headers['Content-Type']).toBe('application/json');
    expect(opts.headers.Authorization).toBe('Bearer tok');
  });

  it('throws a GitHubError with the status and body on a non-ok response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 404, text: async () => 'Not Found' }),
    );
    await expect(gh('/missing', { token: 'tok', method: 'GET' })).rejects.toThrow(GitHubError);
    await expect(gh('/missing', { token: 'tok', method: 'GET' })).rejects.toThrow(/GitHub 404/);
  });
});
