/* The lint configuration the three relays share, and the only place their
 * rules are written.
 *
 * Each of them had its own copy of this file. The copies were never quite
 * identical -- each granted the globals its own source uses -- so the
 * duplication was invisible in the way that matters: three files that
 * differ in six lines out of twenty-five read as three configurations,
 * and a rule added to one of them is a rule missing from the other two
 * with nothing to say so. What is actually shared is the whole of the
 * shape: the language version, the module system, the six globals every
 * Worker has, and the three rules. What is actually each relay's own is
 * the handful of globals its own code reaches for, and that is the
 * argument for a function rather than a configuration object to spread:
 * a relay declares what it uses and inherits everything else, instead of
 * restating the shape in order to add a word to it.
 *
 * Deliberately free of any plugin dependency, which is the reason the
 * original copies gave and it has not changed: a relay's failure locks
 * somebody out -- of signing in, of proposing a talk, of registering --
 * so its quality gate should not rest on anything beyond eslint itself,
 * invoked through `npx` exactly as `quality.yml` already invokes cspell.
 *
 * `.mjs` rather than `.js`: this file sits above the three
 * `package.json` that declare `"type": "module"` and below no other, so
 * Node would read a `.js` here as CommonJS and refuse the `export`
 * below. The relays' own configuration files stay `.js`, inside the
 * packages that declare what that means.
 */

/** The globals every Cloudflare Worker has, and every one of these three
 *  actually uses. `globalThis` is writable because a test replaces
 *  `fetch` on it. */
const WORKER_GLOBALS = {
  fetch: 'readonly',
  Request: 'readonly',
  Response: 'readonly',
  URL: 'readonly',
  console: 'readonly',
  globalThis: 'writable',
};

/** The three rules, and the reason there are three: each one catches a
 *  defect that reaches production silently -- a binding nobody reads, a
 *  name nothing defines, a comparison that coerces. */
const RULES = {
  'no-unused-vars': 'error',
  'no-undef': 'error',
  eqeqeq: 'error',
};

/**
 * One relay's configuration: the shared shape, plus the globals that
 * relay's own source reaches for.
 *
 * A global granted here is a name eslint will not complain about, so the
 * list a relay passes is a claim about the runtime it deploys to. Adding
 * one it does not have buys a lint run that passes and a Worker that
 * throws.
 *
 * @param {Record<string, 'readonly' | 'writable'>} globals
 */
export function relayConfig(globals = {}) {
  return {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...WORKER_GLOBALS, ...globals },
    },
    rules: RULES,
  };
}
