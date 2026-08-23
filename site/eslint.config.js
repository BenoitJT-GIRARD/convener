// Minimal flat config, deliberately free of any plugin dependency: the same
// pattern services/auth-proxy's own eslint.config.js already uses, invoked
// via npx (see quality.yml's `site` job). CommonJS, matching .eleventy.js —
// this package.json carries no "type": "module".
module.exports = [
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'commonjs',
      globals: {
        module: 'writable',
        require: 'readonly',
      },
    },
    rules: {
      'no-unused-vars': 'error',
      'no-undef': 'error',
      eqeqeq: 'error',
    },
  },
  // Fix round 1: scripts/check-paris-standing-start.cjs -- a plain
  // CommonJS Node script (`.cjs`, so it parses as CommonJS regardless of
  // this package.json's own missing "type": "module", the same guarantee
  // the `.mjs` extension gives the block below for the opposite case), but
  // one that (unlike `.eleventy.js` above) actually reads a file and
  // reports to the console, so it needs the Node globals the bare
  // CommonJS block does not declare.
  {
    files: ['scripts/*.cjs'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'commonjs',
      globals: {
        module: 'writable',
        require: 'readonly',
        __dirname: 'readonly',
        process: 'readonly',
        console: 'readonly',
      },
    },
    rules: {
      'no-unused-vars': 'error',
      'no-undef': 'error',
      eqeqeq: 'error',
    },
  },
  // Task 11: scripts/check-a11y.mjs -- an `.mjs` file, always parsed as an
  // ES module by Node regardless of this package.json's own missing
  // "type": "module" (that field only decides how a bare `.js` extension
  // is read), so it needs `sourceType: 'module'` and Node's own runtime
  // globals rather than the CommonJS block above, which would otherwise
  // reject its `import` statements as a parse error. `document`/`window`
  // are also declared here: some functions in this file are never called
  // in Node at all -- they are handed to Puppeteer's `page.evaluate` and
  // actually run inside the real browser page under test, where both
  // exist.
  {
    files: ['scripts/*.mjs'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        process: 'readonly',
        console: 'readonly',
        URL: 'readonly',
        fetch: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        document: 'readonly',
        window: 'readonly',
      },
    },
    rules: {
      'no-unused-vars': 'error',
      'no-undef': 'error',
      eqeqeq: 'error',
    },
  },
];
