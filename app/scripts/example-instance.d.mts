/* Types for example-instance.mjs, so vite.config.ts and the test suite can
 * both import it typed. The script itself stays plain ESM -- see
 * handbook-files.d.mts for why. */

/** The example instance's two data files, as text. Text and not a parsed
 *  shape: `src/data/demo.ts` parses them with the application's own
 *  reader, and a shape declared here would be a second declaration of the
 *  model `src/data/types.ts` already owns. */
export declare function exampleInstance(): { config: string; speakers: string };
