module.exports = function (cfg) {
  cfg.addPassthroughCopy('src/style.css');
  // Self-hosted fonts and their licences. Copied rather than pulled from a CDN
  // at runtime: the phase 5 specification forbids any third-party dependency,
  // and a webfont request is one — it discloses every visitor's address.
  cfg.addPassthroughCopy('src/fonts');
  // Phase 5, task 2: the public showcase repository now receives this
  // project's own build output at its root, alongside `app/`, which is
  // exactly what its already-active GitHub Pages setting ("branch main,
  // folder root") serves. Without this file, GitHub's default Jekyll
  // processing swallows that output and serves the README instead. Sourced
  // here rather than `touch`-ed by the publish workflow so that the built
  // site is reproducible from this repository alone.
  cfg.addPassthroughCopy('src/.nojekyll');
  return {
    dir: { input: 'src', output: '_site' },
    templateFormats: ['njk', 'md'],
    htmlTemplateEngine: 'njk',
  };
};
