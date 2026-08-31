import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { friendlyError } from '../src/github/errors';
import { DateRejected } from '../src/state/dates';
import { AssignmentRejected } from '../src/state/assignment';
import { GitHubError } from '../src/github/client';
import { ConflictError } from '../src/github/mutate';
import { BallotRejected } from '../src/state/ballots';

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
    // Never "your access token": the device-flow sign-in shows the volunteer
    // no token at all, and the sentence has to name a recovery they can walk
    // to.
    const e = new GitHubError(403, 'GitHub 403: secret leak');
    expect(friendlyError(e, 'save')).toBe(
      'Your GitHub account does not have permission to save to this repository. ' +
        'Ask whoever set this instance up for write access.',
    );
  });

  it('maps 403 to a load-specific message when context is load', () => {
    const e = new GitHubError(403, 'GitHub 403: secret leak');
    expect(friendlyError(e, 'load')).toBe(
      'Your GitHub account does not have permission to read this. ' +
        'Ask whoever set this instance up for access.',
    );
  });

  it('relays a rejected ballot as the sentence it already is', () => {
    // A governance rule refusing a write is not a transport failure: the
    // volunteer must read what to add, not "GitHub is not responding".
    const e = new BallotRejected('A recusal needs a written reason.');
    expect(friendlyError(e, 'save')).toBe('A recusal needs a written reason.');
  });

  it('relays a rejected date as the sentence it already is', () => {
    // Reaching here means the rule fired inside a `mutate` transformation
    // replayed against freshly-read data -- the moment the volunteer most
    // needs to read that the speaker has not agreed to that evening.
    const e = new DateRejected('2026-10-01 is not a date this speaker has accepted.');
    expect(friendlyError(e, 'save')).toBe('2026-10-01 is not a date this speaker has accepted.');
  });

  it('relays an assignment refusal as the sentence it carries', () => {
    // Not "GitHub is unwell": the line the owner was put down for is not one
    // the journey has, and the volunteer needs to read that, not a status
    // code. The sentence is about the step, never about who chose it.
    const e = new AssignmentRejected(
      '"made/up/step" is not a step of the journey, so nobody can be put down for it.',
    );
    expect(friendlyError(e, 'save')).toBe(
      '"made/up/step" is not a step of the journey, so nobody can be put down for it.',
    );
  });

  it('maps 404 to a plain not-found message naming what was not found', () => {
    const e = new GitHubError(404, 'GitHub 404: Not Found');
    expect(friendlyError(e, 'load')).toBe(
      'GitHub could not find that file. If this keeps happening, ask whoever set this instance up.',
    );
  });

  it('maps any 5xx to the generic "not responding" message, without the raw body', () => {
    const e = new GitHubError(500, 'GitHub 500: <html>internal server error, stack trace...</html>');
    const msg = friendlyError(e, 'save');
    expect(msg).toBe('GitHub is not responding. Try again in a moment.');
    expect(msg).not.toMatch(/500|html|stack trace/);
  });

  it('passes a ConflictError message through unchanged -- it is already plain language', () => {
    const e = new ConflictError('instance/data/speakers.yml', 3);
    expect(friendlyError(e, 'save')).toBe(e.message);
    expect(friendlyError(e, 'save')).toMatch(/someone else is editing/);
  });

  it('says only that GitHub could not be reached when it never answered at all', () => {
    // A bare TypeError is a request that got no answer: offline, DNS, a
    // captive portal. "GitHub is not responding" asserts a state of GitHub
    // that nothing here established, and is plainly false for the commonest
    // cause. The two branches are separate for that reason -- a status code
    // above is an answer that *was* received.
    const e = new TypeError('Failed to fetch');
    expect(friendlyError(e, 'load')).toBe(
      'Could not reach GitHub. Check your connection, then try again.',
    );
    expect(friendlyError(new GitHubError(500, 'boom'), 'load')).toBe(
      'GitHub is not responding. Try again in a moment.',
    );
  });

  it('logs the raw error for diagnosis without surfacing it', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const e = new GitHubError(500, 'GitHub 500: raw body');
    friendlyError(e, 'load');
    expect(spy).toHaveBeenCalledWith(e);
  });
});
