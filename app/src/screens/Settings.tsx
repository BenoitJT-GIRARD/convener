/**
 * This instance's own settings -- settled where they can be checked.
 *
 * Phase 11, task 5. **A file cannot refuse a value; a form can.** That is
 * the whole argument for this screen, and there is one case that proves it
 * rather than illustrating it: `config/queue-drain.yml`'s
 * `alarm_after_hours` is bounded on *both* sides by other declarations --
 * its floor is twice the drain's own cron period, its ceiling is
 * `config/registration-lanes.yml`'s `queue_beyond_hours` minus the same --
 * and with this repository's settings those two meet exactly at 48. There
 * is precisely one legal value, and nothing in the file tells anybody
 * editing it. A test says so, later, somewhere else. A field says so as
 * they type.
 *
 * What it edits, and what it only reports
 * ---------------------------------------
 * The set of things this instance owns is not typed into this file: it is
 * read from `config/boundary.yml` and from each `config/` file's own
 * `owner:` header, exactly as `tools/convener_ops/boundary.py` reads it
 * (`../settings/declaration.ts`). Of the eight paths that come back, three
 * are files of numbers and this screen offers them as a form. The other
 * five are not "not implemented": each one is a path a form is the wrong
 * instrument for, and `form.ts::whyNotAForm` says which reason applies --
 * a directory the other screens already are, cryptographic material no
 * field could hold, output a workflow regenerates, and one file the
 * *build* reads, whose values this very bundle was compiled with and which
 * therefore cannot change under it.
 *
 * What it never does
 * ------------------
 * **Accept a secret.** The cockpit is a static bundle, served publicly,
 * writing with the signed-in person's token; a token that could write a
 * repository secret would be a right every Board member held, which is
 * precisely what the 2026-08-23 security audit named and declined to close
 * at zero cost. So there is no field for one anywhere below. What there is
 * instead is a report -- which integrations are configured, which are not,
 * and what the code does without each -- built from
 * `config/integrations.yml`, which already carries exactly that matter, and
 * from the *names* GitHub will give for a repository's secrets and
 * variables. Never a value; see `../settings/secrets.ts`.
 *
 * When a change takes effect
 * --------------------------
 * Not on save, in every case, and the differences matter enough to be
 * printed beside each field rather than once at the top: `deploy.yml`
 * ignores `config/**`, so committing here starts nothing. The queue alarm
 * is live at the next run of the daily sweep; the lane threshold reaches
 * the registration relay only once *Deploy app* has regenerated
 * `public-data/registration-routing.json`, and until then registrations
 * route on the threshold already published there. See `../settings/form.ts`.
 */
import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { Button } from '../components/Button';
import { isDemoMode } from '../data/demo';
import { githubStore } from '../github/contents';
import { friendlyError } from '../github/errors';
import { mutate } from '../github/mutate';
import { configEdit, settingKey, settingsFile } from '../state/decisions';
import { alarmBounds, checkSetting, laneFloorHours, silenceFloorDays } from '../settings/bounds';
import type { Coupling, Refusal } from '../settings/bounds';
import { INSTANCE } from '../settings/declaration';
import { EditRefused, alreadySays, setScalar } from '../settings/edit';
import { SETTINGS, editableFiles, whyNotAForm } from '../settings/form';
import type { Setting } from '../settings/form';
import { couplingOf, loadSettings } from '../settings/load';
import type { SettingsDocument } from '../settings/load';
import { SECRETS_SETTINGS_PATH, loadSecretNames, reportAll } from '../settings/secrets';
import type { IntegrationReport, SecretNames } from '../settings/secrets';

/** The identity of a field, for the draft map. Not a path: two files carry
 *  a `max_silent_days` and they are different settings. */
function fieldId(setting: Setting): string {
  return `${setting.file}#${setting.key}`;
}

/** What a field currently holds in the repository, as text. */
function storedText(source: SettingsDocument, setting: Setting): string {
  const line = (source.files[setting.file] ?? '')
    .split('\n')
    .find(one => one.startsWith(`${setting.key}:`));
  return line === undefined ? '' : line.slice(setting.key.length + 1).trim();
}

