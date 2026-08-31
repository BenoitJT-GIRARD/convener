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
 * Reporting is a different act, and it is the useful one. GitHub's own
 * Actions endpoints answer *which names exist* and never a value: the
 * secrets endpoint is documented as listing secrets "without revealing
 * their encrypted values", and there is no endpoint at all that would give
 * one back. So the question this module asks is the one
 * `config/integrations.yml` was written to answer -- for each integration,
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
import { gh } from '../github/client';
import type { Integration } from './declaration';

/** Where an operator sets these, named once so the screen and its refusal
 *  sentence agree. */
export const SECRETS_SETTINGS_PATH =
  "GitHub's Settings → Secrets and variables → Actions";

/** The names GitHub answered with, or the sentence saying why it did not.
 *  Never a value of either kind. */
export interface SecretNames {
  secrets: string[];
  variables: string[];
  /** Non-null when the question could not be asked. */
  refusal: string | null;
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
    };
  } catch (error) {
    const said = error instanceof Error ? error.message : String(error);
    return {
      secrets: [],
      variables: [],
      refusal:
        'GitHub did not say which secrets and variables this repository holds ' +
        `(${said}). Listing them needs a token with access to the repository's ` +
        'own Actions settings, and this screen only ever asks for their names ' +
        '— never a value, which no endpoint would return anyway. What each ' +
        'integration is for is below regardless.',
    };
  }
}

/** Whether one integration's inputs are all set, and which are not. */
export type ConfiguredState = 'configured' | 'absent' | 'partial' | 'unknown';

export interface IntegrationReport {
  integration: Integration;
  state: ConfiguredState;
  /** The declared names that were not found. Empty when `state` is
   *  `unknown`: nothing was found and nothing was looked for. */
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
    return { integration, state: 'unknown', missing: [], family: null };
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
    return { integration, state: 'unknown', missing: [], family: null };
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
