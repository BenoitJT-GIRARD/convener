/* Types for csp.mjs, so vite.config.ts and the test suite can both import
 * it typed. The script itself stays plain ESM -- see handbook-files.d.mts
 * for why. */
export declare function cspMetaContent(env: Record<string, string | undefined>): string;
