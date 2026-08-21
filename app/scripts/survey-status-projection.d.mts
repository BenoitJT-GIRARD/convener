/* Types for survey-status-projection.mjs, so the test suite can assert its
 * rules. The script itself stays plain ESM -- see
 * certificates-projection.d.mts for the identical reason. */
export declare const DEST_FILENAME: string;
export declare const PUBLIC_DIR: string;
export declare function readProjection(srcPath: string): Promise<unknown[]>;
export declare function writeProjection(
  srcPath: string,
  dstDir: string,
): Promise<{ ids: unknown[]; dest: string }>;
