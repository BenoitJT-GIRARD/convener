/**
 * Where a line says its artefact is, against where the artefact is actually
 * written.
 *
 * The defect this closes was not that the images were missing: they are
 * generated for every scheduled edition and have been for months. It was
 * that the line asking somebody to confirm them named no path at all, so
 * confirming it meant knowing to open the Actions tab and find a run. A
 * screen that answers that question is a screen whose answer can go stale,
 * which is what the first half of this suite is for: the workflow, the two
 * commands and the formats module are read from disk, and a name that
 * stops matching one of them is red here rather than a dead path a
 * volunteer meets on the day of the talk.
 *
 * The second half is the behaviour: what a line says when the file exists,
 * and what it says when there is nothing yet to point at.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import { DOWNLOAD, visualsWorkflowUrl, whereabouts } from '../../src/state/artefacts';
import { channelItem } from '../../src/state/channels';
import { itemByKey } from '../../src/state/phases';
import type { RunbookItem } from '../../src/state/phases';
import { config, speaker as double } from '../helpers/data-doubles';

const ROOT = resolve(__dirname, '../../..');

function read(relative: string): string {
  return readFileSync(resolve(ROOT, relative), 'utf-8');
}

const WORKFLOW = read(`.github/workflows/${DOWNLOAD.workflow}`);
const FORMATS = read('tools/convener_ops/publication/formats.py');
const RENDER = read('tools/convener_ops/cli/publication.py');
const ANNOUNCE = read('tools/convener_ops/publication/announce.py');

const VISUALS = itemByKey('scheduled/T-30/visuals')!;
const ROOM = itemByKey('scheduled/T-14/zoom-link')!;

/** A scheduled record with an edition code, which is the state every one of
 *  these lines is met in. */
const scheduled = double({ status: 'scheduled', edition_code: 'MRG-05', zoom_link: '' });

