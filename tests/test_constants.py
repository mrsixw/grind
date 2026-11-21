"""Tests for the centralised constants in grind.constants."""

import grind.constants as constants


def test_app_identity():
    assert constants.APP_NAME == "grind"
    assert constants.BINARY_NAME == "grind"
    assert constants.ENVVAR_PREFIX == "GRIND"
    assert constants.LOG_FILENAME == "grind.log"


def test_update_constants():
    assert constants.UPDATE_CHECK_REPO == "mrsixw/grind"
    assert constants.RELEASE_ASSET_URL.startswith("https://github.com/")
    assert constants.RELEASE_ASSET_URL.endswith(f"/download/{constants.BINARY_NAME}")
    assert constants.VERSION_CACHE_FILENAME == "latest_version.json"
    assert constants.VERSION_CACHE_TTL_SECONDS == 86400


def test_cache_constants():
    assert constants.DEFAULT_CACHE_TTL == 300
    assert constants.TTL_SUFFIX_MAP == {"s": 1, "m": 60, "h": 3600}


def test_ui_constants():
    assert len(constants.APP_ITEMS) > 0
    assert "purple" in constants.SEASONAL_PALETTES
    assert len(constants.PRIDE_RAINBOW) == 6
    assert len(constants.HOLI_RAINBOW) == 6


def test_holiday_tables_cover_the_current_decade():
    tables = [
        constants.DIWALI,
        constants.EID_AL_ADHA,
        constants.EID_AL_FITR,
        constants.HANUKKAH_START,
        constants.HOLI_DATES,
        constants.MID_AUTUMN,
        constants.PASSOVER_START,
        constants.ROSH_HASHANAH,
        constants.SUKKOT_START,
    ]
    for table in tables:
        assert set(range(2024, 2046)) <= set(table)


def test_holiday_table_entries_are_valid_dates():
    import datetime

    for table in (constants.DIWALI, constants.HOLI_DATES, constants.ROSH_HASHANAH):
        for year, (month, day) in table.items():
            datetime.date(year, month, day)  # raises ValueError if bogus


def test_pastry_recipes_are_croissant_and_pain_au_chocolat():
    titles = [r["title"] for r in constants.PASTRY_RECIPES]
    assert any("Croissant" in t for t in titles)
    assert any("Pain au Chocolat" in t for t in titles)
    for recipe in constants.PASTRY_RECIPES:
        assert recipe["source"], f"{recipe['title']} must credit its source"
        assert recipe["source_url"].startswith(
            "https://"
        ), f"{recipe['title']} must link to its source"


def test_coffee_recipes():
    assert len(constants.COFFEE_RECIPES) >= 4
    titles = [r["title"] for r in constants.COFFEE_RECIPES]
    assert len(titles) == len(set(titles))
    for recipe in constants.COFFEE_RECIPES:
        assert recipe["source"], f"{recipe['title']} must credit its source"
        assert recipe["source_url"].startswith(
            "https://"
        ), f"{recipe['title']} must link to its source"


def test_cake_recipes():
    assert len(constants.CAKE_RECIPES) >= 3
    titles = [r["title"] for r in constants.CAKE_RECIPES]
    assert len(titles) == len(set(titles))


def test_easter_egg_dates():
    # BIRTHDAY is intentionally overridable to None by a scaffolded CLI.
    assert constants.BIRTHDAY is None or len(constants.BIRTHDAY) == 2
    assert constants.CHRISTMAS == (12, 25)
    assert constants.BIRTHDAY_NAME
