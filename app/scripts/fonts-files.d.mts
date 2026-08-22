/* Types for fonts-files.mjs, so the test suite can assert its rules.
 * The script itself stays plain ESM -- see handbook-files.d.mts for why. */
export declare const PUBLIC_FONTS_DIR: string;
export declare function writeFonts(
  srcDir: string,
  dstDir: string,
): Promise<{ files: string[] }>;
