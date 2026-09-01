/**
 * The browser's side of the boundary between an instance threshold and the
 * arithmetic that bounds it.
 *
 * `tools/convener_ops/maintenance/queue_watch.py` and
 * `tools/convener_ops/journey/registration_routing.py` decide what
 * `instance/queue-drain.yml`'s `alarm_after_hours` and
 * `instance/registration-lanes.yml`'s `queue_beyond_hours` may be; the
 * scheduled jobs enforce it, and no browser is running when one runs. The
 * settings screen computes the same bounds where somebody types, because a
 * file takes whatever is written into it and the bound is discovered later
 * -- and with this repository's settings the two ends of that coupling
 * *meet*, so there is exactly one legal alarm and nothing in the file says
 * so.
 *
 * Two copies, one answer. `tools/tests/fixtures/instance-settings.json`
 * holds the cases, `tools/tests/repository/test_instance_settings.py` answers them
 * from Python, and this file answers them from `src/settings/bounds.ts`. A
 * bound the cockpit computed differently from the one the daily job
 * enforces would be worse than no form at all.
 *
 * The two cases that matter most are the two this screen exists for: one
 * hour below the floor and one hour above the ceiling, each refused with a
 * sentence naming the bound and the declaration it comes from -- never
 * "invalid", which is a message that sends a maintainer to edit the file by
 * hand instead.
 */
