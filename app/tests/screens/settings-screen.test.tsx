/**
 * The settings screen, driven.
 *
 * What is being held here is one claim and its two
 * halves: **a file cannot refuse a value; a form can** -- so the screen has
 * to refuse an illegal one *at the point of entry*, on both ends of the
 * coupling, with a sentence naming the bound and where it comes from; and
 * it has to write a legal one to the file it names, through the one door,
 * leaving the file's own argument for itself intact.
 *
 * Everything below is served by a stand-in for the Contents API built from
 * **this repository's own declarations**, not from samples: the whole
 * point of the coupling is that today's declarations leave exactly one
 * legal alarm, and a fixture invented to make the arithmetic pleasant would
 * be exercising a repository nobody has.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import * as yaml from 'js-yaml';
import { AuthProvider } from '../../src/auth/AuthContext';
import { DataProvider } from '../../src/data/DataContext';
import { Settings } from '../../src/screens/Settings';
import {
  CONFIG_DIRS,
  CONFIG_SUFFIXES,
  integrationsFromData,
} from '../../src/settings/declaration';
import { SETTINGS, editableFiles } from '../../src/settings/form';

const ROOT = resolve(__dirname, '../..', '..');

function encodeUtf8(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function decodeUtf8(b64: string): string {
  const bin = atob(b64.replace(/\n/g, ''));
  const bytes = Uint8Array.from(bin, c => c.charCodeAt(0));
  return new TextDecoder('utf-8').decode(bytes);
}

/** Every configuration file this repository holds, by path -- both the
 *  directories `CONFIG_DIRS` names, which is what the screen lists. */
function realConfig(): Record<string, string> {
  const files: Record<string, string> = {};
  for (const directory of CONFIG_DIRS) {
    for (const entry of readdirSync(resolve(ROOT, directory), { withFileTypes: true })) {
      if (!entry.isFile()) continue;
      if (!CONFIG_SUFFIXES.some(suffix => entry.name.endsWith(suffix))) continue;
      files[`${directory}/${entry.name}`] = readFileSync(
        resolve(ROOT, directory, entry.name),
        'utf-8',
      );
    }
  }
  return files;
}

const DRAIN_WORKFLOW = '.github/workflows/sweep-and-notify.yml';

interface Backend {
  fetchMock: ReturnType<typeof vi.fn>;
  files: Record<string, string>;
  subjects: string[];
}

/**
 * A stand-in for the Contents API and the two Actions listings.
 *
 * `secrets` and `variables` answer with **names only**, exactly as the real
 * endpoints do -- there is no value anywhere in this double, because there
 * is none in the real answer either and a test that invented one would be
 * describing a screen this repository must never have.
 */
