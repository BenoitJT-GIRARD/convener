/**
 * What the demonstration carries, against what its settings screen draws.
 *
 * The build used to hand the cockpit every configuration file in the
 * repository. The screen shows the ones the instance owns and filters the
 * rest out, so `declarations/standing-up.yml` -- sixty-nine kilobytes of
 * standing-up sequence, owned by the product -- was compiled into every
 * bundle and drawn nowhere. Since the demonstration is hosted, strangers
 * downloaded it too.
 *
 * The fix is a derivation, and a derivation can be wrong in one direction
 * that no byte count would catch: a file the screen *does* read left behind.
 * So this drives the screen's own readers over what the build carries and
 * over every file on disk, and refuses any difference between the two --
 * the same list of owned paths, the same integrations, the same text under
 * every field of the form. What shrinks is what nothing reads.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import * as yaml from 'js-yaml';
import { carriedFrom } from '../../scripts/example-settings.mjs';
import {
  BOUNDARY_PATH,
  CONFIG_SUFFIXES,
  INTEGRATIONS_PATH,
  configOwner,
  handedFromData,
  instancePaths,
  integrationsFromData,
} from '../../src/settings/declaration';
import { SETTINGS } from '../../src/settings/form';

const ROOT = resolve(__dirname, '../../..');
const EXAMPLE = 'examples/the-example-collective';

function read(relative: string): string {
  return readFileSync(resolve(ROOT, relative), 'utf-8');
}

/** Every configuration file the signed-in screen would list and read, with
 *  the example's own copies standing in for the instance's -- which is what
 *  the build carried before it started deriving. */
function everyFile(): Record<string, string> {
  const files: Record<string, string> = {};
  for (const name of readdirSync(resolve(ROOT, 'declarations')).sort()) {
    if (CONFIG_SUFFIXES.some(suffix => name.endsWith(suffix))) {
      files[`declarations/${name}`] = read(`declarations/${name}`);
    }
  }
  for (const name of readdirSync(resolve(ROOT, EXAMPLE, 'instance')).sort()) {
    if (CONFIG_SUFFIXES.some(suffix => name.endsWith(suffix))) {
      files[`instance/${name}`] = read(`${EXAMPLE}/instance/${name}`);
    }
  }
  return files;
}

/** What the screen makes of one set of bytes: the two questions it asks and
 *  the values every field of the form is filled from. */
function asScreenReadsIt(files: Record<string, string>) {
  const owners: Record<string, string> = {};
  for (const [name, text] of Object.entries(files)) owners[name] = configOwner(name, text);
  const handed = handedFromData(yaml.load(files[BOUNDARY_PATH] ?? ''));
  return {
    owned: instancePaths(handed, owners),
    integrations: integrationsFromData(yaml.load(files[INTEGRATIONS_PATH] ?? '')),
    fields: SETTINGS.map(setting => [setting.file, setting.key, files[setting.file]] as const),
  };
}

const all = everyFile();
const carried: Record<string, string> = carriedFrom(all);

describe('the demonstration carries what its screen will show', () => {
  it('reads a real repository, so an empty comparison cannot pass', () => {
    expect(Object.keys(all).length).toBeGreaterThan(Object.keys(carried).length);
    expect(SETTINGS.length).toBeGreaterThan(5);
  });

  it('leaves out a file nothing on the screen reads, by name', () => {
    // The one this was measured on. Named rather than counted: a test that
    // only asserted "fewer files" would pass on a build that dropped the
    // boundary itself.
    expect(Object.keys(all)).toContain('declarations/standing-up.yml');
    expect(Object.keys(carried)).not.toContain('declarations/standing-up.yml');
  });

  it('carries the two files the screen parses whole, whoever owns them', () => {
    expect(Object.keys(carried)).toContain(BOUNDARY_PATH);
    expect(Object.keys(carried)).toContain(INTEGRATIONS_PATH);
    expect(configOwner(BOUNDARY_PATH, carried[BOUNDARY_PATH])).toBe('product');
  });

  it('carries every file the instance owns, which is what the screen lists', () => {
    const owned = Object.entries(all)
      .filter(([name, text]) => configOwner(name, text) === 'instance')
      .map(([name]) => name);
    expect(owned.length).toBeGreaterThan(3);
    for (const name of owned) expect(carried[name]).toBe(all[name]);
  });

  it('draws exactly the screen it drew when every file travelled', () => {
    expect(asScreenReadsIt(carried)).toEqual(asScreenReadsIt(all));
  });
});
