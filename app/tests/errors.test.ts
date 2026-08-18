import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { friendlyError } from '../src/github/errors';
import { GitHubError } from '../src/github/client';
import { ConflictError } from '../src/github/mutate';

describe('friendlyError', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('maps 401 to an expired-session message regardless of context', () => {
    const e = new GitHubError(401, 'GitHub 401: Bad credentials');
    expect(friendlyError(e, 'load')).toBe('Your sign-in has expired. Sign in again.');
    expect(friendlyError(e, 'save')).toBe('Your sign-in has expired. Sign in again.');
  });

  it('maps 403 to a save-specific message when context is save', () => {
    const e = new GitHubError(403, 'GitHub 403: secret leak');
    expect(friendlyError(e, 'save')).toBe(
      'Your access token does not have permission to save.',
    );
  });

  it('maps 403 to a load-specific message when context is load', () => {
    const e = new GitHubError(403, 'GitHub 403: secret leak');
    expect(friendlyError(e, 'load')).toBe(
      'Your access token does not have permission to load this.',
    );
  });

  it('maps 404 to a plain not-found message', () => {
    const e = new GitHubError(404, 'GitHub 404: Not Found');
    expect(friendlyError(e, 'load')).toBe('That could not be found on GitHub.');
  });

  it('maps any 5xx to the generic "not responding" message, without the raw body', () => {
    const e = new GitHubError(500, 'GitHub 500: <html>internal server error, stack trace...</html>');
    const msg = friendlyError(e, 'save');
    expect(msg).toBe('GitHub is not responding. Try again in a moment.');
    expect(msg).not.toMatch(/500|html|stack trace/);
  });

  it('passes a ConflictError message through unchanged -- it is already plain language', () => {
    const e = new ConflictError('data/speakers.yml', 3);
    expect(friendlyError(e, 'save')).toBe(e.message);
    expect(friendlyError(e, 'save')).toMatch(/someone else is editing/);
  });

  it('maps a network failure (bare TypeError) to the generic "not responding" message', () => {
    const e = new TypeError('Failed to fetch');
    expect(friendlyError(e, 'load')).toBe('GitHub is not responding. Try again in a moment.');
  });

  it('logs the raw error for diagnosis without surfacing it', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const e = new GitHubError(500, 'GitHub 500: raw body');
    friendlyError(e, 'load');
    expect(spy).toHaveBeenCalledWith(e);
  });
});
