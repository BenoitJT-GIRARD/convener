"""Pieces of a motif drawn for a page rather than for a poster.

A poster is one canvas, and a family draws its motif on it so that the
stroke enters and leaves through the poster's own edges (`ribbon.py`'s own
docstring). A page has no such canvas. Its hero, the stretch under the
first band and the band near its foot are each a box of their own, and a
drawing made for a square, set in one of them, stops wherever the square
does: in the middle of the field, where nothing explains the cut.

So a family may also draw *pieces*, each for one named box, each entering
and leaving through that box's real edges and never ending inside it. The
showcase sets each piece in its box (`site/src/style.css`, the
`.motif-piece` rules) and a family that draws none is drawn the way it
always was. Units are CSS pixels at the showcase's own scale, because a
piece is sized in the stylesheet rather than stretched to fit.

A piece is written as steps rather than as a path: a point the stroke
passes through with the direction it is heading, or an arc of a circle.
Every join between two steps is one cubic whose handles follow the
tangents on both sides, so a curve meets a loop without a corner, and every
arc is cubic too (at most a quarter turn per segment), so a piece is the
same `M` then `C` path every family already writes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

Point = tuple[float, float]
Cubic = tuple[Point, Point, Point, Point]

#: How far a join's handles reach, as a fraction of the distance it spans.
_HANDLE: Final = 0.42


@dataclass(frozen=True)
class Through:
    """The stroke passes through `point`, heading along `direction`."""

    point: Point
    direction: Point


@dataclass(frozen=True)
class Arc:
    """An arc of the circle (`centre`, `radius`) from `start` to `end`.

    Angles are degrees in the SVG plane (x right, y down), so an `end`
    larger than `start` turns clockwise on screen and a smaller one turns
    the other way.
    """

    centre: Point
    radius: float
    start: float
    end: float


Step = Through | Arc


@dataclass(frozen=True)
class Piece:
    """One piece, ready for a template: its box, how the box is fitted to
    the element it sits in (an SVG `preserveAspectRatio`), the stroke's
    width in the box's own units, and the path."""

    width: float
    height: float
    align: str
    stroke_width: float
    path: str

    @property
    def view_box(self) -> str:
        return f"0 0 {_fmt(self.width)} {_fmt(self.height)}"


def _fmt(number: float) -> str:
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text if text and text != "-0" else "0"


def _unit(vector: Point) -> Point:
    length = math.hypot(*vector)
    if length == 0:
        raise ValueError("a direction needs a length")
    return (vector[0] / length, vector[1] / length)


def _on(arc: Arc, degrees: float) -> Point:
    angle = math.radians(degrees)
    return (
        arc.centre[0] + arc.radius * math.cos(angle),
        arc.centre[1] + arc.radius * math.sin(angle),
    )


def _heading(arc: Arc, degrees: float) -> Point:
    """The direction of travel at `degrees`, in the arc's own sense."""
    sense = 1.0 if arc.end > arc.start else -1.0
    angle = math.radians(degrees)
    return (-math.sin(angle) * sense, math.cos(angle) * sense)


def _join(start: Point, heading: Point, end: Point, arriving: Point) -> Cubic:
    reach = _HANDLE * math.hypot(end[0] - start[0], end[1] - start[1])
    return (
        start,
        (start[0] + heading[0] * reach, start[1] + heading[1] * reach),
        (end[0] - arriving[0] * reach, end[1] - arriving[1] * reach),
        end,
    )


def _arc_cubics(arc: Arc) -> list[Cubic]:
    """The arc as cubics of at most a quarter turn, the standard
    `4/3 * tan(theta / 4)` handle length that keeps each one on the circle."""
    turns = max(1, math.ceil(abs(arc.end - arc.start) / 90.0))
    sweep = (arc.end - arc.start) / turns
    handle = 4.0 / 3.0 * math.tan(math.radians(sweep) / 4.0) * arc.radius
    cubics: list[Cubic] = []
    for i in range(turns):
        a0 = arc.start + sweep * i
        a1 = a0 + sweep
        p0, p3 = _on(arc, a0), _on(arc, a1)
        r0, r1 = math.radians(a0), math.radians(a1)
        p1 = (p0[0] - math.sin(r0) * handle, p0[1] + math.cos(r0) * handle)
        p2 = (p3[0] + math.sin(r1) * handle, p3[1] - math.cos(r1) * handle)
        cubics.append((p0, p1, p2, p3))
    return cubics


def cubics(steps: tuple[Step, ...]) -> list[Cubic]:
    """Every cubic a piece's steps draw, in order, one continuous stroke."""
    if not steps:
        raise ValueError("a piece needs at least one step")
    drawn: list[Cubic] = []
    pen: Point | None = None
    heading: Point | None = None
    for step in steps:
        if isinstance(step, Through):
            arriving = _unit(step.direction)
            if pen is not None and heading is not None:
                drawn.append(_join(pen, heading, step.point, arriving))
            pen, heading = step.point, arriving
        else:
            first = _on(step, step.start)
            if pen is not None and heading is not None:
                drawn.append(_join(pen, heading, first, _heading(step, step.start)))
            drawn.extend(_arc_cubics(step))
            pen, heading = _on(step, step.end), _heading(step, step.end)
    if not drawn:
        raise ValueError("a piece needs a stroke, not a single point")
    return drawn


def piece(
    width: float,
    height: float,
    *,
    align: str,
    stroke_width: float,
    steps: tuple[Step, ...],
) -> Piece:
    """A `Piece` from its box and its steps."""
    drawn = cubics(steps)
    start = drawn[0][0]
    commands = [f"M {_fmt(start[0])} {_fmt(start[1])}"]
    for _start, c1, c2, end in drawn:
        coordinates = (*c1, *c2, *end)
        commands.append("C " + " ".join(_fmt(value) for value in coordinates))
    return Piece(
        width=width,
        height=height,
        align=align,
        stroke_width=stroke_width,
        path=" ".join(commands),
    )
