/* Types for example-settings.mjs, so vite.config.ts and the test suite can
 * both import it typed. The script itself stays plain ESM -- see
 * handbook-files.d.mts for why. */

/** The six declarations the demonstration's settings screen reads, as text,
 * plus the drain workflow's own `on:` block converted from YAML to JSON.
 *
 * Text and not a parsed shape, for the reason `example-instance.d.mts`
 * gives: `src/settings/declaration.ts` parses them with the reader the
 * signed-in path uses, and a shape declared here would be a second
 * declaration of what `declarations/boundary.yml` already owns.
 *
 * `drainTriggers` is `unknown` on purpose. What a schedule *means* is
 * `src/settings/bounds.ts::drainCadence`'s decision, pinned to
 * `registration_routing.drain_period_hours` by a shared fixture; this
 * build only carries the block across, and a type here that described its
 * shape would be that decision written down a second time. */
export declare function exampleSettings(): {
  files: Record<string, string>;
  drainTriggers: unknown;
};
