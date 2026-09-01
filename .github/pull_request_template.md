<!--
`CONTRIBUTING.md` states what a contribution certifies and which gates it
has to leave green. This is the acting half of that page: four boxes, each
one a thing to do rather than a thing to have read. Tick what is true and
leave the rest untouched -- an unticked box is information, and a ticked
one that is not true is the only way this template can do harm.
-->

## What this changes



## Before it can be merged

- [ ] **Every commit carries one `Signed-off-by`.** `git commit -s` writes
      it, using your configured name and email. By adding it you certify
      the Developer Certificate of Origin 1.1 and grant the one further
      right `CONTRIBUTING.md` asks for, which it explains in full.
- [ ] **`sh gates.sh` is green** on this branch, from the repository root.
      That is every check `.github/workflows/quality.yml` runs, and none of
      them needs an account or a secret. The four that live in workflows of
      their own need a browser binary; `gates.sh`'s own header names them.
- [ ] **Nothing is copied.** A passage needed on a second page is included
      from the first rather than written twice
      (`docs/engineering/content-rules.md`), and a test refuses the copy.
- [ ] **If this is a substantial contribution**, one line in *What this
      changes* above, in your own words, saying that it is yours to
      contribute.
