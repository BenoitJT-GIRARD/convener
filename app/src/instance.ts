/**
 * Who runs this series, on the application's side of the language boundary.
 *
 * One declaration -- `config/instance.json` -- and one reader per language:
 * `tools/convener_ops/published.py::load_identity` for Python,
 * `site/scripts/published.cjs::identity` for the showcase's build,
 * `app/scripts/published.mjs::identity` for this one. This module is not a
 * fourth reader: it is how the value that build already read reaches the
 * browser, where no file can be read at all. `vite.config.ts` substitutes
 * the whole object into every bundle through Vite's own `define`, exactly
 * as it already does for the published address.
 *
 * Phase 10, task 3. Before it, the organisation's name, the series' title,
 * the forum and the contact address were typed out in the cockpit's chrome,
 * in three islands, in the content registry's repository URL and in the
 * role check's organisation -- a hundred and fifty-six times in all,
 * across sixty-six files, counted over `docs/` (its own specs and plans
 * aside), `site/src/`, `app/src/`, `tools/convener_ops/` and the two
 * publishing workflows.
 * None of them is the product's: a duplicate of this repository runs a
 * different series for a different organisation, and every one of those
 * strings would have had to be found and edited by hand.
 *
 * Throws rather than defaulting, the same rule `render.ts::signupBase` and
 * `published.mjs` both follow. A bundle built without the define is a
 * broken build, not an ordinary state (D-13 is about an integration that
 * may genuinely not be configured yet; this is not that), and the
 * alternative to throwing is the word "undefined" in the sign-off of an
 * e-mail to a speaker or in the masthead of a public page.
 */

/** The vocabulary, and the whole of it. Mirrors
 *  `published.py::IDENTITY_FIELDS` plus the one derived name both sides
 *  compose (`forum_host`); `snake_case` because these keys are the JSON
 *  declaration's own, and renaming them on the way in would be a second
 *  spelling of each. */
export interface InstanceIdentity {
  /** The organisation's full name -- what a stranger is told. */
  organisation: string;
  /** Its abbreviation -- what a correspondent who already knows is told,
   *  and the form that reads naturally in a subject line. */
  short_name: string;
  /** What the series is called. */
  series: string;
  /** The display line the poster sets in heavy capitals above the talk's
   *  own title -- two or three words, never a sentence. `tagline` is the
   *  sentence; see `published.py::Identity` for why both exist. */
  strapline: string;
  tagline: string;
  /** The forum's whole address, for an `href`. */
  forum: string;
  /** The forum's bare host, for a sentence that names it. */
  forum_host: string;
  /** Where a participant writes about their own data. */
  contact: string;
  /** The public proposal form. */
  proposal_form: string;
  /** `owner/name` -- this repository, the one the cockpit writes to. */
  repository: string;
}

let cached: InstanceIdentity | null = null;

/** This instance's identity, parsed once. */
export function instanceIdentity(): InstanceIdentity {
  if (cached) return cached;
  const raw = import.meta.env.VITE_INSTANCE_IDENTITY as string | undefined;
  if (!raw) {
    throw new Error(
      'VITE_INSTANCE_IDENTITY is unset: this bundle was built without ' +
        "vite.config.ts's own define, so it cannot say who runs this series " +
        '(see config/instance.json)',
    );
  }
  cached = JSON.parse(raw) as InstanceIdentity;
  return cached;
}

/** `https://github.com/<owner>/<name>` -- this repository on the web. Both
 *  the "edit this page" link and the attribution line under an included
 *  handbook passage are built from it. */
export function repositoryUrl(): string {
  return `https://github.com/${instanceIdentity().repository}`;
}

let cachedEditionPrefix: string | null = null;

