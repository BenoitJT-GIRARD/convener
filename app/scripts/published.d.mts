/* Types for published.mjs, so vite.config.ts and the test suite can both
 * import it typed. The script itself stays plain ESM -- see
 * handbook-files.d.mts for why. */
export declare function published(): {
  url: string;
  origin: string;
  pathPrefix: string;
  appBase: string;
};