describe('the coordinates match the workflow that writes the files', () => {
  it('reads a workflow with an upload in it, so an empty read cannot pass', () => {
    expect(WORKFLOW).toContain('upload-artifact');
    expect(FORMATS.length).toBeGreaterThan(1000);
    expect(RENDER.length).toBeGreaterThan(1000);
  });

  it('names the artefact the workflow actually uploads', () => {
    expect(WORKFLOW).toContain(`name: ${DOWNLOAD.artefact}`);
  });

  it('states the retention the workflow asks GitHub for', () => {
    expect(WORKFLOW).toContain(`retention-days: ${DOWNLOAD.retentionDays}`);
  });

  it('points at the directory the workflow commits the banner into', () => {
    expect(WORKFLOW).toContain(DOWNLOAD.bannerDir.replace(/\/$/, ''));
  });

  it('names the three formats the renderer produces, and no fourth', () => {
    const declared = [...FORMATS.matchAll(/Format\(\s*name="([a-z]+)"/g)].map(m => `${m[1]}.png`);
    expect([...DOWNLOAD.images].sort()).toEqual([...declared].sort());
  });

  it('names the drafted texts the announcement command writes for a scheduled edition', () => {
    const declared = [...RENDER.matchAll(/texts\["([a-z-]+)"\] = announce\./g)].map(
      m => `${m[1]}.md`,
    );
    expect([...DOWNLOAD.texts].sort()).toEqual([...declared].sort());
  });

  it('sends the volunteer to the workflow rather than to the Actions tab', () => {
    expect(visualsWorkflowUrl()).toMatch(
      new RegExp(`^https://github\\.com/.+/actions/workflows/${DOWNLOAD.workflow}$`),
    );
  });
});

describe('the line that asks for the images says where they are', () => {
  it('names every file under this event’s own directory', () => {
    const found = whereabouts(VISUALS, scheduled, config())!;
    const where = found.found.map(one => one.where);
    for (const file of [...DOWNLOAD.images, ...DOWNLOAD.texts]) {
      expect(where).toContain(`mrg-05/${file}`);
    }
    expect(where).toContain(`${DOWNLOAD.bannerDir}mrg-05.png`);
    expect(found.pending).toBeNull();
  });

  it('carries the download it comes out of, with a link', () => {
    const found = whereabouts(VISUALS, scheduled, config())!;
    expect(found.from?.href).toBe(visualsWorkflowUrl());
    expect(found.from?.label).toContain(DOWNLOAD.artefact);
    expect(found.from?.label).toContain(String(DOWNLOAD.retentionDays));
  });

  it('says why there is nothing yet, rather than a path that resolves to nothing', () => {
    const found = whereabouts(VISUALS, double({ edition_code: '' }), config())!;
    expect(found.found).toEqual([]);
    expect(found.pending).toContain('no edition code');
  });
});

describe('the line that asks for the room link shows it', () => {
  it('shows the record’s own link, and the series’ joining instructions with it', () => {
    const found = whereabouts(
      ROOM,
      double({ zoom_link: 'https://meet.example.test/j/1' }),
      config({ instructions: 'dial 0000, code 1234' }),
    )!;
    expect(found.found.map(one => one.where)).toEqual([
      'https://meet.example.test/j/1',
      'dial 0000, code 1234',
    ]);
    expect(found.pending).toBeNull();
  });

  it('leaves the instructions out when the series has none to give', () => {
    const found = whereabouts(
      ROOM,
      double({ zoom_link: 'https://meet.example.test/j/1' }),
      config({ instructions: '' }),
    )!;
    expect(found.found).toHaveLength(1);
  });

  it('says nothing is on record only when neither source has anything', () => {
    const found = whereabouts(
      ROOM,
      double({ zoom_link: '' }),
      config({ instructions: '' }),
    )!;
    expect(found.found).toEqual([]);
    expect(found.pending).toContain('No way into the room');
  });

  it('reports the series instructions when the record has no link of its own', () => {
    // The defect. D-06 is that the account *is* the permanent room, so
    // `zoom_link` is empty by design on such an account and the way in lives
    // in the series instructions. `confirmation.py` was taught to read both;
    // this was not, and a volunteer preparing the seminar then read "No room
    // link is on this record yet" on the very screen whose e-mail was
    // carrying the link.
    const found = whereabouts(
      ROOM,
      double({ zoom_link: '' }),
      config({ instructions: 'Join online: https://example.test/room' }),
    )!;
    expect(found.pending).toBeNull();
    expect(found.found).toHaveLength(1);
    expect(found.found[0].where).toContain('https://example.test/room');
  });

  it('shows one line when the per-event link is a spelling of the series one', () => {
    // Confusing rather than false, and reachable by doing exactly what
    // `convener-check-config` invites: filling a per-event field on an
    // account that has no per-event room.
    const link = 'https://example.test/room';
    const found = whereabouts(
      ROOM,
      double({ zoom_link: link }),
      config({ instructions: `Join online: ${link}` }),
    )!;
    expect(found.found).toHaveLength(1);
  });

  it('shows both when they are genuinely two facts', () => {
    // Non-vacuity for the clause above: a one-off room for this edition and a
    // series-wide note about how to get in are two things, and collapsing
    // them would lose the one the registrant actually needs.
    const found = whereabouts(
      ROOM,
      double({ zoom_link: 'https://example.test/one-off' }),
      config({ instructions: 'Access code: 8842798' }),
    )!;
    expect(found.found).toHaveLength(2);
  });

  it('needs no token, because the room is read off the record either way', () => {
    // D-06: the meeting account is the permanent room, so
    // `PlatformFCC.get_room` reads the same `zoom_link` `ManualPlatform`
    // does rather than calling the API. Nothing here may grow a condition
    // on an integration that does not decide this.
    const source = read('app/src/state/artefacts.ts');
    expect(source).not.toContain('CONVENER_MEETING_API_TOKEN');
    expect(read('tools/convener_ops/journey/platform_fcc.py')).toContain(
      'get_room does not call the API',
    );
  });
});

describe('a promotion line points at the list rather than repeating it', () => {
  it('answers for a channel key the product has never seen', () => {
    const invented: RunbookItem = channelItem({ key: 'noticeboards', label: 'Put up on the noticeboards' });
    const found = whereabouts(invented, scheduled, config())!;
    expect(found.found).toHaveLength(1);
    expect(found.found[0].where).toContain(DOWNLOAD.artefact);
  });

  it('names the line it sends the reader to, by that line’s own label', () => {
    const invented: RunbookItem = channelItem({ key: 'posters', label: 'Posters printed and put up' });
    const found = whereabouts(invented, scheduled, config())!;
    expect(found.found[0].what).toContain(VISUALS.label);
  });
});

describe('a line handing over a template says the filled-in one exists', () => {
  it('maps each one to a runbook line, a template page and a rendered text', () => {
    // Four sides, and this is what holds them together. The line hands over
    // a toolkit page; `announce.py` renders that same page from the record;
    // `publication.py` writes the result under a name; and this module puts
    // that name on the line. Any one of the four renamed without the others
    // is a volunteer retyping a text that already exists, which is what this
    // closes.
    expect(DOWNLOAD.drafted.length).toBe(DOWNLOAD.texts.length);
    for (const { key, file, page } of DOWNLOAD.drafted) {
      const item = itemByKey(key);
      expect(item, `${key} is not a runbook line`).not.toBeUndefined();
      expect(item!.contentKey, `${key} hands over no template`).toBe(`toolkit/${page}`);
      expect([...DOWNLOAD.texts]).toContain(file);
      expect(ANNOUNCE, `announce.py names no ${page}`).toContain(
        `docs/handbook/toolkit/${page}.md`,
      );
      expect(RENDER).toContain(`texts["${file.replace(/\.md$/, '')}"]`);
    }
  });

  it('points at the one text this line’s own template was rendered into', () => {
    const found = whereabouts(itemByKey('scheduled/T-21/linkedin')!, scheduled, config())!;
    expect(found.found.map(one => one.where)).toEqual(['mrg-05/network.md']);
    expect(found.from?.href).toBe(visualsWorkflowUrl());
  });

  it('leaves the images on the line whose subject they are', () => {
    const found = whereabouts(itemByKey('scheduled/T-7/forum-announce')!, scheduled, config())!;
    for (const image of DOWNLOAD.images) {
      expect(found.found.map(one => one.where)).not.toContain(`mrg-05/${image}`);
    }
  });

  it('says why there is nothing yet, in the same words the images line uses', () => {
    const found = whereabouts(
      itemByKey('scheduled/T-21/mailing-list')!,
      double({ edition_code: '' }),
      config(),
    )!;
    expect(found.found).toEqual([]);
    expect(found.pending).toBe(whereabouts(VISUALS, double({ edition_code: '' }), config())!.pending);
  });
});

describe('every other line is left alone', () => {
  it('answers nothing for a line that asks for nothing to be fetched', () => {
    for (const key of [
      'scheduled/T-7/seed-questions',
      'scheduled/T-21/promotion-starting',
      'scheduled/T-0/recording-talk-started',
      'delivered/forum-summary',
      'lead/acknowledge-proposal',
    ]) {
      expect(whereabouts(itemByKey(key)!, scheduled, config())).toBeNull();
    }
  });
});
