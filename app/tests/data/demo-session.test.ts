/**
 * The demonstration remembers what somebody did to it, for as long as they
 * are there and not a moment longer.
 *
 * Measured before this existed: propose a speaker, advance it through the
 * pipeline, reload the page -- and the record is gone, with nothing to say
 * it ever existed. The records lived in one React component's state, so
 * they lasted exactly as long as the document did, and following a link
 * out to the showcase and back was enough to lose them.
 *
 * Three properties, and the third is as load-bearing as the first two: a
 * demonstration that remembered past the tab would raise the question it
 * exists not to raise.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  forgetDemoSession,
  readDemoSession,
  writeDemoSession,
} from '../../src/data/demo-session';
import { demoConfig, demoSpeakers } from '../../src/data/demo';

const KEY = 'convener.demo.session.v1';

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
});

afterEach(() => {
  sessionStorage.clear();
  localStorage.clear();
});

describe('what the demonstration keeps', () => {
  it('has nothing for a tab that has done nothing', () => {
    expect(readDemoSession()).toBeNull();
  });

  it('gives back the records it was given, through the readers a real load uses', () => {
    const speakers = demoSpeakers();
    const config = demoConfig();
    writeDemoSession(speakers, config);
    const kept = readDemoSession();
    expect(kept).not.toBeNull();
    expect(kept!.speakers).toEqual(speakers);
    expect(kept!.config).toEqual(config);
  });

  it('keeps an edit, which is the whole point of it', () => {
    const edited = [
      { ...demoSpeakers()[0], name: 'Someone A Visitor Proposed' },
      ...demoSpeakers().slice(1),
    ];
    writeDemoSession(edited, demoConfig());
    expect(readDemoSession()!.speakers[0].name).toBe('Someone A Visitor Proposed');
  });

  it('forgets on request, which is what leaving the demonstration does', () => {
    writeDemoSession(demoSpeakers(), demoConfig());
    forgetDemoSession();
    expect(readDemoSession()).toBeNull();
  });
});

describe('where it keeps it', () => {
  it('is the session and never longer', () => {
    // `localStorage` survives the browser being closed and reopened next
    // week. A demonstration still holding your edits then invites exactly
    // the question this one must never raise -- where is this kept, and
    // who can read it.
    writeDemoSession(demoSpeakers(), demoConfig());
    expect(sessionStorage.getItem(KEY)).not.toBeNull();
    expect(localStorage.length).toBe(0);
  });

  it('is the two documents a repository holds, not a shape of its own', () => {
    // Serialised by the writer a real edit goes through and read by the
    // reader a real load goes through, so a stale blob fails the way a
    // malformed file fails rather than reaching a screen half-parsed.
    writeDemoSession(demoSpeakers(), demoConfig());
    const stored = JSON.parse(sessionStorage.getItem(KEY)!) as Record<string, string>;
    expect(stored.speakers).toContain('- id: exm-001');
    expect(stored.config).toContain('board:');
  });
});

describe('what it does with something it cannot read', () => {
  it('falls back to the example rather than rendering half of it', () => {
    sessionStorage.setItem(KEY, 'not json at all');
    expect(readDemoSession()).toBeNull();
  });

  it('does the same for a document that no longer matches the model', () => {
    sessionStorage.setItem(
      KEY,
      JSON.stringify({ speakers: '- id: 1\n  name: []\n', config: 'board: []\n' }),
    );
    expect(readDemoSession()).toBeNull();
  });

  it('and for a browser that refuses site data at all', () => {
    // A private window, or one configured to block storage, throws on the
    // first touch rather than answering null. A demonstration that cannot
    // remember is still a demonstration; one that throws on startup is
    // not.
    const refuse = () => {
      throw new Error('the operation is insecure');
    };
    const real = {
      getItem: sessionStorage.getItem,
      setItem: sessionStorage.setItem,
      removeItem: sessionStorage.removeItem,
    };
    Object.assign(sessionStorage, {
      getItem: refuse,
      setItem: refuse,
      removeItem: refuse,
    });
    try {
      expect(readDemoSession()).toBeNull();
      expect(() => writeDemoSession(demoSpeakers(), demoConfig())).not.toThrow();
      expect(() => forgetDemoSession()).not.toThrow();
    } finally {
      Object.assign(sessionStorage, real);
    }
  });

  it('writes nothing at all before the configuration has arrived', () => {
    writeDemoSession(demoSpeakers(), null);
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });
});
