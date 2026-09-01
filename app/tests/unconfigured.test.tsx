/**
 * A duplicate that has not been configured says so, on its own pages.
 *
 * The rule, in as many words: a duplicate that has not been configured
 * says so, loudly, rather than publishing silently under somebody else's
 * identity. That is the direct continuation of a rule this project
 * already settled: a default that leaks when you forget it is not a
 * default, it is a trap.
 *
 * What "not configured" means, mechanically, is decided on the other side
 * of the language boundary and stated once in
 * `tools/convener_ops/declaration/published.py::unconfigured`: a declared value still
 * equal to the one the product ships in `examples/the-example-collective/instance/
 * instance.json`. `app/scripts/published.mjs::unconfigured` is this
 * build's reader of it and `vite.config.ts` carries the answer into the
 * bundle; what is tested here is the browser end of that -- the reader of
 * the define, and the two screens that print it.
 *
 * Both directions, deliberately. A banner that shows when it should not
 * is deleted within a week and takes the real warning with it, so "it
 * renders nothing on a configured instance" is not a smaller claim than
 * "it renders on an unconfigured one" -- it is the one that decides
 * whether the other survives.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AuthProvider } from '../src/auth/AuthContext';
import { Login } from '../src/auth/Login';

/** Every value `instance/config.json` declares about who is publishing,
 *  as `published.py::declared_values` names them. Written out here rather
 *  than derived, because this side of the boundary has no reader of the
 *  file: `tools/tests/declaration/test_published.py::test_the_declaration_names_every_
 *  value_that_says_who_is_publishing` is what holds the enumeration to the
 *  declaration's own lists, and
 *  `test_every_bundle_the_application_builds_carries_the_unconfigured_
 *  verdict` is what holds this bundle's define to what that reader says. */
const EVERY_KEY = [
  'edition_prefix',
  'identity.contact',
  'identity.forum',
  'identity.organisation',
  'identity.proposal_form',
  'identity.repository',
  'identity.series',
  'identity.short_name',
  'identity.strapline',
  'identity.tagline',
  'published_url',
];

/** Load the banner with a given verdict in the bundle. `src/instance.ts`
 *  parses the define once and caches it, exactly as a real bundle does,
 *  so the module registry has to be reset rather than the cache poked at
 *  -- the same arrangement `instance-identity.test.ts` already uses. */
async function bannerWith(fields: string[] | null) {
  vi.resetModules();
  vi.stubEnv('VITE_INSTANCE_UNCONFIGURED', fields === null ? '' : JSON.stringify(fields));
  return import('../src/components/UnconfiguredBanner');
}

beforeEach(() => {
  vi.unstubAllEnvs();
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('the verdict reaches the browser or the build is broken', () => {
  it('throws when the bundle carries no verdict at all', async () => {
    vi.resetModules();
    vi.stubEnv('VITE_INSTANCE_UNCONFIGURED', '');
    const { unconfiguredFields } = await import('../src/instance');
    expect(() => unconfiguredFields()).toThrow(/VITE_INSTANCE_UNCONFIGURED/);
  });

  it('reads an empty verdict as configured rather than as absent', async () => {
    vi.resetModules();
    vi.stubEnv('VITE_INSTANCE_UNCONFIGURED', '[]');
    const { unconfiguredFields } = await import('../src/instance');
    expect(unconfiguredFields()).toEqual([]);
  });

  it('reads the verdict back as the keys the declaration names', async () => {
    vi.resetModules();
    vi.stubEnv('VITE_INSTANCE_UNCONFIGURED', JSON.stringify(EVERY_KEY));
    const { unconfiguredFields } = await import('../src/instance');
    expect(unconfiguredFields()).toEqual(EVERY_KEY);
  });
});

describe('the banner', () => {
  it('renders nothing at all on a configured instance', async () => {
    const { UnconfiguredBanner } = await bannerWith([]);
    const { container } = render(<UnconfiguredBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it('names every value still left as the example’s', async () => {
    const { UnconfiguredBanner } = await bannerWith(EVERY_KEY);
    render(<UnconfiguredBanner />);
    expect(screen.getByText('Not configured')).toBeInTheDocument();
    for (const key of EVERY_KEY) {
      expect(screen.getByText(new RegExp(key.replace('.', '\\.')))).toBeInTheDocument();
    }
  });

  it('shows on a half-configured duplicate, naming only what is left', async () => {
    const left = ['identity.contact', 'published_url'];
    const { UnconfiguredBanner } = await bannerWith(left);
    render(<UnconfiguredBanner />);
    expect(screen.getByText('Not configured')).toBeInTheDocument();
    expect(screen.getByText(/identity\.contact, published_url/)).toBeInTheDocument();
    expect(screen.queryByText(/identity\.organisation/)).not.toBeInTheDocument();
  });
});

describe('the screen a visitor with no account actually reaches', () => {
  it('carries the warning above the sign-in it offers', async () => {
    vi.resetModules();
    vi.stubEnv('VITE_INSTANCE_UNCONFIGURED', JSON.stringify(EVERY_KEY));
    // Both halves out of the *same* registry: `vi.resetModules()` gives
    // `Login` a fresh `AuthContext`, and a provider imported before the
    // reset would be a different module holding a different React
    // context -- which reads, from inside the screen, as no provider at
    // all.
    const { Login: Screen } = await import('../src/auth/Login');
    const { AuthProvider: Provider } = await import('../src/auth/AuthContext');
    render(
      <Provider>
        <Screen />
      </Provider>,
    );
    expect(screen.getByText('Not configured')).toBeInTheDocument();
  });

  it('says nothing there on a configured instance', () => {
    vi.stubEnv('VITE_INSTANCE_UNCONFIGURED', '[]');
    render(
      <AuthProvider>
        <Login />
      </AuthProvider>,
    );
    expect(screen.queryByText('Not configured')).not.toBeInTheDocument();
  });
});
