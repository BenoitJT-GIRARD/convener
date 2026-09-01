/* Types for instance-paths.mjs, so vite.config.ts and the test suite can
 * both import it typed. The script itself stays plain ESM -- see
 * handbook-files.d.mts for why. */

/** The declared paths, keyed by their final component. */
export declare function byLastComponent(paths: string[]): Record<string, string>;

/** Every path an already-loaded `declarations/boundary.yml` hands to the instance. */
export declare function handedFrom(data: unknown): string[];

/** The declared instance paths, keyed by their final component. */
export declare function instancePaths(): Record<string, string>;

/** The declared instance path whose final component is `name`. */
export declare function handed(name: string): string;

/** The instance's own records and its governance configuration. */
export declare function dataDir(): string;

/** The instance's published public keys, event keys and signing keys both. */
export declare function keysDir(): string;

/** Everything the instance publishes about itself. */
export declare function publicDataDir(): string;

/** The decision register. */
export declare function registerPath(): string;
