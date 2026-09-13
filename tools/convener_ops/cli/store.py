"""The store's two YAML files, read and written in the dialect the browser writes.

`instance/data/speakers.yml` and `instance/data/config.yml` are written by
this package and by `app/src/data/yaml.ts`, and both sides have to produce
the same bytes for the same records: a file rewritten by whichever wrote
last, in its own dialect, is a diff nobody made. So there is one writer
here rather than one per command, and `app/src/data/yaml.ts` is its other
half -- `tools/tests/fixtures/speakers-from-app.yml` is written by one and
read by the other.

`load` is the reading side, and it is here rather than beside a command
for the smaller reason: every command that opens one of these files wants
the same two-part answer, the document or the sentence saying why not.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from convener_ops.declaration.yaml_safe import safe_load as yaml_safe_load

#: The header line each data file carries. `app/src/data/yaml.ts` holds the
#: same two strings: it is the browser's half of this file format, and the
#: YAML-boundary fixture is written by one side and read by the other.
SPEAKERS_HEADER = "# Speakers (unified schema v6 — see docs/engineering/schema.md)\n"


CONFIG_HEADER = "# Repo-wide config for the convener app\n"


class _Dumper(yaml.SafeDumper):
    """SafeDumper that writes a multi-line string the way js-yaml does.

    PyYAML's default for a string containing a newline is a single-quoted
    scalar with the line breaks folded through blank lines; js-yaml writes a
    literal block (`|-`). Both read back identically, but they are different
    bytes for the same abstract, so a talk abstract typed into the browser
    form and later touched by the sweep would be rewritten wholesale by
    whichever side wrote last. `_represent_str` below makes this package
    write the block form too -- see `app/src/data/yaml.ts::DUMP` for the
    browser's half, and `tools/tests/fixtures/speakers-from-app.yml` for the
    fixture that holds the two together.
    """


#: Text that js-yaml quotes on write and PyYAML would leave bare.
#:
#: Both loaders read every one of these back as a string, so this is not a
#: correctness fix -- it is a formatting one, and the fixture is byte-level,
#: so it has to be made. The four families, all of them YAML 1.1 leftovers
#: js-yaml still defends against: a sexagesimal time whose first digit is a
#: zero (`09:05`; PyYAML's own int resolver requires 1-9 there, which is why
#: `12:30` needs nothing added), an exponent with no decimal point (`1e3`),
#: the one-letter booleans (`y`, `Y`, `n`, `N`), and a YAML 1.2 octal
#: (`0o17`). The exponent alternative deliberately excludes any form with a
#: decimal point: that is what a real float represents as, and quoting one
#: would turn a number into a string on the next read.
_QUOTE_LIKE_JS_YAML = re.compile(
    r"""^(?:[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+
        |[-+]?[0-9][0-9_]*[eE][-+]?[0-9]+
        |[yYnN]
        |[-+]?0o[0-7_]+)$""",
    re.X,
)


# Registered on the dumper only. The tag names what the scalar would be
# mistaken for; all that matters to the emitter is that it is not `str`, which
# is what makes it quote the value.
_Dumper.add_implicit_resolver(
    "tag:yaml.org,2002:int", _QUOTE_LIKE_JS_YAML, list("-+0123456789yYnN")
)


def _represent_str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _represent_str)


def dump(data: Any) -> str:
    """The one YAML writer of this package.

    Every writer -- the sweep, the form handler, the v3 migration -- goes
    through it, so a file written by any of them keeps the same shape and
    stays readable by the browser.
    """
    return yaml.dump(
        data,
        Dumper=_Dumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=1000,
    )


def dump_speakers(speakers: Any) -> str:
    return SPEAKERS_HEADER + dump(speakers)


def under_its_own_header(original: str, body: str, fallback: str) -> str:
    """`body`, under whatever header `original` already carried.

    The constants above are what a *fresh* file gets, and they are pinned byte
    for byte against `app/src/data/yaml.ts`. They are not what an existing file
    should be handed back. This repository's own
    `instance/data/speakers.yml` opened with sixty-seven lines saying that
    nobody in it is real, why every address is under `.test` and why every
    board login is prefixed -- and the nightly sweep replaced all of it with
    one line, in a commit that said it had swept elapsed events. Nobody
    noticed for a day.

    The file is reviewed in ordinary pull requests and, on a real instance,
    holds personal data. Its header is what tells a reader which of the two
    they are looking at.

    A file with no header of its own gets `fallback`, which is the only case
    the constant was ever for.
    """
    lead: list[str] = []
    for line in original.split("\n"):
        if line.lstrip().startswith("#") or not line.strip():
            lead.append(line)
        else:
            break
    if not any(line.lstrip().startswith("#") for line in lead):
        return fallback + body
    return "\n".join(lead) + "\n" + body


def speakers_under_own_header(original: str, speakers: Any) -> str:
    """What a writer of an existing `speakers.yml` should produce."""
    return under_its_own_header(original, dump(speakers), SPEAKERS_HEADER)


def dump_config(config: Any) -> str:
    return CONFIG_HEADER + dump(config)


def load(path: Path) -> tuple[Any, list[str]]:
    if not path.exists():
        return None, [f"{path.name}: file missing"]
    try:
        return yaml_safe_load(path.read_text(encoding="utf-8")), []
    except yaml.YAMLError as exc:
        return None, [f"{path.name}: invalid YAML - {exc}"]