/** The number a field holds, or `NaN` -- which every check below refuses by
 *  the same path an out-of-range value takes, so an empty field is not a
 *  special case anybody has to remember. */
function typed(raw: string): number {
  return raw.trim() === '' ? Number.NaN : Number(raw);
}

function Refused({ refusal }: { refusal: Refusal }) {
  return (
    <p role="alert" className="mt-1 text-xs text-danger">
      <strong className="uppercase tracking-wider mr-1">{refusal.bound}</strong>
      {refusal.message}
    </p>
  );
}

/** One number, its bound, and when saving it changes anything. */
function SettingField({
  setting,
  value,
  onChange,
  refusal,
  stored,
}: {
  setting: Setting;
  value: string;
  onChange: (next: string) => void;
  refusal: Refusal | null;
  stored: string;
}) {
  return (
    <div className="py-3 border-t border-border">
      <label className="block">
        <span className="text-xs uppercase tracking-wider text-ink-muted">
          {setting.label}
        </span>
        <span className="flex items-baseline gap-2 mt-1">
          <input
            className="w-32 px-3 py-2 border border-border rounded-md bg-surface text-sm font-mono"
            type="number"
            step="any"
            aria-label={`${setting.key} in ${setting.file}`}
            value={value}
            onChange={event => onChange(event.target.value)}
          />
          <span className="text-xs text-ink-muted">{setting.unit}</span>
          <span className="text-[10px] font-mono text-ink-faint">
            {setting.key} · {setting.file}
            {/* The two ends of the coupling, marked: each bounds the other,
                and moving one to make room for the other is the manoeuvre
                nothing tells anybody about outside this screen. */}
            {setting.coupled && ' · coupled'}
          </span>
        </span>
      </label>
      <p className="mt-1 text-xs text-ink-muted">{setting.what}</p>
      {refusal ? (
        <Refused refusal={refusal} />
      ) : (
        <p className="mt-1 text-xs text-ink-faint">
          Saved, this takes effect {setting.effect.when} ({setting.effect.where})
          {value.trim() !== stored && stored !== '' && ` The file says ${stored} today.`}
        </p>
      )}
    </div>
  );
}

/** The sentence that says what the two coupled thresholds currently leave
 *  each other. Printed whether or not anything is wrong: the point of this
 *  screen is that somebody can see the room they have before they need
 *  it. */
function CouplingNote({ coupling }: { coupling: Coupling }) {
  const { floor, ceiling } = alarmBounds(coupling.periodHours, coupling.queueBeyondHours);
  return (
    <p className="text-sm text-ink-muted">
      The drain runs every {coupling.periodHours} hours (
      <code className="font-mono text-xs">{coupling.cron}</code>), so the queue alarm
      may fire no earlier than <strong>{floor}</strong> and no later than{' '}
      <strong>{ceiling}</strong> hours.{' '}
      {floor === ceiling && (
        <>
          Those two meet, so <strong>{floor}</strong> is the only value this pair
          admits: raising the immediate-lane threshold below is what buys any room
          at all.
        </>
      )}
      {floor > ceiling && (
        <>
          Those two have crossed, so no alarm is legal at all — the immediate-lane
          threshold has to move first.
        </>
      )}{' '}
      The silence tolerance is floored at {silenceFloorDays(coupling.periodHours)} day(s),
      and the lane threshold at {laneFloorHours(coupling.periodHours)} hours, from the
      same cadence.
    </p>
  );
}

