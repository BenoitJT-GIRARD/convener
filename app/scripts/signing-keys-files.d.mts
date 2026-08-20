/* Types for signing-keys-files.mjs, so the test suite can assert its rules.
 * The script itself stays plain ESM -- see handbook-files.d.mts for why. */
export declare const INDEX_FILENAME: string;
export declare function sortDescending(filenames: string[]): string[];
export declare function readPublicKeys(dir: string): Promise<string[]>;
