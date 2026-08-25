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
 * role check's organisation -- and eighty-five more times across `docs/`.
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
  /** "The Example Collective" -- the name a stranger is told. */
  organisation: string;
  /** "TEC" -- the name a correspondent who already knows is told. */
  short_name: string;
  /** "Monthly Reading Group". */
  series: string;
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

/** The organisation half of `repository` -- the GitHub organisation whose
 *  team membership decides who signs in as a Board member
 *  (`auth/role.ts`). One fact, not two: the repository the cockpit writes
 *  to and the organisation it belongs to cannot be different organisations. */
export function organisationLogin(): string {
  return instanceIdentity().repository.split('/')[0];
}
