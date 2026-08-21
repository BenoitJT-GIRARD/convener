/* Types for certificates-projection.mjs, so the test suite can assert its
 * rules. The script itself stays plain ESM -- see handbook-files.d.mts for
 * why. */
export declare const DEST_FILENAME: string;
export declare const PUBLIC_DIR: string;
export declare function readProjection(srcPath: string): Promise<unknown[]>;
export declare function writeProjection(
  srcPath: string,
  dstDir: string,
): Promise<{ rows: unknown[]; dest: string }>;
