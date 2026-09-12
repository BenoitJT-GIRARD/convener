/**
 * Which integrations are configured -- asked without ever asking for a
 * secret.
 *
 * The constraint this module is built around is not a preference and it is
 * not negotiable. **The cockpit can never hold a secret.** It is a static
 * bundle, served publicly, and it writes with the signed-in person's own
 * token; a token that could write a repository secret would be a right
 * every Board member held, which is exactly the problem a security review
 * named and declined to close at zero cost. So this screen
 * has no field for a secret, no place to paste one, and no code path that
 * could send one anywhere.
 *
 * **That argument rests on something outside this file**, and it is worth
 * saying which: it assumes a Board member does not already hold the right
 * it declines to introduce. Whether they do is decided by how the
 * repository grants them access. `declarations/standing-up.yml` gives the
 * `editorial-board` team Write, which is enough for everything the cockpit
 * does and carries no access to secrets -- and says, at the same step, that
 * Board membership is not a reason to own the organisation, because an
 * owner holds admin on every repository it has. An instance that grants
 * access some other way can make this restraint moot without changing a
 * line of it. The first instance to walk that sequence did, before the step
 * said so.
 *
 * Reporting is a different act, and it is the useful one. GitHub's own
 * Actions endpoints answer *which names exist* and never a value: the
 * secrets endpoint is documented as listing secrets "without revealing
 * their encrypted values", and there is no endpoint at all that would give
 * one back. So the question this module asks is the one
 * `declarations/integrations.yml` was written to answer -- for each integration,
 * is the thing it needs set, and if not, what does the code do instead --
 * and it asks it with names alone.
 *
 * Variables are asked for too, and their values are deliberately dropped.
 * Three of the declared names are repository *variables* rather than
 * secrets (`deploy.yml` reads `vars.VITE_AUTH_PROXY_URL` and
 * `vars.VITE_GITHUB_APP_CLIENT_ID`), and that endpoint does return values.
 * This module takes the names and discards the rest at the point of
 * parsing: a screen that has no use for a value should not be holding one,
 * whether or not it is secret.
 *
 * **An unanswered question is an answer this screen prints.** A token
 * without the right to list either collection gets a 403, and D-13's rule
 * applies to this screen as much as to any integration: the report says it
 * could not ask and shows what each integration is for anyway. It never
 * silently reports "absent" for something it simply did not get to see --
 * that is the failure mode the whole file exists to avoid.
 */
import { gh, GitHubError } from '../github/client';
import type { Integration } from './declaration';

/** Where an operator sets these, named once so the screen and its refusal
 *  sentence agree. */
export const SECRETS_SETTINGS_PATH =
  "GitHub's Settings → Secrets and variables → Actions";

/** Why the listing did not happen, which is not the same question as
 *  whether an integration is set.
 *
 *  `not-permitted` is a boundary: GitHub answered, and the answer was that
 *  this sign-in may not read the repository's Actions settings. Nothing is
 *  wrong and nothing is worth retrying. `unanswered` is everything else --
 *  a rate limit, an outage, a network that never reached a response -- and
 *  it is worth retrying. They print differently because they are different
 *  facts, and because a screen that called an outage a boundary would be
 *  telling an operator to stop trying. */
export type RefusalKind = 'not-permitted' | 'unanswered';

/** The names GitHub answered with, or the sentence saying why it did not.
 *  Never a value of either kind. */
export interface SecretNames {
  secrets: string[];
  variables: string[];
  /** Non-null when the question could not be asked. */
  refusal: string | null;
  /** Which of the two it was, for the one statement the section prints.
   *  `null` exactly when `refusal` is. */
  refusalKind: RefusalKind | null;
}

/** A declared name carrying a `<...>` placeholder is a *family*, not a
 *  name: `CONVENER_EVENT_KEY_<ID>` is one secret per edition, and the count is
 *  the answer rather than a yes or no. */
const FAMILY = /<[^>]*>/;

function familyPrefix(declared: string): string | null {
  const at = declared.search(FAMILY);
  return at === -1 ? null : declared.slice(0, at);
}

function namesOf(payload: unknown, field: string): string[] {
  const rows = (payload as Record<string, unknown> | null)?.[field];
  if (!Array.isArray(rows)) return [];
  return rows
    .map(row => (row as Record<string, unknown> | null)?.name)
    .filter((name): name is string => typeof name === 'string');
}

/**
 * Ask GitHub for the names, both collections at once.
 *
 * Both calls go through `github/client.ts`, so both go through
 * `net/request.ts` -- the one door -- and a demonstration refuses them
 * before they reach the wire.
 */
