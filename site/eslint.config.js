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
        // Task 8 (phase 6): `icsFoldLine`'s own UTF-8-aware line folding
        // needs byte access a JavaScript string does not give directly --
        // `Buffer`, Node's own built-in, no new dependency. The only file
        // this bare, unscoped block actually lints is `.eleventy.js`
        // itself, and this is the first place in it that has ever needed
        // a Node global beyond `module`/`require`.
        Buffer: 'readonly',
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
  // CommonJS block does not declare. Phase 10 task 2 added two more under
  // the same override -- `published.cjs`, this package's own reader of
  // `config/instance.json`, and `print-published.cjs`, which prints what
  // that reader and the real `.eleventy.js` resolve for the Python suite
  // to compare -- and `URL` with them, the parser `published.cjs` uses to
  // take the declared address apart rather than doing it with a regular
  // expression.
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
        URL: 'readonly',
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
