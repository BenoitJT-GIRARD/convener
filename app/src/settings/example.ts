/**
 * The example instance's own declarations, as they reach this bundle.
 *
 * One define, one reader. `vite.config.ts` substitutes the whole of
 * `scripts/example-settings.mjs`'s result under
 * `import.meta.env.VITE_EXAMPLE_SETTINGS` -- the four `config/` files
 * `instances/example/` owns plus the product's two -- and more than one
 * place in the cockpit needs something out of it: `./load.ts` parses all
 * six for the settings screen, and `state/agenda.ts` needs the one value
 * the example numbers its editions under. They read it through here, so
 * the define has a single reader on this side exactly as
 * `instance/config.json` has one per language on the other.
 *
 * Throws rather than defaulting, the rule `../instance.ts` and
 * `scripts/example-settings.mjs` both follow: a bundle built without the
 * define cannot demonstrate anything at all, and the alternative to
 * stopping is a settings screen whose every bound reads `undefined` and a
 * cockpit offering `undefined-4` as the next edition of the series on
 * screen.
 */

/** The example instance's settings, exactly as `vite.config.ts`'s own
 *  `define` put them into this bundle (`scripts/example-settings.mjs` is
 *  what read them). */
export interface ExampleSettings {
  files: Record<string, string>;
  drainTriggers: unknown;
}

/** Where the example instance says who it is, keyed by the path it holds
 *  in the tree the settings screen describes -- the same path
 *  `instance/config.json` is for the instance that built this bundle.
 *  `scripts/example-settings.mjs` reads it out of
 *  `instances/example/instance/`. */
const DECLARATION = 'instance/config.json';

/** The six declarations, as text. */
export function exampleSettings(): ExampleSettings {
  const raw = import.meta.env.VITE_EXAMPLE_SETTINGS as string | undefined;
  if (!raw) {
    throw new Error(
      'VITE_EXAMPLE_SETTINGS is unset: this bundle was built without ' +
        "vite.config.ts's own define, so the demonstration has no settings to " +
        'show (see instances/example/instance/)',
    );
  }
  return JSON.parse(raw) as ExampleSettings;
}

/** The example's own declaration, parsed. Not cached: the two values
 *  below cache what they take from it, and nothing else reads it. */
function declaration(): Record<string, unknown> {
  const text = exampleSettings().files[DECLARATION];
  if (!text) {
    throw new Error(
      `VITE_EXAMPLE_SETTINGS carries no ${DECLARATION}: this bundle was built ` +
        "without the example instance's own declaration, so the demonstration " +
        'cannot say anything about the instance whose records it shows (see ' +
        'instances/example/instance/config.json)',
    );
  }
  return JSON.parse(text) as Record<string, unknown>;
}

function declaredString(key: string): string {
  const value = declaration()[key];
  if (typeof value !== 'string' || value === '') {
    throw new Error(
      `instances/example/instance/config.json declares no ${key}, so the ` +
        "demonstration has nothing to compose the example instance's own " +
        'values from',
    );
  }
  return value;
}

let cachedEditionPrefix: string | null = null;

/**
 * The prefix the example instance numbers *its* editions under -- `MRG`,
 * so `MRG-4`.
 *
 * Read back out of the declaration this bundle already carries rather
 * than given a define of its own: the same file substituted in twice
 * would be the second home for one value that this project spends its
 * time deleting, and it would be paid for in bytes served to every
 * visitor.
 */
export function exampleEditionPrefix(): string {
  cachedEditionPrefix ??= declaredString('edition_prefix');
  return cachedEditionPrefix;
}

let cachedPublishedUrl: string | null = null;

/**
 * The address the example instance publishes at, trailing slash included
 * -- `https://example-instance.github.io/example-showcase/`.
 *
 * Read the same way and for the same reason as the prefix above. Nothing
 * is served there and nothing is asked to be: the demonstration composes
 * this into the registration link of a record that belongs to that
 * instance, where the alternative is this instance's own address carrying
 * somebody else's edition code (`content/render.ts::signupBase`).
 */
export function examplePublishedUrl(): string {
  cachedPublishedUrl ??= declaredString('published_url');
  return cachedPublishedUrl;
}