/**
 * The prefix this instance numbers its editions under -- `MRG`, so `MRG-05`
 * and, lower-cased, the event id `/events/mrg-05/` (D-19).
 *
 * Phase 11, task 4. `state/agenda.ts::nextEditionCode` used to compose
 * `MRG-${n}` from a literal, and `validate.py::EDITION_RE` fixed the same
 * two letters on the other side of the language boundary -- the initials
 * of the series that happens to run this repository, in the product's own
 * code, so a duplicate's reading group numbered its sessions `MRG-1`.
 *
 * A separate define from the identity rather than a tenth field of it:
 * everything in `InstanceIdentity` is prose somebody outside this project
 * reads, checked the one way prose can be checked, while this is a token
 * with a grammar (`scripts/published.mjs::editionPrefix`, mirroring
 * `published.py::EDITION_PREFIX_RE`) that is refused at declaration.
 *
 * Throws rather than defaulting, for the reason `instanceIdentity` above
 * does: the alternative to throwing is a cockpit quietly suggesting
 * `undefined-6` as the next edition of a series, and an edition code is
 * the one value in this repository that can never be corrected after the
 * fact -- it is in a published address, on an issued certificate and in a
 * key filename.
 *
 * The `MRG-` form an edition code actually starts with is deliberately
 * *not* here, and that absence is the correction phase 11's own bilan
 * asked for: composing it needs the prefix of the instance whose records
 * are on screen, which in demo mode is the example's and not this one's
 * (`state/agenda.ts::editionCodePrefix`). A second function here
 * returning this instance's prefix with a hyphen on it would be a trap
 * the next call site walks into.
 */
export function editionPrefix(): string {
  if (cachedEditionPrefix) return cachedEditionPrefix;
  const raw = import.meta.env.VITE_INSTANCE_EDITION_PREFIX as string | undefined;
  if (!raw) {
    throw new Error(
      'VITE_INSTANCE_EDITION_PREFIX is unset: this bundle was built without ' +
        "vite.config.ts's own define, so it cannot say what this series " +
        'numbers its editions (see config/instance.json)',
    );
  }
  cachedEditionPrefix = raw;
  return cachedEditionPrefix;
}

/** The organisation half of `repository` -- the GitHub organisation whose
 *  team membership decides who signs in as a Board member
 *  (`auth/role.ts`). One fact, not two: the repository the cockpit writes
 *  to and the organisation it belongs to cannot be different organisations. */
export function organisationLogin(): string {
  return instanceIdentity().repository.split('/')[0];
}

let cachedUnconfigured: string[] | null = null;

/**
 * Which of this instance's declared values are still the ones the product
 * ships in `instances/example/config/instance.json` -- empty for an
 * instance somebody has configured, and the names of the offending keys
 * for one nobody has.
 *
 * Phase 11, task 6. The first thing anybody does with a template is
 * deploy it before configuring it, and until this the result was a public
 * cockpit whose masthead named the example collective, whose footer
 * linked its invented forum and whose every check stayed green -- a
 * declaration that belongs to somebody else is still a perfectly valid
 * declaration. `scripts/published.mjs::unconfigured` is this build's
 * reader of it; `tools/convener_ops/published.py::unconfigured` states the
 * whole rule and why the `REPLACE` marker is deliberately no part of it.
 *
 * Throws when the define is absent, for the reason `instanceIdentity`
 * above does and then one more: the ordinary answer here is the empty
 * list, so a bundle built without the define would look exactly like a
 * configured instance and this warning would fall silent precisely when
 * the build was broken. `vite.config.ts` therefore carries the value as
 * JSON -- `'[]'` is a value, an absent define is not (D-25).
 */
export function unconfiguredFields(): string[] {
  if (cachedUnconfigured) return cachedUnconfigured;
  const raw = import.meta.env.VITE_INSTANCE_UNCONFIGURED as string | undefined;
  if (!raw) {
    throw new Error(
      'VITE_INSTANCE_UNCONFIGURED is unset: this bundle was built without ' +
        "vite.config.ts's own define, so it cannot say whether this instance " +
        'has been configured (see config/instance.json)',
    );
  }
  cachedUnconfigured = JSON.parse(raw) as string[];
  return cachedUnconfigured;
}
