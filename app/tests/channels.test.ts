/**
 * The promotion channels, and the one thing worth pinning about them.
 *
 * Not that there are seven. The seven in `instance/data/config.yml` are configuration
 * precisely because nobody here can confirm they are still the right seven --
 * that would mean asking the collaborators, which this project never does --
 * so a test counting them would freeze exactly what the data file exists to
 * leave free, and the next volunteer to add a channel would meet a red suite.
 *
 * What is pinned instead is that the list *comes from the file*: a config
 * naming one channel yields that one channel, whatever it is called; the real
 * `instance/data/config.yml` yields whatever that file happens to say, compared
 * against the file itself rather than against a list retyped here; and the
 * module's own source carries none of the keys or labels, so a hard-coded
 * list cannot be reintroduced without a red test even if every other
 * assertion here were satisfied by it.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import yaml from 'js-yaml';
import { channelItem, channelsOf } from '../src/state/channels';
import { itemAssignee } from '../src/state/assignment';
import { isItemDone } from '../src/state/phases';
import { parseConfig } from '../src/data/yaml';
import { DataShapeError } from '../src/data/validate';
import { config, configYaml, speaker } from './data-doubles';
import type { Channel, Config } from '../src/data/types';

/** `instance/data/config.yml` as it stands in the repository, not a copy of it. */
function repoConfigText(): string {
  return readFileSync(resolve(__dirname, '../../instance/data/config.yml'), 'utf8');
}

/** The channels that file lists, read straight from the YAML, so the
 *  assertions below compare the module against the file and never against a
 *  list retyped in this suite. */
function channelsOnFile(): Channel[] {
  return (yaml.load(repoConfigText()) as { channels: Channel[] }).channels;
}

/** The message of the refusal `run` produces, or a failure if it produced none. */
function refusal(run: () => unknown): string {
  try {
    run();
  } catch (e) {
    expect(e).toBeInstanceOf(DataShapeError);
    return (e as Error).message;
  }
  throw new Error('expected a refusal, and the read went through');
}

describe('the list comes from the file', () => {
  it('reads the channels from config, not from a constant', () => {
    const cfg: Config = config({ channels: [{ key: 'only', label: 'Only one' }] });
    expect(channelsOf(cfg).map(c => c.key)).toEqual(['only']);
    expect(channelsOf(cfg).map(c => c.label)).toEqual(['Only one']);
  });

  it('follows the file when the file says something else entirely', () => {
    const cfg = config({
      channels: [
        { key: 'pigeon-post', label: 'Pigeon post' },
        { key: 'town_crier', label: 'Town crier' },
        { key: 'forum', label: 'The forum, renamed' },
      ],
    });
    expect(channelsOf(cfg)).toEqual([
      { key: 'pigeon-post', label: 'Pigeon post' },
      { key: 'town_crier', label: 'Town crier' },
      { key: 'forum', label: 'The forum, renamed' },
    ]);
  });

  it('gives back what instance/data/config.yml says, compared against that file itself', () => {
    expect(channelsOf(parseConfig(repoConfigText()))).toEqual(channelsOnFile());
  });

  it('names no channel in its own source, so no constant can shadow the file', () => {
    const source = readFileSync(resolve(__dirname, '../src/state/channels.ts'), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/\/\/[^\n]*/g, '');
    for (const channel of channelsOnFile()) {
      expect(source).not.toContain(channel.key);
      expect(source).not.toContain(channel.label);
    }
  });

  it('hands back a list the caller cannot write back into the config through', () => {
    const cfg = config({ channels: [{ key: 'forum', label: 'Forum' }] });
    channelsOf(cfg).push({ key: 'sneaked-in', label: 'Sneaked in' });
    expect(channelsOf(cfg).map(c => c.key)).toEqual(['forum']);
  });
});

describe('a list that cannot be read is refused, never silently emptied', () => {
  it('accepts an empty list, which means nothing is promoted through this app', () => {
    expect(channelsOf(config({ channels: [] }))).toEqual([]);
    expect(parseConfig(configYaml({ channels: [] })).channels).toEqual([]);
  });

  it('refuses a config with no channels at all, naming the file and the field', () => {
    const message = refusal(() =>
      channelsOf({ ...config(), channels: undefined } as unknown as Config),
    );
    expect(message).toContain('instance/data/config.yml');
    expect(message).toContain('"channels"');
  });

  it('refuses a channels that is not a list', () => {
    const message = refusal(() =>
      channelsOf({ ...config(), channels: 'forum' } as unknown as Config),
    );
    expect(message).toContain('"channels"');
  });

  it('says who can fix it, and does not blame whoever opened the app', () => {
    const message = refusal(() => channelsOf({ ...config(), channels: null } as unknown as Config));
    expect(message).toContain('Someone with access to the repository');
    expect(message.toLowerCase()).not.toContain('you ');
  });
});

