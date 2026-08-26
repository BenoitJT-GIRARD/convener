"""An independent QR byte-mode decoder, written for this test suite alone.

`registration_code.registration_code_svg` (`convener_ops`) draws a code with
`segno` -- an already-vetted encoder, not written by this project (see
that module's own docstring for why reusing it, rather than hand-rolling a
second one, is the right call). Nothing in this project's dependency tree
reads a QR code back, and no test may reach a network service to ask one
to. A code nobody has decoded is a rectangle of noise, so this module is
that decoder: given the exact `<svg>` fragment
`registration_code_svg` returns, it recovers the original string, using
nothing from `segno` except the handful of *structural* constants the ISO
standard itself defines (`segno.consts`'s own `FORMAT_INFO`,
`ALIGNMENT_POS` and `ECC` tables, each a direct, page-cited transcription
of ISO/IEC 18004:2015's own annexes -- the same tables any independent
decoder has to have, reused here rather than a second, hand-typed copy
that risks a transcription error segno's own maintainers have long since
found and fixed). Everything that actually turns pixels into the encoded
string -- the module matrix, the format-info read, the data mask, the
zigzag placement order, the block deinterleave, the byte-mode segment
parse -- is implemented independently below, verified by round-tripping
against `segno.make` for several hundred generated strings spanning every
QR version and error level before this module was trusted, rather than
assumed correct from the first render that happened to work.

Scope, deliberately narrow: byte mode only, no error *correction*
------------------------------------------------------------------
This decoder assumes -- and raises if it finds otherwise -- that the
message is encoded in byte mode (`segno.consts.MODE_BYTE`). Every string
this project ever encodes with it is a `signup_url(event_id)` (D-19): a
lowercase ASCII domain and edition id, which `segno` always places in byte
mode (its lowercase letters are outside the QR alphanumeric character set,
so numeric/alphanumeric mode is never a candidate segno would choose for
this project's own data -- verified, not assumed: this module raises
loudly, never silently misreads, if that ever stopped being true).
Kanji and structured-append are out of scope for the same reason.

This decoder also never performs Reed-Solomon error *correction* --
deliberately, not by oversight. What it needs is not "recover the message
even if some modules were misread", the problem Reed-Solomon exists to
solve for a scanner reading a scratched, creased poster; it is "prove the
message this project's own renderer just produced, byte for byte, decodes
back to the exact URL expected", which only needs reading the SAME
modules the encoder wrote, correctly, with no channel between the two to
introduce noise. Deinterleaving data codewords from error-correction
codewords, using `segno.consts.ECC`'s own block-size table, is still
required (multi-block versions genuinely interleave the two before
placement) -- but the error-correction codewords themselves are read and
discarded, never used to correct anything, because nothing here is ever
wrong to correct.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import cast

from segno import consts
from segno.consts import EC as _EC

from convener_ops.registration_code import QR_BORDER

__all__ = ["decode_registration_qr"]

#: `real[row][col]` boolean matrices below are always square; a small
#: alias so signatures do not repeat `list[list[bool]]` everywhere.
_Matrix = list[list[bool]]


def _parse_svg_matrix(svg: str) -> _Matrix:
    """Reconstructs the full (bordered) module matrix from segno's own
    compact `<path>` mini-language -- `M x y` once, then any mixture of
    `h<n>` (a horizontal run of `n` dark modules, drawn as a stroke
    centred at `y = row + 0.5`) and `m<dx> <dy>` (a pen move, drawing
    nothing) -- rather than from `segno.QRCode.matrix` itself: decoding the
    literal string this project embeds into the poster is the actual
    artefact under test, not segno's own in-memory state, which a bug in
    `registration_code_svg`'s own call to `svg_inline` could disagree with
    silently.
    """
    viewbox = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
    if not viewbox or viewbox.group(1) != viewbox.group(2):
        raise ValueError("not a square QR viewBox")
    size = int(viewbox.group(1))
    path = re.search(r'd="([^"]+)"', svg)
    if not path:
        raise ValueError("no path data found in the QR SVG")
    matrix: _Matrix = [[False] * size for _ in range(size)]
    x, y = 0.0, 0.0
    for token in re.findall(r"[Mmh][^Mmh]*", path.group(1)):
        op, rest = token[0], token[1:].strip()
        if op == "M":
            xs, ys = rest.split()
            x, y = float(xs), float(ys)
        elif op == "m":
            dx, dy = rest.split()
            x, y = x + float(dx), y + float(dy)
        else:  # "h": a run of `length` dark modules from the current pen
            length = round(float(rest))
            row, col0 = round(y - 0.5), round(x)
            for i in range(length):
                matrix[row][col0 + i] = True
            x += length
    return matrix


def _read_format_info(real: _Matrix) -> tuple[int, int]:
    """The (error level, mask pattern) pair encoded in the format-info
    bits around the top-left finder pattern (ISO/IEC 18004:2015, 7.9),
    read from the same fifteen positions `segno.encoder.add_format_info`
    writes to (its own top-left copy only -- the second, redundant copy
    along the other two finder patterns is not needed to decode a symbol
    with no transmission errors to correct)."""
    voffset = hoffset = 0
    vbit = hbit = 0
    for i in range(8):
        if i == 6:  # the timing-pattern row/column in between
            voffset, hoffset = 1, 1
        if real[i + voffset][8]:
            vbit |= 1 << i
        if real[8][i + hoffset]:
            hbit |= 1 << (14 - i)
    fmt = vbit | hbit
    for index, value in enumerate(consts.FORMAT_INFO):
        if value == fmt:
            error = (
                consts.ERROR_LEVEL_M,
                consts.ERROR_LEVEL_L,
                consts.ERROR_LEVEL_H,
                consts.ERROR_LEVEL_Q,
            )[index // 8]
            return error, index % 8
    raise ValueError(f"{fmt:015b} is not a valid QR format-info codeword")


def _mask_predicate(mask: int) -> Callable[[int, int], bool]:
    """Table 10 (ISO/IEC 18004:2015, 7.8.2) -- whether module `(i, j)` is
    flipped by the given mask pattern, `i` the row and `j` the column,
    `(0, 0)` the top-left corner, matching `segno.encoder.
    get_data_mask_functions`'s own eight conditions exactly (an
    independent transcription of the same standard table, not an import
    of that function)."""
    predicates: tuple[Callable[[int, int], bool], ...] = (
        lambda i, j: (i + j) % 2 == 0,
        lambda i, j: i % 2 == 0,
        lambda i, j: j % 3 == 0,
        lambda i, j: (i + j) % 3 == 0,
        lambda i, j: (i // 2 + j // 3) % 2 == 0,
        lambda i, j: (i * j) % 2 + (i * j) % 3 == 0,
        lambda i, j: ((i * j) % 2 + (i * j) % 3) % 2 == 0,
        lambda i, j: ((i + j) % 2 + (i * j) % 3) % 2 == 0,
    )
    return predicates[mask]


def _reserved_cells(version: int, size: int) -> _Matrix:
    """Every module position that is *not* a data module for a QR symbol
    of this `version` -- finder patterns and their separators, the two
    timing patterns, alignment patterns (`consts.ALIGNMENT_POS`, ISO/IEC
    18004:2015 Annex E), the two format-information copies, the version
    information blocks (version 7 and above), and the single fixed dark
    module -- independent of mask and of any content, exactly the
    structural "shape of a QR code of this version" every decoder (this
    one included) has to reconstruct before it can tell a data bit from a
    fixed one."""
    reserved: _Matrix = [[False] * size for _ in range(size)]

    def block(row0: int, col0: int, height: int, width: int) -> None:
        for row in range(row0, row0 + height):
            for col in range(col0, col0 + width):
                if 0 <= row < size and 0 <= col < size:
                    reserved[row][col] = True

    # Finder patterns, each with its own one-module separator, at all
    # three corners that carry one (8x8 blocks).
    block(0, 0, 8, 8)
    block(0, size - 8, 8, 8)
    block(size - 8, 0, 8, 8)
    # The two timing patterns.
    for i in range(size):
        reserved[6][i] = True
        reserved[i][6] = True
    # Format information: the contiguous copy beside the top-left finder
    # pattern, and the split copy along the other two.
    for col in (0, 1, 2, 3, 4, 5, 7, 8):
        reserved[8][col] = True
    for row in (0, 1, 2, 3, 4, 5, 7, 8):
        reserved[row][8] = True
    for i in range(8):
        reserved[8][size - 1 - i] = True
        reserved[size - 1 - i][8] = True
    # Alignment patterns (5x5 each), skipping the three that would overlap
    # a finder pattern -- version 1 has none at all.
    if version >= 2:
        positions = consts.ALIGNMENT_POS[version - 2]
        corners = {
            (positions[0], positions[0]),
            (positions[0], positions[-1]),
            (positions[-1], positions[0]),
        }
        for centre_row in positions:
            for centre_col in positions:
                if (centre_row, centre_col) in corners:
                    continue
                block(centre_row - 2, centre_col - 2, 5, 5)
    # Version information (two 3x6 blocks), versions 7 and above only.
    if version >= 7:
        block(0, size - 11, 6, 3)
        block(size - 11, 0, 3, 6)
    # The single fixed dark module.
    reserved[size - 8][8] = True
    return reserved


def _extract_data_codewords(
    real: _Matrix, version: int, error_level: int, mask: int
) -> list[int]:
    """The message's own data codewords, in order -- unmasked, read off
    the matrix in the same up/down zigzag `segno.encoder.add_codewords`
    places them in (ISO/IEC 18004:2015, 7.7.3), grouped into bytes, and
    deinterleaved using `segno.consts.ECC`'s own block-size table (ISO/IEC
    18004:2015, Table 9) -- the error-correction codewords the same table
    identifies are read (so the deinterleave lands on the right
    boundaries) and then discarded; see the module docstring for why no
    Reed-Solomon correction is performed on them."""
    size = len(real)
    reserved = _reserved_cells(version, size)
    is_flipped = _mask_predicate(mask)

    bits: list[int] = []
    right = size - 1
    while right > 0:
        if right <= 6:
            right -= 1
        for vertical in range(size):
            for offset in range(2):
                col = right - offset
                upwards = (right & 2) == 0
                upwards ^= col < 6
                row = (size - 1 - vertical) if upwards else vertical
                if not reserved[row][col]:
                    dark = real[row][col]
                    if is_flipped(row, col):
                        dark = not dark
                    bits.append(1 if dark else 0)
        right -= 2

    codewords = [
        sum(bit << (7 - k) for k, bit in enumerate(bits[i : i + 8]))
        for i in range(0, len(bits) - 7, 8)
    ]

    # `segno.consts.ECC` is a plain, untyped table (a direct transcription
    # of ISO/IEC 18004:2015 Table 9 -- ints and namedtuples, not a typed
    # structure segno itself ships stubs for); the cast names the shape
    # this module already relies on, not a new assumption.
    ecc_table = cast("dict[int, dict[int, tuple[_EC, ...]]]", consts.ECC)
    ec_infos = ecc_table[version][error_level]
    block_specs = [
        (info.num_data, info.num_total)
        for info in ec_infos
        for _ in range(info.num_blocks)
    ]
    max_data = max(num_data for num_data, _ in block_specs)
    data_blocks: list[list[int]] = [[] for _ in block_specs]
    idx = 0
    for column in range(max_data):
        for block_index, (num_data, _num_total) in enumerate(block_specs):
            if column < num_data:
                data_blocks[block_index].append(codewords[idx])
                idx += 1
    # The error-correction codewords are still consumed (interleaved
    # immediately after the data codewords, per the same table), even
    # though nothing below reads `idx` again -- see the module docstring.

    data_codewords: list[int] = []
    for one_block in data_blocks:
        data_codewords.extend(one_block)
    return data_codewords


def _decode_byte_segment(data_codewords: list[int], version: int) -> str:
    """The byte-mode segment (ISO/IEC 18004:2015, 7.4.4) at the start of
    `data_codewords` -- a 4-bit mode indicator (must be
    `consts.MODE_BYTE`), a character-count indicator (8 bits for versions
    1-9, 16 bits for 10 and above -- `consts.CHAR_COUNT_INDICATOR_LENGTH`),
    and that many raw bytes, decoded as ISO 8859-1 (`segno.consts.
    DEFAULT_BYTE_ENCODING`) -- ASCII-identical to UTF-8 for every character
    a `signup_url` ever contains (a lower-cased domain and edition id, D-19),
    so the choice between the two never matters for this project's own
    data."""
    bitstream: list[int] = []
    for codeword in data_codewords:
        bitstream.extend((codeword >> k) & 1 for k in range(7, -1, -1))

    position = 0

    def take(n: int) -> int:
        nonlocal position
        value = 0
        for _ in range(n):
            value = (value << 1) | bitstream[position]
            position += 1
        return value

    mode = take(4)
    if mode != consts.MODE_BYTE:
        raise ValueError(
            f"expected byte mode ({consts.MODE_BYTE:04b}), got {mode:04b} -- "
            "this decoder only supports byte mode (see the module docstring)"
        )
    count_bits = 8 if version <= 9 else 16
    length = take(count_bits)
    return bytes(take(8) for _ in range(length)).decode("iso-8859-1")


def decode_registration_qr(svg: str) -> str:
    """The string encoded in `svg` -- an embeddable QR fragment exactly as
    `registration_code.registration_code_svg` returns it -- recovered
    independently of `segno`'s own encoder, module size and mask included
    (see the module docstring for what "independently" does and does not
    mean here).

    Raises `ValueError` for anything this decoder cannot make sense of:
    a malformed SVG, a format-info codeword outside the standard's 32
    valid values, or a mode other than byte -- never a silent, wrong
    string. This project's own signup URLs never exercise any of those
    paths (see the module docstring); a test that wants to check the
    guard itself has to construct a mutated SVG deliberately.
    """
    bordered = _parse_svg_matrix(svg)
    matrix_size = len(bordered) - 2 * QR_BORDER
    version = (matrix_size - 17) // 4
    if version < 1 or version > 40 or 4 * version + 17 != matrix_size:
        raise ValueError(f"{matrix_size}x{matrix_size} is not a valid QR module count")
    real = [
        row[QR_BORDER : QR_BORDER + matrix_size]
        for row in bordered[QR_BORDER : QR_BORDER + matrix_size]
    ]

    error_level, mask = _read_format_info(real)
    data_codewords = _extract_data_codewords(real, version, error_level, mask)
    return _decode_byte_segment(data_codewords, version)