function IntegrationRow({ report }: { report: IntegrationReport }) {
  const { integration, state, missing, family } = report;
  const tone =
    state === 'configured'
      ? 'text-primary'
      : state === 'unknown'
        ? 'text-ink-muted'
        : integration.absentIsNormal
          ? 'text-accent'
          : 'text-danger';
  return (
    <li className="py-3 border-t border-border">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <span className="font-medium text-sm">{integration.label}</span>
        <span className={`font-mono text-[11px] uppercase tracking-wider ${tone}`}>
          {state}
          {!integration.absentIsNormal && state !== 'configured' && ' · not a normal state'}
        </span>
      </div>
      <p className="mt-1 text-xs text-ink-muted">
        <span className="font-mono">{integration.secrets.join(', ') || 'no declared input'}</span>
        {family && ` · ${family.count} set under ${family.prefix}`}
      </p>
      {missing.length > 0 && (
        <p className="mt-1 text-xs text-ink-faint">
          Not set: <span className="font-mono">{missing.join(', ')}</span> — set it in{' '}
          {SECRETS_SETTINGS_PATH}, never here.
        </p>
      )}
      <p className="mt-1 text-xs text-ink-muted">
        <strong className="uppercase tracking-wider text-[10px] mr-1">Without it</strong>
        {integration.absentBehaviour}
      </p>
    </li>
  );
}

