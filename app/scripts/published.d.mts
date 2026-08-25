/* Types for published.mjs, so vite.config.ts and the test suite can both
 * import it typed. The script itself stays plain ESM -- see
 * handbook-files.d.mts for why. */
export declare function published(): {
  url: string;
  origin: string;
  pathPrefix: string;
  appBase: string;
};

/** Who runs this series -- `config/instance.json`'s own `identity`, plus
 *  the one derived name both sides compose (`forum_host`). A record rather
 *  than a named shape: `src/instance.ts` declares the vocabulary for the
 *  browser side, and a second declaration of it here would be the copy the
 *  whole design refuses. */
export declare function identity(): Record<string, string>;
