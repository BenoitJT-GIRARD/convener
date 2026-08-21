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
];
