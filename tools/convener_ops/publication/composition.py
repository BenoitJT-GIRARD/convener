"""Where the generated poster's own bands sit, for the readers that are
not the poster.

One figure, and it is here rather than in `visual.py` because three
modules read it and `visual.py` is not importable by two of them:
`motifs/steps.py` and `motifs/chevrons.py` are imported *by*
`motifs/__init__.py`, which `visual.py` imports, so a family reaching for
the poster's own measurement would close a cycle. Each of the two carried
its own copy of the number instead -- `0.224`, written down twice, with
`visual.py` implicitly carrying a third answer by not using it at all --
which is the shape this project deletes on sight.

A family may not read a charter and may not read a page. What it may read
is a fact about the composition every one of them is drawn into, which is
what this module is.
"""

from __future__ import annotations

from typing import Final

__all__ = ["CONTENT_TOP"]

#: The row `.content` begins at, as a fraction of the page's height, on
#: the format where it begins earliest.
#:
#: `.content` is the generated poster's last band before the register band
#: -- the "what to expect" copy and the speaker's photographic plate beside
#: it. Measured in the pinned engine it begins at 0.317 of a square and
#: 0.224 of an A4 print, and the banner drops the band outright (see
#: `visual.py`'s "The wide derivation"). The earliest of the three is the
#: one every reader here wants: a drawing that clears the band on the
#: print clears it on the square as well.
#:
#: What reads it, and what each does with it:
#:
#: - `visual._motif_content_right_margin` pads `.content`'s own right with
#:   the family's reach *over these rows*. It used the clearance alone
#:   until this figure had a home -- an argument about where the ribbon's
#:   right side happens to run, made into the rule for every family -- and
#:   this instance's own poster had the ribbon's right loop painted 14.4
#:   pixels across the speaker's plate on the square and 29.8 on the
#:   print, at every gate green, because the one rendering anything
#:   compared was the example's charter and the example's charter draws
#:   `bracket`.
#: - `motifs/steps.py` and `motifs/chevrons.py` each decide how far down
#:   the right of the page their own drawing runs. Both stop above this
#:   row on purpose, which is a design choice about the drawing rather
#:   than a rule the composition imposes -- `_motif_content_right_margin`
#:   now holds the composition to whatever a family does.
#:
#: It is a measurement of a rendered page and cannot be derived: `.content`
#: is a flex band whose top is decided by the bands above it, and the
#: engine that lays them out is the browser. `tools/visuals/check-posters.mjs`
#: is what re-measures the consequence, over every charter, every family
#: and every canvas.
CONTENT_TOP: Final = 0.224
