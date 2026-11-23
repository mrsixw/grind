"""Resolved runtime settings shared across commands.

The CLI group callback builds one :class:`Settings` from flags + config file
and stores it on ``ctx.obj``; subcommands receive it via ``@click.pass_obj``.
Business modules can accept a ``Settings`` instead of a pile of loose
parameters.
"""

import time
from dataclasses import dataclass, field

from .constants import DEFAULT_TABLE_STYLE
from .ui import Theme, apply_seasonal_colour, seasonal_colour, with_emoji

__all__ = [
    "Settings",
]


@dataclass
class Settings:
    """Runtime settings resolved from CLI flags, config file, and defaults."""

    cfg: dict = field(default_factory=dict)
    config_path: str | None = None
    theme_name: str = "default"
    theme: Theme = field(default_factory=Theme)
    seasonal_colours: bool = True
    seasonal_calendar: str = "western"
    colour: bool = True
    #: A tabulate format name, one of ``constants.TABLE_STYLES``.
    table_style: str = DEFAULT_TABLE_STYLE
    #: Whether grind prints emoji. Off, every message reads the same without.
    emoji: bool = True
    cache_enabled: bool = False
    cache_ttl: int = 300
    update_check: bool = True
    update_summary: bool = False
    brew: bool = False
    cake: bool = False
    pastry: bool = False
    debug_summary: bool = False
    #: When this invocation started, for the debug summary's elapsed row.
    #: monotonic, so a clock adjustment mid-run cannot produce a negative time.
    started_at: float = field(default_factory=time.monotonic)

    def with_emoji(self, emoji: str, text: str) -> str:
        """Put *emoji* in front of *text*, unless ``--no-emoji`` is in effect."""
        return with_emoji(emoji, text, self.emoji)

    def paint(self, text: str, *, index: int = 0, role: str = "primary") -> str:
        """Colour *text* per the resolved colour/seasonal/theme settings.

        A seasonal colour wins on the days its calendar marks; every other
        day the theme applies, so the default theme is what most days look
        like. ``--no-colour`` disables both. *index* drives cycling palettes
        (Pride, Holi, the rainbow theme).
        """
        if not self.colour:
            return text
        if self.seasonal_colours and seasonal_colour(index, self.seasonal_calendar):
            return apply_seasonal_colour(text, index, calendar=self.seasonal_calendar)
        if role == "primary" and self.theme.cycle:
            return self.theme.apply_cycle(text, index)
        return self.theme.apply(text, role=role)
