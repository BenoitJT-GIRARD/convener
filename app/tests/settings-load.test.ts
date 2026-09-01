/**
 * What the settings screen refuses to read, and what it says instead.
 *
 * Every refusal below exists because the alternative is a screen that shows
 * somebody a boundary, a bound or an integration state it *guessed*. A
 * guessed boundary offers to edit a file upstream owns; a guessed bound
 * tells a maintainer a value is fine that the daily job will go red on; a
 * guessed integration state says "absent" about a secret nobody looked for.
 * A refusal that has never been run is a refusal nobody has checked, so
 * each one is driven here.
 */
import { describe, expect, it, vi } from 'vitest';
import {
  DeclarationRefused,
  configOwner,
  handedFromData,
  instancePaths,
  integrationsFromData,
} from '../src/settings/declaration';
import { cadenceFrom, couplingOf, loadSettings } from '../src/settings/load';
import type { SettingsDocument } from '../src/settings/load';
import { loadSecretNames, reportOn } from '../src/settings/secrets';
import type { Integration } from '../src/settings/declaration';

function declaration(instance: unknown): unknown {
  return { v: 1, owner: 'product', instance };
}

describe('the boundary declaration', () => {
  it('refuses a version this reader does not know', () => {
    expect(() => handedFromData({ v: 2, owner: 'product', instance: [] })).toThrow(
      /supported format version/,
    );
    expect(() => handedFromData('not a mapping')).toThrow(DeclarationRefused);
  });

  it('refuses a declaration that is not the product’s own statement', () => {
    expect(() => handedFromData({ v: 1, owner: 'instance', instance: [] })).toThrow(
      /owner: product/,
    );
  });

  it('refuses an empty list, which would hand the instance nothing at all', () => {
    expect(() => handedFromData(declaration([]))).toThrow(/non-empty list/);
    expect(() => handedFromData(declaration('instance/data/'))).toThrow(/non-empty list/);
  });

  it('refuses an entry with no path, no reason, or no shape', () => {
    expect(() => handedFromData(declaration(['instance/data/']))).toThrow(/not an entry/);
    expect(() => handedFromData(declaration([{ reason: 'because' }]))).toThrow(
      /instance path/,
    );
    expect(() => handedFromData(declaration([{ path: 'instance/data/' }]))).toThrow(/reason/);
  });

  it('reads a kept file and a regenerated flag as the other reader does', () => {
    const handed = handedFromData(
      declaration([
        {
          path: 'instance/data/',
          reason: 'the records',
          kept: [{ path: 'instance/data/schema.md', reason: 'a stub' }],
        },
        { path: 'docs/handbook/governance/register.md', reason: 'the register', regenerated: true },
      ]),
    );
    expect(handed[0].kept).toEqual(['instance/data/schema.md']);
    expect(handed[1].regenerated).toBe(true);
    expect(handed[0].regenerated).toBe(false);
  });

  it('sorts both halves together, so the screen reads as one list', () => {
    const handed = handedFromData(declaration([{ path: 'instance/keys/', reason: 'material' }]));
    expect(
      instancePaths(handed, {
        'instance/queue-drain.yml': 'instance',
        'declarations/boundary.yml': 'product',
      }),
    ).toEqual(['instance/keys/', 'instance/queue-drain.yml']);
  });

  it('reads a JSON file’s owner out of the same key a YAML one uses', () => {
    expect(configOwner('declarations/thing.json', '{"owner": "instance"}')).toBe('instance');
    expect(() => configOwner('declarations/thing.json', '{"owner": "somebody"}')).toThrow(
      /declares no owner/,
    );
  });
});

describe('the integrations declaration', () => {
  it('refuses a file with no rows, rather than reporting none', () => {
    expect(() => integrationsFromData({ integrations: [] })).toThrow(/non-empty list/);
    expect(() => integrationsFromData(null)).toThrow(DeclarationRefused);
    expect(() => integrationsFromData({ integrations: ['smtp'] })).toThrow(/not a row/);
  });

  it('refuses a row that cannot say what breaks without it', () => {
    expect(() =>
      integrationsFromData({ integrations: [{ name: 'a', label: 'A' }] }),
    ).toThrow(/absent_behaviour/);
  });

  it('reads absent_is_normal as declared, defaulting to the ordinary case', () => {
    const rows = integrationsFromData({
      integrations: [
        { name: 'a', label: 'A', absent_behaviour: 'nothing happens', secrets: ['X'] },
        {
          name: 'b',
          label: 'B',
          absent_behaviour: 'something happens',
          absent_is_normal: false,
        },
      ],
    });
    expect(rows[0].absentIsNormal).toBe(true);
    expect(rows[1].absentIsNormal).toBe(false);
    expect(rows[1].secrets).toEqual([]);
  });
});

