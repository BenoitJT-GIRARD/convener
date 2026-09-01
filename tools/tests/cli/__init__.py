"""This directory carries a package marker, and its `journey/` does too, for
the reason `tools/tests/repository/__init__.py` gives about itself: a module
imported by name has to have one name. `cli/` mirrors `convener_ops/cli/`,
which dispatches into sub-packages that already have test directories of
their own, so `cli/journey/test_certificate.py` and
`journey/test_certificate.py` are two modules with one basename -- and
without these two files that is a collection error for pytest and a
duplicate module for `mypy`, on the day the mirror becomes real."""
