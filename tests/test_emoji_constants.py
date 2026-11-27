"""Every emoji grind prints is a named constant in ``constants.py``.

An emoji written inline in a message is easy to miss when the set changes,
and two messages meaning the same thing drift apart. This walks the source
for string literals holding one. Docstrings are exempt: Click prints the
group's docstring as ``--help``, which cannot name a constant.
"""

import ast
import unicodedata
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "src" / "grind"
#: Where the emoji are defined, so the one module allowed to spell them out.
HOME = PACKAGE / "constants.py"
#: Asks for emoji presentation of the character before it (ℹ️, ▶️, ⚠️).
VARIATION_SELECTOR = "\ufe0f"
#: The first block holding emoji in their own right (Miscellaneous Technical:
#: ⌛, ⏳, ⏰). Arrows such as the → in the update notice sit below it.
FIRST_EMOJI_CODEPOINT = 0x2300
#: Symbols at or above it that are drawing, not emoji: box drawing and block
#: elements (show's rule and gutter), and Braille (spinners).
NOT_EMOJI = (range(0x2500, 0x25A0), range(0x2800, 0x2900))
#: The Unicode category emoji are in: Symbol, other.
EMOJI_CATEGORY = "So"


def _is_emoji(char: str) -> bool:
    point = ord(char)
    return (
        point >= FIRST_EMOJI_CODEPOINT
        and unicodedata.category(char) == EMOJI_CATEGORY
        and not any(point in block for block in NOT_EMOJI)
    )


def _has_emoji(text: str) -> bool:
    """Whether *text* holds an emoji. A lone variation selector, as in
    ``ui.with_emoji``'s check for one, has nothing to present and is not."""
    return VARIATION_SELECTOR in text.lstrip(VARIATION_SELECTOR) or any(
        _is_emoji(char) for char in text
    )


def _docstrings(tree: ast.Module) -> set[int]:
    """The ids of the string nodes that are docstrings."""
    owners = [tree] + [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    ]
    return {
        id(owner.body[0].value)
        for owner in owners
        if owner.body
        and isinstance(owner.body[0], ast.Expr)
        and isinstance(owner.body[0].value, ast.Constant)
    }


def _inline_emoji(path: Path) -> list[str]:
    return _inline_emoji_at(path, PACKAGE)


def _inline_emoji_at(path: Path, root: Path) -> list[str]:
    """Each string literal in *path* holding an emoji, as ``file:line: text``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _docstrings(tree)
    return [
        f"{path.relative_to(root)}:{node.lineno}: {node.value!r}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skip
        and _has_emoji(node.value)
    ]


@pytest.mark.parametrize(
    "path",
    sorted(p for p in PACKAGE.rglob("*.py") if p != HOME),
    ids=lambda p: str(p.relative_to(PACKAGE)),
)
def test_no_emoji_is_written_inline(path):
    assert _inline_emoji(path) == []


@pytest.mark.parametrize(
    "literal",
    ['"⚠️ careful"', '"ℹ️"', '"⏳"', '"▶️"', 'f"{x} ☕"', '"🐛"'],
)
def test_the_check_finds_an_inline_emoji(tmp_path, literal):
    path = tmp_path / "inline.py"
    path.write_text(f"x = 1\nmessage = {literal}\n", encoding="utf-8")
    assert len(_inline_emoji_at(path, tmp_path)) == 1


@pytest.mark.parametrize(
    "literal",
    ['"─" * 3', '"  │ "', '"⠋"', '"v1 → v2"', '"—"', '"\\ufe0f"'],
)
def test_the_check_allows_drawing_and_punctuation(tmp_path, literal):
    path = tmp_path / "drawing.py"
    path.write_text(f"message = {literal}\n", encoding="utf-8")
    assert _inline_emoji_at(path, tmp_path) == []


def test_the_check_allows_docstrings(tmp_path):
    path = tmp_path / "documented.py"
    path.write_text(
        '"""☕ module."""\n\n'
        'def f():\n    """⚠️ function."""\n\n'
        'class C:\n    """🐛 class."""\n',
        encoding="utf-8",
    )
    assert _inline_emoji_at(path, tmp_path) == []