describe('the file is read field by field, with the position named', () => {
  it('refuses a file with the channels key missing', () => {
    const text = configYaml().replace(/channels:[\s\S]*$/, '');
    expect(refusal(() => parseConfig(text))).toContain('missing "channels"');
  });

  it('refuses a channels that reads as something other than a list', () => {
    const text = configYaml().replace(/channels:[\s\S]*$/, 'channels: 7\n');
    const message = refusal(() => parseConfig(text));
    expect(message).toContain('instance/data/config.yml');
    expect(message).toContain('"channels"');
    expect(message).toContain('list');
  });

  it('names the entry when one channel is not a block', () => {
    const text = configYaml().replace(/channels:[\s\S]*$/, 'channels:\n- forum\n');
    expect(refusal(() => parseConfig(text))).toContain('channels entry 1');
  });

  it('names the entry when a key is not a key anything could be stored under', () => {
    const text = configYaml().replace(
      /channels:[\s\S]*$/,
      'channels:\n- key: Forum Announcement\n  label: Forum\n',
    );
    const message = refusal(() => parseConfig(text));
    expect(message).toContain('channels entry 1');
    expect(message).toContain('lower-case');
  });

  it('refuses a channel with nothing to show anyone', () => {
    const text = configYaml().replace(
      /channels:[\s\S]*$/,
      "channels:\n- key: forum\n  label: '  '\n",
    );
    expect(refusal(() => parseConfig(text))).toContain('no label');
  });

  it('refuses an entry carrying a setting this app does not use', () => {
    const text = configYaml().replace(
      /channels:[\s\S]*$/,
      'channels:\n- key: forum\n  label: Forum\n  owner: ada\n',
    );
    expect(refusal(() => parseConfig(text))).toContain('"owner"');
  });

  it('refuses two channels sharing a key, naming the earlier one', () => {
    const text = configYaml().replace(
      /channels:[\s\S]*$/,
      'channels:\n- key: forum\n  label: Forum\n- key: risc\n  label: RISC\n' +
        '- key: forum\n  label: Forum again\n',
    );
    const message = refusal(() => parseConfig(text));
    expect(message).toContain('channel 3');
    expect(message).toContain('channel 1');
  });
});

describe('a channel is a line of the journey like any other', () => {
  const channel: Channel = { key: 'teatime', label: 'TEATIME mailing list' };
  const item = channelItem(channel);

  it('is a checkbox keyed by the channel, labelled in the words of the file', () => {
    expect(item.form).toBe('checkbox');
    expect(item.key).toBe('promotion/teatime');
    expect(item.label).toBe('TEATIME mailing list');
  });

  it('keys the line on the channel key and not on its wording', () => {
    expect(channelItem({ ...channel, label: 'Liste de diffusion TEATIME' }).key).toBe(item.key);
  });

  it('carries an owner through the checklist, with nothing added to the model', () => {
    const s = speaker({ checklist: { [item.key]: { assignee: 'ada' } } });
    expect(itemAssignee(s, item.key)).toBe('ada');
    expect(Object.keys(s.checklist[item.key])).toEqual(['assignee']);
  });

  it('is nobody in particular until somebody is named, like every other line', () => {
    expect(itemAssignee(speaker({ assigned_to: 'ada', host_1: 'bob' }), item.key)).toBe('');
  });

  it('is outstanding until it is ticked, read the one way the app reads done', () => {
    expect(isItemDone(speaker(), item)).toBe(false);
    expect(isItemDone(speaker({ runbook_progress: { [item.key]: true } }), item)).toBe(true);
  });

  it('gives every channel of a config a line of its own', () => {
    const cfg = config({
      channels: [
        { key: 'forum', label: 'Forum' },
        { key: 'risc', label: 'RISC newsletter' },
      ],
    });
    expect(channelsOf(cfg).map(c => channelItem(c).key)).toEqual([
      'promotion/forum',
      'promotion/risc',
    ]);
  });
});
