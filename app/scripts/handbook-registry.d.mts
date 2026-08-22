/* Types for handbook-registry.mjs, so the test suite can assert its rules.
 * The script itself stays plain ESM -- see handbook-files.d.mts for why. */
export declare function stripComments(text: string): string;
export declare function parseContentFiles(source: string): string[];
export declare function parsePublicAssets(source: string): string[];
export declare function publishedPaths(registrySource: string): string[];
export declare function walkAll(dir: string, base?: string): Promise<string[]>;
export declare function copyHandbook(args: {
  docsDir: string;
  registrySource: string;
  dst: string;
}): Promise<{ files: string[]; counts: Map<string, number> }>;