export async function loadSecretNames(token: string): Promise<SecretNames> {
  try {
    const [secrets, variables] = await Promise.all([
      gh('/actions/secrets?per_page=100', { token, method: 'GET' }),
      gh('/actions/variables?per_page=100', { token, method: 'GET' }),
    ]);
    return {
      secrets: namesOf(secrets, 'secrets'),
      variables: namesOf(variables, 'variables'),
      refusal: null,
      refusalKind: null,
    };
  } catch (error) {
    const said = error instanceof Error ? error.message : String(error);
    // 403 is what a user-to-server token gets for a permission its App does
    // not hold; 404 is what GitHub answers for a resource a token may not
    // know exists, which is the same refusal wearing a quieter hat. Anything
    // else is a call that failed, and saying so is the whole point of
    // telling the two apart.
    const status = error instanceof GitHubError ? error.status : null;
    const kind: RefusalKind =
      status === 403 || status === 404 ? 'not-permitted' : 'unanswered';
    return {
      secrets: [],
      variables: [],
      refusalKind: kind,
      refusal:
        kind === 'not-permitted'
          ? 'This screen is deliberately not allowed to list them. It runs in ' +
            'your browser under the App you signed in with, and that App holds ' +
            'Contents and nothing else — a sign-in able to read this ' +
            "repository's Actions settings would be a right every Board member " +
            'carried. So this is not a failure to retry or wait out: the answer ' +
            "is not this screen's to have. It only ever asks for names, never a " +
            'value — no endpoint would return one. Whoever administers this ' +
            `repository can see the names in ${SECRETS_SETTINGS_PATH}, and ` +
            'convener-check-config reports authoritatively from inside a ' +
            'workflow. If you are not that person, there is nothing here for ' +
            'you to do — and nothing is wrong.'
          : 'GitHub did not answer when this screen asked which secrets and ' +
            `variables this repository holds (${said}). That is a call that ` +
            'failed rather than a boundary, so it is worth trying again. What ' +
            'each integration is for is below regardless.',
    };
  }
}

/** Whether one integration's inputs are all set, and which are not.
 *
 *  `unknown` used to stand for two unrelated facts: that the listing was
 *  refused, and that the integration declares no input to look for. The
 *  first is a property of the *screen* -- when it happens, every row
 *  carries it, so printing it per row implied per-row information that did
 *  not exist -- and the second is a property of the integration, which is
 *  true whatever GitHub answers. `not-looked` and `undeclared` are those
 *  two facts, and the section prints the reason for the first once, above
 *  the rows, where it belongs. */
export type ConfiguredState =
  | 'configured'
  | 'absent'
  | 'partial'
  | 'undeclared'
  | 'not-looked';

export interface IntegrationReport {
  integration: Integration;
  state: ConfiguredState;
  /** The declared names that were not found. Empty when `state` is
   *  `not-looked` or `undeclared`: nothing was found and nothing was
   *  looked for. */
  missing: string[];
  /** For a declared family, how many names are set under its prefix.
   *  `null` when the integration declares no family. */
  family: { prefix: string; count: number } | null;
}

/**
 * One integration, judged against the names GitHub gave.
 *
 * Mirrors `integrations.resolve_states` in what it means by absent -- any
 * declared input unset makes the integration absent -- and deliberately not
 * in how it looks: `resolve_states` reads the *process environment* of
 * whichever machine runs the tooling, which is a different observation from
 * what the repository holds. Which is why this screen says where it looked.
 */
export function reportOn(integration: Integration, names: SecretNames): IntegrationReport {
  if (names.refusal !== null) {
    return { integration, state: 'not-looked', missing: [], family: null };
  }
  const known = new Set([...names.secrets, ...names.variables]);
  const missing: string[] = [];
  let family: { prefix: string; count: number } | null = null;
  for (const declared of integration.secrets) {
    const prefix = familyPrefix(declared);
    if (prefix === null) {
      if (!known.has(declared)) missing.push(declared);
      continue;
    }
    const count = [...known].filter(name => name.startsWith(prefix)).length;
    family = { prefix, count };
    if (count === 0) missing.push(declared);
  }
  if (integration.secrets.length === 0) {
    return { integration, state: 'undeclared', missing: [], family: null };
  }
  const state: ConfiguredState =
    missing.length === 0
      ? 'configured'
      : missing.length === integration.secrets.length
        ? 'absent'
        : 'partial';
  return { integration, state, missing, family };
}

/** Every integration, reported. Sorted so the ones whose absence is *not* a
 *  normal state come first: three rows declare `absent_is_normal: false`,
 *  and one of them means a registration nobody can ever decrypt. */
export function reportAll(
  integrations: Integration[],
  names: SecretNames,
): IntegrationReport[] {
  return integrations
    .map(integration => reportOn(integration, names))
    .sort((left, right) => {
      const weight = (report: IntegrationReport) =>
        (report.integration.absentIsNormal ? 1 : 0) +
        (report.state === 'configured' ? 2 : 0);
      return weight(left) - weight(right);
    });
}
