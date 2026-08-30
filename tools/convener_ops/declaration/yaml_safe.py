"""A `yaml.safe_load` that does not misread hand-typed dates and times.

PyYAML's default resolvers still carry two YAML 1.1 behaviours that YAML 1.2
(and js-yaml, which this data interchanges with) dropped:

* `HH:MM` is resolved as a **sexagesimal integer** — `12:30` becomes `750`,
  not the string `"12:30"`.
* An unquoted `YYYY-MM-DD` is resolved as a `datetime.date`, not a string.

The app's browser-side YAML writer (js-yaml) always quotes both fields, so
files it produces are unambiguous either way. But this repository is meant
to survive a volunteer hand-editing `instance/data/speakers.yml` in a text editor,
and an unquoted `time: 12:30` typed by hand must still come back as the
string `"12:30"`, not the integer 750 — which is exactly what broke
`validate-data`, the nightly sweep, and the browser's own re-read of the
same field.

`safe_load` below is a drop-in replacement for `yaml.safe_load` that keeps
every other SafeLoader behaviour (ints, floats, bools, null, dates that are
never meant to be strings elsewhere in the config) and only removes the two
resolvers above.
"""

from __future__ import annotations

import re
from typing import Any

import yaml


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader without the sexagesimal-int and implicit-timestamp resolvers."""


# YAML 1.2 core-schema int: no sexagesimal (`h:mm:ss`) alternative. This is
# PyYAML's own `int` regexp with that one alternative removed.
_INT_RE = re.compile(
    r"""^(?:[-+]?0b[0-1_]+
        |[-+]?0[0-7_]+
        |[-+]?(?:0|[1-9][0-9_]*)
        |[-+]?0x[0-9a-fA-F_]+)$""",
    re.X,
)

# Drop the built-in timestamp resolver entirely (dates in this repository's
# data files are always meant to come back as plain `YYYY-MM-DD` strings,
# validated by regex in convener_ops.validate, not as datetime.date objects), and
# drop the built-in int resolver too -- it's the one with the sexagesimal
# alternative baked in. A corrected int resolver is added back below.
_StrictLoader.yaml_implicit_resolvers = {
    first: [
        (tag, regexp)
        for tag, regexp in resolvers
        if tag not in ("tag:yaml.org,2002:timestamp", "tag:yaml.org,2002:int")
    ]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_StrictLoader.add_implicit_resolver(
    "tag:yaml.org,2002:int", _INT_RE, list("-+0123456789")
)


def safe_load(text: str) -> Any:
    """Like `yaml.safe_load`, but immune to the sexagesimal-int and
    implicit-timestamp misreads described above."""
    # _StrictLoader is a yaml.SafeLoader subclass with no added constructors,
    # so this is exactly as safe as yaml.safe_load (itself just
    # yaml.load(Loader=SafeLoader)); bandit flags any yaml.load call by name.
    return yaml.load(text, Loader=_StrictLoader)  # nosec B506