function makeBackend(
  options: {
    secretNames?: string[];
    refuseSecrets?: boolean;
    refuseWith?: number;
    /** Who is signed in. Board by default, because that is who these
     *  thresholds are for -- and because a harness that signed everybody in
     *  as an organizer would make every saving test here prove the gate
     *  rather than the bound it was written for. */
    role?: 'board' | 'organizer';
  } = {},
): Backend {
  // 403 unless the test says otherwise: that is what a user-to-server token
  // gets for a permission its App does not hold, and it is the refusal the
  // screen has to read as a boundary rather than as a failure.
  const refusalStatus = options.refuseWith ?? 403;
  const files = realConfig();
  const subjects: string[] = [];
  let counter = 0;
  const shas: Record<string, string> = {};
  for (const name of Object.keys(files)) shas[name] = `${name}-0`;

  const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
    if (url.includes('/user')) {
      return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
    }
    // 404 for a login that is genuinely not on the team, which is the one
    // authoritative negative (`auth/role.ts`). Never 403 here: that means the
    // caller may not ask, and it falls through to the configuration instead.
    if (url.includes('/memberships/')) {
      return options.role === 'organizer'
        ? Promise.resolve({ ok: false, status: 404, text: async () => 'not a member' })
        : Promise.resolve({ ok: true, json: async () => ({ state: 'active' }) });
    }
    if (url.endsWith('/actions/secrets?per_page=100')) {
      if (options.refuseSecrets) {
        return Promise.resolve({ ok: false, status: refusalStatus, text: async () => 'no access' });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          secrets: (options.secretNames ?? []).map(name => ({ name })),
        }),
      });
    }
    if (url.endsWith('/actions/variables?per_page=100')) {
      if (options.refuseSecrets) {
        return Promise.resolve({ ok: false, status: refusalStatus, text: async () => 'no access' });
      }
      return Promise.resolve({ ok: true, json: async () => ({ variables: [] }) });
    }
    const listed = CONFIG_DIRS.find(directory => url.endsWith(`/contents/${directory}`));
    if (listed !== undefined) {
      return Promise.resolve({
        ok: true,
        json: async () =>
          Object.keys(files)
            .filter(path => path.startsWith(`${listed}/`))
            .map(path => ({
              name: path.slice(listed.length + 1),
              path,
              type: 'file',
            })),
      });
    }
    const path = decodeURIComponent(url.split('/contents/')[1] ?? '');
    if (path === DRAIN_WORKFLOW) {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          content: encodeUtf8(readFileSync(resolve(ROOT, DRAIN_WORKFLOW), 'utf-8')),
          sha: 'workflow-0',
        }),
      });
    }
    if (files[path] !== undefined) {
      if (opts?.method === 'PUT') {
        const body = JSON.parse(opts.body as string);
        if (body.sha !== shas[path]) {
          return Promise.resolve({ ok: false, status: 409, text: async () => 'stale sha' });
        }
        files[path] = decodeUtf8(body.content);
        shas[path] = `${path}-${++counter}`;
        subjects.push(body.message);
        return Promise.resolve({ ok: true, json: async () => ({ content: { sha: shas[path] } }) });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ content: encodeUtf8(files[path]), sha: shas[path] }),
      });
    }
    return Promise.resolve({ ok: false, status: 404, text: async () => 'no' });
  });

  return { fetchMock, files, subjects };
}

function renderSettings(backend: Backend) {
  vi.stubGlobal('fetch', backend.fetchMock);
  render(
    <MemoryRouter>
      <AuthProvider>
        <DataProvider>
          <Settings />
        </DataProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

/** How long a `findBy*` here may wait for the screen's first render.
 *
 *  Longer than the default second, and for a reason rather than to make a
 *  flake go away: this screen reads the whole drain workflow -- fifty-four
 *  kilobytes -- and parses it, plus six declarations, before it can put a
 *  bound on anything. On a loaded machine that has been observed to take
 *  past a second, and a test that fails only when the machine is busy is
 *  the least useful kind of failure. */
const FIRST_RENDER = { timeout: 5000 };

/** The alarm field, once the screen has finished reading the repository. */
function alarmField() {
  // The accessible name leads with the words printed beside the field and
  // keeps the key and the path behind them: two files carry a
  // `max_silent_days`, so the name still has to disambiguate, but it may no
  // longer omit "Queue alarm" -- which is what a sighted volunteer reads and
  // what a screen-reader user was not being told.
  return screen.findByLabelText(
    'Queue alarm — alarm_after_hours in instance/queue-drain.yml',
    undefined,
    FIRST_RENDER,
  );
}

beforeEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  localStorage.setItem('convener.token', 'tok');
});