import { readFileSync } from 'node:fs';
import { readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import yaml from 'js-yaml';
import {
  ACTIONS_BUDGET_FILE,
  CronShapeRefused,
  DRAIN_WORKFLOW,
  QUEUE_DRAIN_FILE,
  REGISTRATION_LANES_FILE,
  alarmBounds,
  checkSetting,
  drainCadence,
  drainSchedule,
  laneFloorHours,
  silenceFloorDays,
} from '../src/settings/bounds';
import type { Coupling } from '../src/settings/bounds';
import { SETTINGS } from '../src/settings/form';
import {
  CONFIG_DIRS,
  CONFIG_SUFFIXES,
  configOwner,
  handedFromData,
  instancePaths,
  integrationsFromData,
} from '../src/settings/declaration';

const ROOT = resolve(__dirname, '..', '..');
const FIXTURE = resolve(ROOT, 'tools', 'tests', 'fixtures', 'instance-settings.json');

interface CadenceCase {
  schedule: unknown;
  hours: number | null;
  why: string;
}
interface BoundsCase {
  period_hours: number;
  queue_beyond_hours: number;
  alarm_floor: number;
  alarm_ceiling: number;
  lane_floor: number;
  silence_floor_days: number;
  why: string;
}
interface EditedKey {
  file: string;
  key: string;
  kind: 'whole' | 'share';
  least: number | null;
}
interface SettingCase {
  file: string;
  key: string;
  value: number;
  context: { period_hours: number; queue_beyond_hours: number; alarm_after_hours: number };
  accepted: boolean;
  bound: 'floor' | 'ceiling' | 'coupling' | null;
  why: string;
}

const fixture = JSON.parse(readFileSync(FIXTURE, 'utf-8'));
const cadenceCases: CadenceCase[] = fixture.drain_cadence.cases;
const boundsCases: BoundsCase[] = fixture.bounds.cases;
const editedKeys: EditedKey[] = fixture.edited.keys;
const settingCases: SettingCase[] = fixture.settings.cases;
const declaredPaths: string[] = fixture.instance_paths.paths;

function couplingFor(one: SettingCase['context'], cron = '0 5 * * *'): Coupling {
  return {
    periodHours: one.period_hours,
    cron,
    queueBeyondHours: one.queue_beyond_hours,
    alarmAfterHours: one.alarm_after_hours,
  };
}

/** Every declaration this repository holds that a refusal may point at. A
 *  message that names none of them is the "invalid" this screen exists to
 *  replace. */
const DECLARATIONS = [
  DRAIN_WORKFLOW,
  QUEUE_DRAIN_FILE,
  REGISTRATION_LANES_FILE,
  ACTIONS_BUDGET_FILE,
];

describe('what a schedule means', () => {
  it('answers every shared cadence case the way the other reader does', () => {
    expect(cadenceCases.length).toBeGreaterThan(4);
    for (const one of cadenceCases) {
      if (one.hours === null) {
        expect(() => drainCadence(one.schedule), one.why).toThrow(CronShapeRefused);
      } else {
        expect(drainCadence(one.schedule).hours, one.why).toBe(one.hours);
      }
    }
  });

  it('has cases on both sides, so neither verdict passes for free', () => {
    expect(cadenceCases.some(one => one.hours !== null)).toBe(true);
    expect(cadenceCases.some(one => one.hours === null)).toBe(true);
  });

  it('carries the cron it read, because every refusal names it', () => {
    expect(drainCadence([{ cron: '0 5 * * *' }]).cron).toBe('0 5 * * *');
  });

  it('names the workflow when it refuses, not just the value', () => {
    expect(() => drainCadence([])).toThrow(DRAIN_WORKFLOW);
    expect(() => drainCadence([{ cron: '0 */6 * * *' }])).toThrow(DRAIN_WORKFLOW);
  });

  it('reads the schedule out of a document under either spelling of `on:`', () => {
    // PyYAML's YAML-1.1 resolver turns `on:` into the boolean `true`; this
    // reader leaves it the string. The difference is met once, here, and it
    // decides nothing.
    const schedule = [{ cron: '0 5 * * *' }];
    expect(drainSchedule({ on: { schedule } })).toEqual(schedule);
    expect(drainSchedule({ true: { schedule } })).toEqual(schedule);
    expect(drainSchedule({ on: 'push' })).toBeUndefined();
    expect(drainSchedule(null)).toBeUndefined();
  });

  it('reads this repository’s own drain workflow', () => {
    const loaded = yaml.load(readFileSync(resolve(ROOT, DRAIN_WORKFLOW), 'utf-8'));
    expect(drainCadence(drainSchedule(loaded)).hours).toBe(24);
  });
});

describe('the bounds the coupling leaves', () => {
  it('is what the fixture pins, case for case', () => {
    for (const one of boundsCases) {
      const { floor, ceiling } = alarmBounds(one.period_hours, one.queue_beyond_hours);
      expect(floor, one.why).toBe(one.alarm_floor);
      expect(ceiling, one.why).toBe(one.alarm_ceiling);
      expect(laneFloorHours(one.period_hours), one.why).toBe(one.lane_floor);
      expect(silenceFloorDays(one.period_hours), one.why).toBe(one.silence_floor_days);
    }
  });

  it('has a case where the two meet and one where they cross', () => {
    expect(boundsCases.some(one => one.alarm_floor === one.alarm_ceiling)).toBe(true);
    expect(boundsCases.some(one => one.alarm_ceiling < one.alarm_floor)).toBe(true);
  });
});

describe('a typed value', () => {
  it('is judged the same way on this side of the boundary', () => {
    for (const one of settingCases) {
      const refusal = checkSetting(one.file, one.key, one.value, couplingFor(one.context));
      expect(refusal === null, `${one.key} = ${one.value}: ${one.why}`).toBe(one.accepted);
    }
  });

  it('is refused by the end the fixture names, and told which', () => {
    for (const one of settingCases.filter(c => !c.accepted)) {
      const refusal = checkSetting(one.file, one.key, one.value, couplingFor(one.context));
      expect(refusal?.bound, one.why).toBe(one.bound);
    }
  });

  it('is never refused with a message that names no declaration', () => {
    for (const one of settingCases.filter(c => !c.accepted)) {
      const refusal = checkSetting(one.file, one.key, one.value, couplingFor(one.context));
      expect(
        DECLARATIONS.some(named => refusal!.message.includes(named)),
        `${one.key} = ${one.value} was refused with "${refusal!.message}"`,
      ).toBe(true);
    }
  });

  it('is refused on both ends of the coupling, an hour either side', () => {
    // The case the whole screen exists for, driven rather than described:
    // today's cadence and lane threshold leave exactly one legal alarm.
    const coupling: Coupling = {
      periodHours: 24,
      cron: '0 5 * * *',
      queueBeyondHours: 96,
      alarmAfterHours: 48,
    };
    const below = checkSetting(QUEUE_DRAIN_FILE, 'alarm_after_hours', 47, coupling);
    const above = checkSetting(QUEUE_DRAIN_FILE, 'alarm_after_hours', 49, coupling);
    expect(checkSetting(QUEUE_DRAIN_FILE, 'alarm_after_hours', 48, coupling)).toBeNull();
    expect(below?.bound).toBe('floor');
    expect(below?.message).toContain(DRAIN_WORKFLOW);
    expect(above?.bound).toBe('ceiling');
    expect(above?.message).toContain(REGISTRATION_LANES_FILE);
    expect(above?.message).toContain('96');
  });

  it('says the pair is impossible when the two bounds have crossed', () => {
    const crossed: Coupling = {
      periodHours: 24,
      cron: '0 5 * * *',
      queueBeyondHours: 72,
      alarmAfterHours: 48,
    };
    const refusal = checkSetting(QUEUE_DRAIN_FILE, 'alarm_after_hours', 48, crossed);
    expect(refusal?.message).toContain('crossed');
    expect(refusal?.message).toContain(REGISTRATION_LANES_FILE);
  });

  it('refuses a key no reader in this repository knows', () => {
    const coupling = couplingFor(settingCases[0].context);
    const refusal = checkSetting(QUEUE_DRAIN_FILE, 'invented_key', 1, coupling);
    expect(refusal?.message).toContain('invented_key');
  });

  it('refuses an empty field by the same path as an out-of-range one', () => {
    const coupling = couplingFor(settingCases[0].context);
    expect(checkSetting(QUEUE_DRAIN_FILE, 'alarm_after_hours', Number.NaN, coupling)).not.toBeNull();
  });
});

describe('the set of settings the form offers', () => {
  it('is exactly the set the readers on the other side know', () => {
    const offered = SETTINGS.map(one => `${one.file}#${one.key}`).sort();
    const declared = editedKeys.map(one => `${one.file}#${one.key}`).sort();
    expect(offered).toEqual(declared);
  });

  it('reads each one back the way the fixture declares it', () => {
    for (const one of editedKeys) {
      const setting = SETTINGS.find(s => s.file === one.file && s.key === one.key);
      expect(setting?.kind, `${one.file}#${one.key}`).toBe(one.kind);
    }
  });

  it('refuses one step below every whole minimum a reader declares', () => {
    const coupling: Coupling = {
      periodHours: 24,
      cron: '0 5 * * *',
      queueBeyondHours: 96,
      alarmAfterHours: 48,
    };
    for (const one of editedKeys.filter(k => k.kind === 'whole')) {
      const refusal = checkSetting(one.file, one.key, one.least! - 1, coupling);
      expect(refusal, `${one.file}#${one.key} at ${one.least! - 1}`).not.toBeNull();
    }
  });

  it('gives every one of them a moment it takes effect, and a workflow', () => {
    for (const setting of SETTINGS) {
      expect(setting.effect.when.length, setting.key).toBeGreaterThan(20);
      expect(setting.effect.where, setting.key).toMatch(/^\.github\/workflows\//);
    }
  });
});

describe('what this instance owns', () => {
  /** The declaration, read from this repository the way the browser reads
   *  it from the repository -- same reader, different source of bytes. */
  function derived(): string[] {
    const boundaryText = readFileSync(resolve(ROOT, 'declarations', 'boundary.yml'), 'utf-8');
    const owners: Record<string, string> = {};
    for (const directory of CONFIG_DIRS) {
      for (const name of readdirSync(resolve(ROOT, directory), { withFileTypes: true })) {
        if (!name.isFile()) continue;
        if (!CONFIG_SUFFIXES.some(suffix => name.name.endsWith(suffix))) continue;
        const path = `${directory}/${name.name}`;
        owners[path] = configOwner(
          path,
          readFileSync(resolve(ROOT, directory, name.name), 'utf-8'),
        );
      }
    }
    return instancePaths(handedFromData(yaml.load(boundaryText)), owners);
  }

  it('is derived from the declaration, and agrees with the other reader', () => {
    expect(derived()).toEqual(declaredPaths);
  });

  it('refuses a declaration that names a configuration file', () => {
    expect(() =>
      handedFromData({
        v: 1,
        owner: 'product',
        instance: [{ path: 'instance/queue-drain.yml', reason: 'because' }],
      }),
    ).toThrow(/one fact two places/);
  });

  it('refuses a config file that declares no owner', () => {
    expect(() => configOwner('declarations/nothing.yml', 'v: 1\n')).toThrow(/declares no owner/);
  });

  it('reads every integration this repository declares, and what breaks without it', () => {
    const text = readFileSync(resolve(ROOT, 'declarations', 'integrations.yml'), 'utf-8');
    const rows = integrationsFromData(yaml.load(text));
    expect(rows.length).toBeGreaterThan(1);
    for (const row of rows) expect(row.absentBehaviour.length).toBeGreaterThan(20);
    // Three rows declare that their absence is not a normal state; one of
    // them is a registration nobody could ever decrypt.
    expect(rows.filter(row => !row.absentIsNormal).length).toBeGreaterThan(0);
  });
});
