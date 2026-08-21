import { describe, it, expect, beforeEach, vi } from 'vitest';
import { fetchContent, invalidateContent } from '../src/content/fetch';
import { substitute } from '../src/content/render';
import type { Speaker } from '../src/data/types';
import { speaker as double } from './data-doubles';
import signupLinkFixture from '../../tools/tests/fixtures/signup-link.json';

beforeEach(() => {
  invalidateContent();
  vi.unstubAllGlobals();
});

// Through the shared double: a field added to `Speaker` reaches this
// record on its own, instead of leaving the file describing a shape
// the reader would refuse.
const BASE_SPEAKER: Speaker = double({
  id: 'sp-1',
  name: '',
  gender: 'undisclosed',
  career_stage: 'undisclosed',
  email: '',
  affiliation: '',
  country: '',
  title: '',
  abstract: '',
  conflicts_of_interest: '',
  source: 'form',
  proposed_by: '',
  assigned_to: '',
  links: [],
  host_1: '',
  host_2: '',
  status: 'lead',
  selection: { ballots: [], opened_on: '', decided_on: '' },
  publication: {
    consent: 'pending',
    approved_by: '',
    approved_on: '',
    objections: [],
    outcome: '',
  },
  edition_code: '',
  date: '',
  time: '',
  zoom_link: '',
  youtube_url: '',
  forum_thread: '',
  runbook_progress: {},
  metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
  notes: '',
});

function makeSpeaker(overrides: Partial<Speaker>): Speaker {
  return { ...BASE_SPEAKER, ...overrides };
}

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

  it('throws a plain-language error on non-ok response, not the raw status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    await expect(fetchContent('handbook/overview', null)).rejects.toThrow(
      /could not be loaded/,
    );
  });

  it('throws a plain-language error, not a rejected promise, when the network fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
    await expect(fetchContent('handbook/roles', null)).rejects.toThrow(
      /check your connection/i,
    );
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
    const out = substitute('Dear {{ speaker.name }},', { speaker: makeSpeaker({ name: 'Mei' }) });
    expect(out).toMatch(/Dear Mei/);
  });

  it('handles missing path with explicit token', () => {
    expect(substitute('Hi {{unknown.path}}', {})).toMatch(/«missing: unknown.path»/);
  });

  it('leaves text without templates untouched', () => {
    expect(substitute('no templates here', {})).toBe('no templates here');
  });
});

describe('substitute v2 context', () => {
  it('derives speaker.first_name from speaker.name', () => {
    const s = makeSpeaker({ name: 'Mei Tanaka' });
    expect(substitute('{{ speaker.first_name }}', { speaker: s })).toBe('Mei');
  });
  it('resolves host_1.name from speaker.host_1', () => {
    const s = makeSpeaker({ name: 'X', host_1: 'alice', host_2: 'bob' });
    expect(substitute('{{ host_1.name }}', { speaker: s })).toBe('alice');
  });
  it('resolves speaker.time', () => {
    const s = makeSpeaker({ name: 'X', time: '14:30' });
    expect(substitute('starts at {{ speaker.time }}', { speaker: s })).toBe('starts at 14:30');
  });

  it('derives speaker.signup_link as the missing marker when edition_code is blank', () => {
    const s = makeSpeaker({ name: 'X', edition_code: '' });
    expect(substitute('{{ speaker.signup_link }}', { speaker: s })).toMatch(
      /«missing: speaker\.signup_link»/,
    );
  });
});

// Fix wave 2 correction: wave 1 published `registration.SIGNUP_BASE` as a
// literal with the event id left for a volunteer to fill in by hand, on the
// mistaken belief that no Speaker-to-event-id mapping existed. R-5
// (`tools/convener_ops/platform.py::find_speaker`) is that mapping -- `event_id`
// is `edition_code`, lower-cased -- and this file's `speaker.signup_link`
// now computes it. Bound here against the same shared, worked fixture
// `tools/tests/test_confirmation.py` reads on the Python side (D-14),
// rather than trusting two lower-casing implementations to agree.
describe('speaker.signup_link matches the shared D-14 fixture', () => {
  it('carries the same signup_base as the fixture', () => {
    expect(signupLinkFixture.signup_base).toBe(
      'https://example-instance.github.io/example-showcase/app/#/signup/',
    );
  });

  for (const c of signupLinkFixture.cases) {
    it(`computes ${c.signup_url} for edition_code ${c.edition_code}`, () => {
      const s = makeSpeaker({ name: 'X', edition_code: c.edition_code });
      expect(substitute('{{ speaker.signup_link }}', { speaker: s })).toBe(c.signup_url);
    });
  }
});
