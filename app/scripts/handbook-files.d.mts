/* Types for the copy step's file rule, so the test suite can assert it.
 * The script itself stays plain ESM: it runs under bare `node` in `prebuild`,
 * where a TypeScript source would need a toolchain that is not there yet. */
export declare const SKIP_DIRS: Set<string>;
export declare const SERVED_EXTENSIONS: string[];
export declare function isServed(name: string): boolean;
export declare function walk(dir: string, base?: string): Promise<string[]>;
