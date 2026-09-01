/* Types for published.mjs, so vite.config.ts and the test suite can both
 * import it typed. The script itself stays plain ESM -- see
 * handbook-files.d.mts for why. */
export declare function published(): {
  url: string;
  origin: string;
  pathPrefix: string;
  appBase: string;
};

/** Who runs this series -- `instance/config.json`'s own `identity`, plus
 *  the one derived name both sides compose (`forum_host`). A record rather
 *  than a named shape: `src/instance.ts` declares the vocabulary for the
 *  browser side, and a second declaration of it here would be the copy the
 *  whole design refuses. */
export declare function identity(): Record<string, string>;

/** The prefix this instance numbers its editions under -- `config/
 *  instance.json`'s own `edition_prefix`. A bare string rather than a
 *  shape: it is one value, not a vocabulary. */
export declare function editionPrefix(): string;

/** Whether a value is a prefix this product will number editions under.
 *  Exported so `tools/tests/fixtures/edition-prefix.json` can be answered
 *  by both readers rather than by a comment claiming they agree; `unknown`
 *  because refusing a non-string is part of what it decides. */
export declare function isEditionPrefix(value: unknown): boolean;

/** Which of this instance's declared values are still the ones the product
 *  ships in `examples/the-example-collective/instance/config.json` -- empty for an
 *  instance somebody has configured, and the names of the offending keys
 *  for one nobody has. Sorted, so a bundle's own define is stable between
 *  builds. */
export declare function unconfigured(): string[];

/** The same answer as `unconfigured`, given two declarations already in
 *  hand. Exported because reading the two files is not always possible
 *  where the question is: a module the test runner transformed has no
 *  `file:` `import.meta.url`, so `unconfigured`'s own reads throw there.
 *  `unknown` on both sides because deciding what a declaration holds is
 *  part of what it does. */
export declare function unconfiguredFrom(
  declaration: unknown,
  example: unknown,
): string[];
