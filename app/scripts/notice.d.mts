/* Types for notice.mjs, so vite.config.ts and the test suite can both import
 * it typed. The script itself stays plain ESM -- see handbook-files.d.mts for
 * why. */

/** Every key `NOTICE.json` has to carry, and the whole of it. */
export declare const FIELDS: string[];

/** The product's own Appropriate Legal Notice -- `NOTICE.json`'s own fields.
 *  A record rather than a named shape: `src/notice.ts` declares the
 *  vocabulary for the browser side, and a second declaration of it here would
 *  be the copy the whole design refuses. */
export declare function notice(): Record<string, string>;
