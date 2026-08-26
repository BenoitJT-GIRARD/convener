/**
 * The band a duplicate that has not been configured publishes above its
 * own chrome.
 *
 * A duplicate that has not been configured should say so, loudly, rather
 * than publish silently under somebody else's identity. That is the
 * direct continuation of a rule this project already settled: a default
 * that leaks when you forget it is not a default, it is a trap.
 *
 * `unconfiguredFields()` (src/instance.ts, from the define
 * `vite.config.ts` fills from `scripts/published.mjs::unconfigured`) is
 * the list of values this bundle's `config/instance.json` still shares
 * with the example declaration the product ships. Empty for a configured
 * instance, so this renders nothing at all on one -- no reserved strip of
 * screen, no markup. The whole rule, and why the `REPLACE` marker is
 * deliberately no part of it, is stated once in
 * `tools/convener_ops/published.py::unconfigured`.
 *
 * Above the sign-in screen as well as above the cockpit, because the
 * sign-in screen is the only one of the two a *visitor* reaches: the
 * cockpit itself is behind a GitHub sign-in, and a warning only an
 * operator can see is a warning addressed to the one person who already
 * knows. `site/src/_includes/layout.njk` carries the same band across
 * every page of the showcase for the same reason.
 *
 * The keys are named rather than counted. A banner that says something is
 * wrong and cannot say what sends its reader through a file; one that
 * says `identity.contact` sends them to a line.
 */
import { unconfiguredFields } from '../instance';

export function UnconfiguredBanner() {
  const fields = unconfiguredFields();
  if (fields.length === 0) return null;
  return (
    <div className="bg-danger/10 border-b-4 border-danger text-sm py-3 px-6">
      <div className="max-w-content mx-auto">
        <p className="font-display font-bold text-[11px] tracking-widest uppercase text-danger mb-1">
          Not configured
        </p>
        <p className="text-ink">
          This deployment still declares the identity the software ships as its
          worked example, so nothing here names a real organisation, a real
          address or a real contact. Fill in{' '}
          <code className="font-mono text-xs">config/instance.json</code> — still
          the example&rsquo;s:{' '}
          <code className="font-mono text-xs break-words">{fields.join(', ')}</code>.
        </p>
      </div>
    </div>
  );
}
