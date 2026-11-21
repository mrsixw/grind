"""Settings.paint: which colour a piece of output actually gets."""

from freezegun import freeze_time

from grind.settings import Settings
from grind.ui import THEMES, get_theme

#: An ordinary day: no holiday on the western calendar.
ORDINARY_DAY = "2026-11-15"


def test_default_theme_is_coffee_coloured():
    # Mocha brown (256-colour 137) for the body of the output, caramel (173)
    # for accents — readable on both dark and light backgrounds.
    default = THEMES["default"]
    assert default.apply("x") == "\x1b[38;5;137mx\x1b[0m"
    assert default.apply("x", role="accent") == "\x1b[38;5;173mx\x1b[0m"


@freeze_time(ORDINARY_DAY)
def test_theme_colours_an_ordinary_day_even_with_seasonal_colours_on():
    settings = Settings(theme=get_theme("default"), seasonal_colours=True)
    assert settings.paint("x") == get_theme("default").apply("x")


@freeze_time("2026-12-25")
def test_a_holiday_still_wins_over_the_theme():
    settings = Settings(theme=get_theme("default"), seasonal_colours=True)
    assert settings.paint("x", index=0) == "\x1b[31mx\x1b[0m"


@freeze_time(ORDINARY_DAY)
def test_seasonal_calendar_off_uses_the_theme():
    settings = Settings(theme=get_theme("dark"), seasonal_calendar="off")
    assert settings.paint("x") == get_theme("dark").apply("x")


@freeze_time(ORDINARY_DAY)
def test_mono_theme_stays_plain_on_an_ordinary_day():
    assert Settings(theme=get_theme("mono")).paint("x") == "x"


def test_no_colour_beats_everything():
    assert Settings(colour=False).paint("x") == "x"
