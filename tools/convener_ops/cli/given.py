"""A value an operator hands a command, and the order the two ways of
handing it are read in.

Three commands here take a value from an operator standing at their own
terminal rather than from a record: the event an identifier is encrypted
under, the address it names, the event an attendance export belongs to,
and the ids and day a key destruction is recorded for. All of them are
driven by environment variable in continuous integration, because that is
how a workflow passes a value into a step (`env:`), and every one of them
was **only** that -- `EVENT_ID=<event id> uv run convener-...`, a shape
Windows PowerShell 5.1 has no form of at all. It is not a wording
problem: there is no third spelling both shells accept, so the page
telling a Windows operator to run one of these was telling them to type
something their shell refuses outright.

So each of them takes the value as an option as well, and this is the one
place the order is decided:

**the option first, the environment second.** An operator who names a
value on the command line means that value; the environment is what
answers when they name none, which keeps every workflow passing the same
variables it always did. Nothing here defaults, invents or merges: a
value given twice is the option's, and a value given nowhere is the empty
string, which each command already refuses in its own words.

Stated once, in code, rather than three times in three docstrings and
twice more in two pages -- `docs/engineering/content-rules.md`'s first
rule applied to a rule about behaviour. `tools/tests/cli/test_given.py`
holds it, and `tools/tests/repository/test_typed_commands.py` is what
stops a page going back to the prefix.
"""

from __future__ import annotations

import os


def value(option: str | None, variable: str) -> str:
    """What the operator gave, stripped: `option` when they named one,
    `os.environ[variable]` when they did not, and `""` when neither is
    there.

    `option` is `None` rather than `""` for "not given", which is what
    `argparse` hands back for an option with no default -- an operator
    who passes `--event ""` has named an empty event, and that is refused
    by the command rather than quietly replaced by whatever the
    environment happens to hold.
    """
    if option is not None:
        return option.strip()
    return os.environ.get(variable, "").strip()