describe('the cadence, and the bound that rests on it', () => {
  it('reports why it could not read a schedule instead of assuming one', () => {
    const { cadence, cadenceRefusal } = cadenceFrom({ on: { push: {} } });
    expect(cadence).toBeNull();
    expect(cadenceRefusal).toContain('.github/workflows/sweep-and-notify.yml');
  });

  it('has no coupling when either threshold file cannot be read', () => {
    const base: SettingsDocument = {
      files: {},
      owners: {},
      handed: [],
      instancePaths: [],
      integrations: [],
      cadence: { hours: 24, cron: '0 5 * * *' },
      cadenceRefusal: null,
    };
    expect(couplingOf(base)).toBeNull();
    expect(
      couplingOf({
        ...base,
        files: { 'instance/registration-lanes.yml': 'queue_beyond_hours: 96' },
      }),
    ).toBeNull();
    expect(
      couplingOf({
        ...base,
        files: {
          'instance/registration-lanes.yml': 'queue_beyond_hours: 96',
          'instance/queue-drain.yml': 'not: valid: yaml:',
        },
      }),
    ).toBeNull();
    expect(couplingOf({ ...base, cadence: null })).toBeNull();
  });

  it('reads both thresholds when both files hold one', () => {
    expect(
      couplingOf({
        files: {
          'instance/registration-lanes.yml': 'queue_beyond_hours: 96',
          'instance/queue-drain.yml': 'alarm_after_hours: 48',
        },
        owners: {},
        handed: [],
        instancePaths: [],
        integrations: [],
        cadence: { hours: 24, cron: '0 5 * * *' },
        cadenceRefusal: null,
      }),
    ).toEqual({
      periodHours: 24,
      cron: '0 5 * * *',
      queueBeyondHours: 96,
      alarmAfterHours: 48,
    });
  });
});

describe('reading the repository', () => {
  it('refuses a declarations/ that is not a directory rather than showing nothing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: true, json: async () => ({ message: 'not a dir' }) })),
    );
    await expect(loadSettings('tok')).rejects.toThrow(/not a directory/);
    vi.unstubAllGlobals();
  });
});

describe('the integration report', () => {
  function row(overrides: Partial<Integration> = {}): Integration {
    return {
      name: 'email_transport',
      label: 'Outbound email',
      secrets: ['CONVENER_SMTP_HOST', 'CONVENER_SMTP_USER'],
      absentBehaviour: 'nothing is sent',
      absentIsNormal: true,
      ...overrides,
    };
  }

  const answered = { secrets: [] as string[], variables: [] as string[], refusal: null };

  it('is unknown when the question could not be asked', () => {
    const report = reportOn(row(), { secrets: [], variables: [], refusal: 'no access' });
    expect(report.state).toBe('unknown');
    expect(report.missing).toEqual([]);
  });

  it('is unknown for a row declaring no input at all', () => {
    expect(reportOn(row({ secrets: [] }), answered).state).toBe('unknown');
  });

  it('reads a variable name as readily as a secret one', () => {
    const report = reportOn(row({ secrets: ['VITE_AUTH_PROXY_URL'] }), {
      ...answered,
      variables: ['VITE_AUTH_PROXY_URL'],
    });
    expect(report.state).toBe('configured');
  });

  it('says partial when some of an integration’s inputs are set', () => {
    const report = reportOn(row(), { ...answered, secrets: ['CONVENER_SMTP_HOST'] });
    expect(report.state).toBe('partial');
    expect(report.missing).toEqual(['CONVENER_SMTP_USER']);
  });

  it('counts a family rather than answering yes or no about it', () => {
    const declared = row({ name: 'event_keys', secrets: ['CONVENER_EVENT_KEY_<ID>'] });
    const none = reportOn(declared, answered);
    expect(none.state).toBe('absent');
    expect(none.family).toEqual({ prefix: 'CONVENER_EVENT_KEY_', count: 0 });

    const some = reportOn(declared, {
      ...answered,
      secrets: ['CONVENER_EVENT_KEY_MRG_05', 'CONVENER_EVENT_KEY_MRG_06', 'CONVENER_SIGNING_KEY'],
    });
    expect(some.state).toBe('configured');
    expect(some.family?.count).toBe(2);
  });

  it('never asks for a value, and reports the refusal when it is refused', async () => {
    const asked: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        asked.push(url);
        return Promise.resolve({ ok: false, status: 403, text: async () => 'forbidden' });
      }),
    );
    const names = await loadSecretNames('tok');
    expect(names.refusal).toContain('never a value');
    expect(asked.every(url => url.includes('/actions/'))).toBe(true);
    vi.unstubAllGlobals();
  });

  it('takes names and nothing else out of an answer that carried more', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        Promise.resolve({
          ok: true,
          json: async () =>
            url.includes('variables')
              ? { variables: [{ name: 'VITE_AUTH_PROXY_URL', value: 'https://relay.example' }] }
              : { secrets: [{ name: 'CONVENER_SIGNING_KEY' }, { notName: 1 }] },
        }),
      ),
    );
    const names = await loadSecretNames('tok');
    expect(names.variables).toEqual(['VITE_AUTH_PROXY_URL']);
    expect(names.secrets).toEqual(['CONVENER_SIGNING_KEY']);
    expect(JSON.stringify(names)).not.toContain('relay.example');
    vi.unstubAllGlobals();
  });
});