describe('the settings screen', () => {
  it('lists what this instance owns, derived rather than typed', async () => {
    renderSettings(makeBackend());
    // From `declarations/boundary.yml`'s own list...
    expect(await screen.findByText('docs/handbook/governance/register.md', undefined, FIRST_RENDER)).toBeInTheDocument();
    expect(screen.getByText('instance/keys/')).toBeInTheDocument();
    // ...and from each configuration file's own `owner:` header.
    expect(screen.getByText('instance/queue-drain.yml')).toBeInTheDocument();
    // Never the product's own files, which answer the same way and say the
    // other thing. The prose above the list names `declarations/boundary.yml` as
    // the declaration it read, so the list itself is what is asked -- read as
    // the list element rather than the whole section, which carries that
    // prose.
    const owned = screen
      .getByRole('heading', { name: 'What this instance owns' })
      .parentElement!.querySelector('ul')!;
    expect(owned.textContent).not.toContain('declarations/integrations.yml');
    expect(owned.textContent).not.toContain('declarations/boundary.yml');
  });

  it('counts what it offers rather than writing the numbers into the sentence', async () => {
    // Every count this page prints about itself is derived from what it
    // draws. *Thresholds* used to open with three examples after a colon
    // and nine fields under it, which reads as a list of everything there
    // is; and the section above it said three paths were settled below,
    // which is a number that moves the day a fourth file joins the form.
    renderSettings(makeBackend());
    const thresholds = await screen.findByText(
      /numbers the scheduled jobs read/,
      undefined,
      FIRST_RENDER,
    );
    expect(thresholds.textContent).toContain(`The ${SETTINGS.length} numbers`);
    expect(thresholds.textContent).toContain(`across ${editableFiles().length} files`);
    expect(screen.getByText(/Nothing here asks you to do anything/).textContent).toContain(
      `${editableFiles().length} are the fields below`,
    );
  });

  it('says why a path it owns is nevertheless not a form', async () => {
    renderSettings(makeBackend());
    expect(await screen.findByText(/never by hand/, undefined, FIRST_RENDER)).toBeInTheDocument();
    expect(screen.getByText(/Read by the build itself/)).toBeInTheDocument();
    expect(screen.getByText(/never renumbers editions/)).toBeInTheDocument();
  });

  it('states the room the coupling leaves before anybody needs it', async () => {
    renderSettings(makeBackend());
    const note = await screen.findByText(/The drain runs every/, undefined, FIRST_RENDER);
    expect(note.textContent).toContain('0 5 * * *');
    expect(note.textContent).toContain('is the only value this pair admits');
  });

  it('refuses an hour below the floor, naming the bound and where it comes from', async () => {
    renderSettings(makeBackend());
    fireEvent.change(await alarmField(), { target: { value: '47' } });

    const refusal = await screen.findByRole('alert');
    expect(refusal.textContent).toContain('floor');
    expect(refusal.textContent).toContain('48 hours is the earliest');
    expect(refusal.textContent).toContain('.github/workflows/sweep-and-notify.yml');
    expect(refusal.textContent).toContain('0 5 * * *');
  });

  it('refuses an hour above the ceiling, naming the other declaration', async () => {
    renderSettings(makeBackend());
    fireEvent.change(await alarmField(), { target: { value: '49' } });

    const refusal = await screen.findByRole('alert');
    expect(refusal.textContent).toContain('ceiling');
    expect(refusal.textContent).toContain('instance/registration-lanes.yml');
    expect(refusal.textContent).toContain('queue_beyond_hours (96)');
  });

  it('writes nothing at all while a value is out of bounds', async () => {
    const backend = makeBackend();
    renderSettings(backend);
    fireEvent.change(await alarmField(), { target: { value: '49' } });

    const save = screen.getByRole('button', { name: /Save/ });
    expect(save).toBeDisabled();
    fireEvent.click(save);
    await waitFor(() => expect(screen.getByText(/out of bounds/)).toBeInTheDocument());
    expect(backend.subjects).toEqual([]);
    expect(backend.files['instance/queue-drain.yml']).toContain('alarm_after_hours: 48');
  });

  it('refuses the other end of the coupling from the other file', async () => {
    renderSettings(makeBackend());
    const lane = await screen.findByLabelText(
      'Immediate-lane threshold — queue_beyond_hours in instance/registration-lanes.yml',
      undefined,
      FIRST_RENDER,
    );
    fireEvent.change(lane, { target: { value: '95' } });

    const refusal = await screen.findByRole('alert');
    expect(refusal.textContent).toContain('coupling');
    expect(refusal.textContent).toContain('instance/queue-drain.yml');
    expect(refusal.textContent).toContain('alarm_after_hours: 48');
  });

  it('writes a legal value to the file that holds it, keeping the argument for it', async () => {
    const backend = makeBackend();
    renderSettings(backend);
    // Raising the lane threshold is what buys the alarm any room at all --
    // the manoeuvre nothing tells anybody about today.
    fireEvent.change(
      await screen.findByLabelText(
        'Immediate-lane threshold — queue_beyond_hours in instance/registration-lanes.yml',
        undefined,
        FIRST_RENDER,
      ),
      { target: { value: '168' } },
    );
    fireEvent.click(screen.getByRole('button', { name: /Save 1 change/ }));

    await waitFor(() =>
      expect(backend.files['instance/registration-lanes.yml']).toContain(
        'queue_beyond_hours: 168',
      ),
    );
    // The file still argues its own case -- every comment line it had,
    // whatever this instance's copy happens to say. One of its sentences
    // was quoted here once, and `config/registration-
    // lanes.yml` is the *instance's* file: quoting its prose made a
    // product test an assertion about which repository was running it.
    const lanes = readFileSync(resolve(ROOT, 'instance/registration-lanes.yml'), 'utf8');
    const comments = lanes.split('\n').filter(line => line.trimStart().startsWith('#'));
    expect(comments.length).toBeGreaterThan(2);
    comments.forEach(line =>
      expect(backend.files['instance/registration-lanes.yml']).toContain(line),
    );
    expect(backend.files['instance/registration-lanes.yml']).toContain('owner: instance');
    // And the subject names the key and the file, never the value.
    expect(backend.subjects).toEqual([
      'config: set queue_beyond_hours in instance/registration-lanes.yml',
    ]);
    expect(backend.subjects[0]).not.toContain('168');
  });

  it('recomputes the alarm’s bounds from the value just written', async () => {
    const backend = makeBackend();
    renderSettings(backend);
    fireEvent.change(
      await screen.findByLabelText(
        'Immediate-lane threshold — queue_beyond_hours in instance/registration-lanes.yml',
        undefined,
        FIRST_RENDER,
      ),
      { target: { value: '168' } },
    );
    fireEvent.click(screen.getByRole('button', { name: /Save 1 change/ }));
    await waitFor(() => expect(backend.subjects.length).toBe(1));

    // 96 was refused a moment ago and is legal now, and the note says so.
    fireEvent.change(await alarmField(), { target: { value: '96' } });
    await waitFor(() =>
      expect(screen.getByText(/The drain runs every/).textContent).toContain('no later than'),
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('tells the reader when a saved value starts being read, per value', async () => {
    renderSettings(makeBackend());
    await alarmField();
    // The lane threshold is the one that does *not* take effect at the next
    // sweep: it reaches the relay only through a file Deploy app rebuilds.
    expect(
      screen.getByText(/public-data\/registration-routing\.json/),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Sweep and notify the board/).length).toBeGreaterThan(0);
  });
});

describe('the integrations it reports and never accepts', () => {
  it('has no field for a secret anywhere on the page', async () => {
    renderSettings(makeBackend());
    await alarmField();
    for (const field of screen.getAllByRole('spinbutton')) {
      expect(field.getAttribute('type')).toBe('number');
    }
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(document.querySelectorAll('input[type="password"]').length).toBe(0);
  });

  it('says which are set and which are not, from names alone', async () => {
    renderSettings(
      makeBackend({
        secretNames: ['CONVENER_SIGNING_KEY', 'CONVENER_EVENT_KEY_MRG_05', 'CONVENER_EVENT_KEY_MRG_06'],
      }),
    );
    expect(await screen.findByText('Certificate signing key', undefined, FIRST_RENDER)).toBeInTheDocument();
    // A declared name carrying a placeholder is a family, and the count is
    // the answer: `CONVENER_EVENT_KEY_<ID>` is one secret per edition.
    expect(screen.getByText(/2 set under CONVENER_EVENT_KEY_/)).toBeInTheDocument();
    expect(screen.getAllByText(/To turn it on, set/).length).toBeGreaterThan(0);
  });

  it('says what each one is for, and not only what breaks without it', async () => {
    // The screen printed a fallback and never a purpose, so somebody
    // reading it met five SMTP names with nothing on the page saying what
    // setting them would buy. Both halves are drawn now, from the
    // declaration's own two fields.
    renderSettings(makeBackend({ refuseSecrets: true }));
    expect(await screen.findByText('Outbound email', undefined, FIRST_RENDER)).toBeInTheDocument();
    expect(screen.getAllByText(/What it does/).length).toBeGreaterThan(5);
  });

  it('answers, where it is asked, that no button here sends a journey email', async () => {
    // The question this row exists to close: a maintainer went looking
    // through the workspace for the send button five declared SMTP secrets
    // implied, and there is none by decision (D-07). The row says so at the
    // place the search started.
    renderSettings(makeBackend({ refuseSecrets: true }));
    expect(await screen.findByText('Outbound email', undefined, FIRST_RENDER)).toBeInTheDocument();
    expect(screen.getByText(/no send button/)).toBeInTheDocument();
  });

  it('counts the rows whose absence is a fault, rather than saying three', async () => {
    // Three rows declare `absent_is_normal: false` today. The sentence
    // introducing the list says how many, and it reads the answer off the
    // rows it is about to draw -- a fourth added to the declaration would
    // otherwise leave the page saying three with four marked below it.
    const declared = integrationsFromData(
      yaml.load(readFileSync(resolve(ROOT, 'declarations/integrations.yml'), 'utf-8')),
    );
    const exceptional = declared.filter(one => !one.absentIsNormal).length;
    expect(exceptional).toBeGreaterThan(0);
    renderSettings(makeBackend());
    const lead = await screen.findByText(
      /What this instance can reach outside itself/,
      undefined,
      FIRST_RENDER,
    );
    expect(lead.textContent).toContain(`but on the ${exceptional} rows`);
  });

  it('says what breaks without each, whatever the answer was', async () => {
    renderSettings(makeBackend({ refuseSecrets: true }));
    expect(await screen.findByText('Outbound email', undefined, FIRST_RENDER)).toBeInTheDocument();
    expect(screen.getAllByText(/Without it/).length).toBeGreaterThan(5);
  });

  it('reads a refusal of rights as a boundary, and says there is nothing to do', async () => {
    renderSettings(makeBackend({ refuseSecrets: true }));
    expect(
      await screen.findByText(/deliberately not allowed to list them/, undefined, FIRST_RENDER),
    ).toBeInTheDocument();
    // The sentence a volunteer leaves on: not where they may not go.
    expect(screen.getByText(/nothing here for you to do/)).toBeInTheDocument();
    expect(screen.queryByText(/Not set:/)).not.toBeInTheDocument();
  });

  it('reads any other failure as a call that failed, and says to try again', async () => {
    // The distinction this screen would otherwise get wrong in the more
    // costly direction: an outage rendered as a boundary tells an operator
    // to stop trying, about something that would have worked in a minute.
    renderSettings(makeBackend({ refuseSecrets: true, refuseWith: 500 }));
    expect(
      await screen.findByText(/GitHub did not answer/, undefined, FIRST_RENDER),
    ).toBeInTheDocument();
    expect(screen.getByText(/worth trying again/)).toBeInTheDocument();
    expect(screen.queryByText(/deliberately not allowed/)).not.toBeInTheDocument();
  });
});

describe('the same screen, demonstrated', () => {
  /** A `fetch` that fails the test rather than the request. Demo mode must
   *  not reach the wire at all here: `net/request.ts` would refuse a
   *  cross-origin call anyway, but a screen that *tried* would show a
   *  visitor an error where a demonstration belongs. */
  function forbidden() {
    return vi.fn(() => {
      throw new Error('the demonstration reached the network');
    });
  }

  beforeEach(() => {
    localStorage.setItem('convener.demo', '1');
  });

  it('reads the example instance out of the bundle, touching nothing', async () => {
    vi.stubGlobal('fetch', forbidden());
    render(
      <MemoryRouter>
        <AuthProvider>
          <DataProvider>
            <Settings />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );
    // The example instance's own declarations, through the same reader the
    // signed-in path uses -- the four instance files `examples/the-example-collective/`
    // holds, plus the product's two.
    const example = yaml.load(
      readFileSync(resolve(ROOT, 'examples/the-example-collective/instance/queue-drain.yml'), 'utf-8'),
    ) as Record<string, number>;
    expect(await alarmField()).toHaveValue(example.alarm_after_hours);
    expect(screen.getByText(/The drain runs every/)).toBeInTheDocument();
  });

  it('refuses an illegal value there too, and writes nothing anywhere', async () => {
    vi.stubGlobal('fetch', forbidden());
    render(
      <MemoryRouter>
        <AuthProvider>
          <DataProvider>
            <Settings />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );
    fireEvent.change(await alarmField(), { target: { value: '47' } });
    expect((await screen.findByRole('alert')).textContent).toContain('is the earliest');

    fireEvent.change(await alarmField(), { target: { value: '48' } });
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });

  it('applies a legal edit in the tab and never on the wire', async () => {
    const wire = forbidden();
    vi.stubGlobal('fetch', wire);
    render(
      <MemoryRouter>
        <AuthProvider>
          <DataProvider>
            <Settings />
          </DataProvider>
        </AuthProvider>
      </MemoryRouter>,
    );
    fireEvent.change(
      await screen.findByLabelText(
        'Immediate-lane threshold — queue_beyond_hours in instance/registration-lanes.yml',
        undefined,
        FIRST_RENDER,
      ),
      { target: { value: '168' } },
    );
    fireEvent.click(screen.getByRole('button', { name: /Save 1 change/ }));
    await waitFor(() => expect(screen.getByText(/^Written: /)).toBeInTheDocument());
    expect(wire).not.toHaveBeenCalled();
  });

});

// ---------------------------------------------------------------- //
// Who may change what an instance runs on.
// ---------------------------------------------------------------- //

describe('an organizer', () => {
  it('reads every threshold and can change none of them', async () => {
    // The gap this closes. Every other write surface in this application
    // asks the role -- `ActionButtons`, `PublicationGate`, `SpeakerPage` --
    // and this one, which settles the Actions allowance and the routing
    // every registration passes through, never did. Measured on a live
    // instance: two of the five repository admins are exactly the
    // `organizer` the product models.
    const backend = makeBackend({ role: 'organizer' });
    renderSettings(backend);

    const alarm = await alarmField();
    expect(alarm).toHaveAttribute('readonly');
    // Readable, selectable, reachable: seeing what the instance is set to
    // is the part an organizer keeps.
    expect(alarm).not.toBeDisabled();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^Save/ })).toBeDisabled(),
    );
    expect(screen.getByText(/These are the Board/)).toBeInTheDocument();
  });

  it('is told it is a division of responsibility and not a lock', async () => {
    // A role check in a browser is not a security boundary, and saying so
    // is not a caveat -- an organizer holds write access to the repository
    // and can edit these three files on GitHub whichever way this screen
    // renders. What the sentence has to carry is why the division is stated
    // here at all: on the private repository D-15 requires, on the free
    // plan, GitHub refuses branch protection and rulesets outright, so
    // CODEOWNERS is advisory and there is nowhere else to say it.
    const backend = makeBackend({ role: 'organizer' });
    renderSettings(backend);

    // The paragraph, not the `<strong>` the matcher lands on: the whole
    // point is the sentences after the first one.
    const notice = (await screen.findByText(/These are the Board/)).closest('p');
    const said = notice?.textContent ?? '';
    expect(said).toMatch(/not a lock/);
    expect(said).toMatch(/CODEOWNERS/);
    expect(said).toMatch(/advisory/);
  });

  it('writes nothing even if the save control is reached anyway', async () => {
    // The gate is on the control, and a disabled control is a rendering.
    // This asserts the outcome rather than the attribute: no subject was
    // ever sent.
    const backend = makeBackend({ role: 'organizer' });
    renderSettings(backend);

    // The lane threshold, not the alarm: 60 hours is out of bounds against
    // the real declarations, so a reading built on it was held disabled by
    // the bound and passed with no gate at all -- which the mutation caught.
    // 168 is the legal edit the saving test above makes, and it is exactly
    // the edit that must not go through from here.
    fireEvent.change(
      await screen.findByLabelText(
        'Immediate-lane threshold — queue_beyond_hours in instance/registration-lanes.yml',
        undefined,
        FIRST_RENDER,
      ),
      { target: { value: '168' } },
    );
    const save = screen.getByRole('button', { name: /^Save/ });
    fireEvent.click(save);

    await waitFor(() => expect(save).toBeDisabled());
    expect(backend.subjects).toEqual([]);
    expect(backend.files['instance/registration-lanes.yml']).not.toContain(
      'queue_beyond_hours: 168',
    );
  });
});

describe('a Board member', () => {
  it('still gets the fields and the control', async () => {
    // Non-vacuity for the three above: a gate that refused everybody would
    // pass all of them and take the screen with it.
    const backend = makeBackend();
    renderSettings(backend);

    const alarm = await alarmField();
    expect(alarm).not.toHaveAttribute('readonly');
    expect(screen.queryByText(/These are the Board/)).not.toBeInTheDocument();

    // The lane threshold rather than the alarm, and for the same reason the
    // saving test above uses it: raising it is the one edit that is legal
    // against the coupling as the real declarations leave it. This reading
    // is about the gate, so the field it moves must not also be arguing
    // about a bound.
    fireEvent.change(
      await screen.findByLabelText(
        'Immediate-lane threshold — queue_beyond_hours in instance/registration-lanes.yml',
        undefined,
        FIRST_RENDER,
      ),
      { target: { value: '168' } },
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Save 1 change/ })).not.toBeDisabled(),
    );
  });
});