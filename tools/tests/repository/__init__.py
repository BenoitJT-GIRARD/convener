"""This directory carries a package marker and the other test directories do
not, for one reason: five modules elsewhere in the suite import a reader out
of `test_cross_references` and `test_no_literal_copies` -- what this
repository tracks, and which of its pages are served -- and a module imported
by name has to have one name. Without this file it has two, `mypy` says so,
and nothing else here would."""