export function Settings() {
  const { token } = useAuth();
  const [doc, setDoc] = useState<SettingsDocument | null>(null);
  const [names, setNames] = useState<SecretNames | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const adopt = useCallback((next: SettingsDocument) => {
    setDoc(next);
    const fresh: Record<string, string> = {};
    for (const setting of SETTINGS) fresh[fieldId(setting)] = storedText(next, setting);
    setDraft(fresh);
  }, []);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    loadSettings(token)
      .then(next => {
        if (!cancelled) adopt(next);
      })
      .catch(e => {
        if (!cancelled) setError(friendlyError(e, 'load'));
      });
    loadSecretNames(token)
      .then(next => {
        if (!cancelled) setNames(next);
      })
      .catch(() => {
        /* `loadSecretNames` resolves with its own refusal; this is belt. */
      });
    return () => {
      cancelled = true;
    };
  }, [token, adopt]);

  if (error !== null) {
    return (
      <div className="space-y-4">
        <h1 className="font-display text-2xl font-bold">Settings</h1>
        <p className="text-danger">{error}</p>
      </div>
    );
  }
  if (doc === null || !token) {
    return <div className="p-8 text-ink-muted">Loading…</div>;
  }

  const coupling = couplingOf(doc);
  const refusalFor = (setting: Setting): Refusal | null =>
    coupling === null
      ? null
      : checkSetting(setting.file, setting.key, typed(draft[fieldId(setting)] ?? ''), coupling);

  const changed = SETTINGS.filter(setting => {
    const value = typed(draft[fieldId(setting)] ?? '');
    if (Number.isNaN(value)) return false;
    return !alreadySays(doc.files[setting.file] ?? '', setting.key, value);
  });
  const refused = SETTINGS.map(refusalFor).filter(one => one !== null);

  async function save(current: SettingsDocument, holder: string) {
    if (coupling === null || refused.length > 0 || changed.length === 0) return;
    setSaving(true);
    setSaveError(null);
    const written: string[] = [];
    const files = { ...current.files };
    try {
      for (const setting of changed) {
        const value = typed(draft[fieldId(setting)] ?? '');
        const message = configEdit(settingsFile(setting.file), settingKey(setting.key));
        if (isDemoMode()) {
          // The same short circuit `DataContext` keeps for the demonstration:
          // the edit is applied in memory and nothing is written anywhere.
          // `net/request.ts` would refuse the write in any case; this is what
          // makes the demonstration show the result rather than an error.
          files[setting.file] = setScalar(files[setting.file] ?? '', setting.key, value);
        } else {
          const result = await mutate({
            store: githubStore(holder),
            path: setting.file,
            parse: (text: string) => text,
            serialize: (text: string) => text,
            transform: (current: string) => setScalar(current, setting.key, value),
            message,
          });
          files[setting.file] = result.value;
        }
        written.push(`${setting.key} in ${setting.file}`);
      }
      adopt({ ...current, files });
      setSaved(written);
    } catch (e) {
      setSaveError(
        e instanceof EditRefused ? e.message : friendlyError(e, 'save'),
      );
    } finally {
      setSaving(false);
    }
  }

  const owned = doc.instancePaths;
  const editable = editableFiles();
  const reports = names === null ? [] : reportAll(doc.integrations, names);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-2xl font-bold">Settings</h1>
        <p className="mt-2 text-sm text-ink-muted max-w-prose">
          What this instance owns, read from <code className="font-mono text-xs">config/boundary.yml</code>{' '}
          and from each file&rsquo;s own <code className="font-mono text-xs">owner:</code> header — the
          same declaration the tooling reads, never a list typed into this screen. The
          numbers below are checked here because a file accepts whatever is written into
          it and only a scheduled job finds out.
        </p>
      </div>

      <section>
        <h2 className="font-display text-lg font-bold">What this instance owns</h2>
        <ul className="mt-2">
          {owned.map(path => {
            const here = editable.includes(path);
            const why = whyNotAForm(path);
            return (
              <li key={path} className="py-2 border-t border-border text-sm">
                <span className="font-mono text-xs">{path}</span>
                <span className="ml-2 text-[11px] uppercase tracking-wider text-ink-faint">
                  {doc.owners[path] === INSTANCE ? 'config/' : 'declared'}
                </span>
                <p className="mt-1 text-xs text-ink-muted">
                  {here ? 'Settled below, and checked as you type.' : (why ?? 'No reason is recorded for this path — see app/src/settings/form.ts.')}
                </p>
              </li>
            );
          })}
        </ul>
      </section>

      <section>
        <h2 className="font-display text-lg font-bold">Thresholds</h2>
        {coupling === null ? (
          <p className="mt-2 text-sm text-danger">
            {doc.cadenceRefusal} No bound on this page can be computed, so nothing
            here may be saved.
          </p>
        ) : (
          <div className="mt-2">
            <CouplingNote coupling={coupling} />
          </div>
        )}
        <div className="mt-3">
          {SETTINGS.map(setting => (
            <SettingField
              key={fieldId(setting)}
              setting={setting}
              value={draft[fieldId(setting)] ?? ''}
              stored={storedText(doc, setting)}
              refusal={refusalFor(setting)}
              onChange={next =>
                setDraft(previous => ({ ...previous, [fieldId(setting)]: next }))
              }
            />
          ))}
        </div>
        <div className="mt-4 flex items-center gap-3 flex-wrap">
          <Button
            onClick={() => void save(doc, token)}
            disabled={saving || refused.length > 0 || changed.length === 0}
          >
            {saving ? 'Saving…' : `Save ${changed.length || 'no'} change${changed.length === 1 ? '' : 's'}`}
          </Button>
          {refused.length > 0 && (
            <span className="text-xs text-danger">
              {refused.length} value{refused.length === 1 ? ' is' : 's are'} out of bounds —
              nothing is written while that is true.
            </span>
          )}
          {saved.length > 0 && (
            <span className="text-xs text-ink-muted">Written: {saved.join('; ')}.</span>
          )}
        </div>
        {saveError && (
          <p role="alert" className="mt-2 text-sm text-danger">
            {saveError}
          </p>
        )}
      </section>

      <section>
        <h2 className="font-display text-lg font-bold">Integrations</h2>
        <p className="mt-2 text-sm text-ink-muted max-w-prose">
          Reported, never entered. This cockpit is a static bundle that writes with your
          own token; a token able to write a repository secret would be a right every
          Board member held. So there is no field for one here — only the names GitHub
          will confirm exist, and what each integration is for. Secrets are set in{' '}
          {SECRETS_SETTINGS_PATH}.
        </p>
        {names?.refusal && (
          <p className="mt-2 text-xs text-accent max-w-prose">{names.refusal}</p>
        )}
        <ul className="mt-2">
          {reports.map(report => (
            <IntegrationRow key={report.integration.name} report={report} />
          ))}
        </ul>
      </section>
    </div>
  );
}
