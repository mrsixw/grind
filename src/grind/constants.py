"""Project-wide constant definitions and data payloads.

App identity, update
and cache defaults, the colour palettes, and the holiday date tables all live
in this one file, so renaming the tool never turns into a hunt through six
modules. Nothing here imports from the rest of the package, so it is always
safe to import from anywhere.
"""

__all__ = [
    "APP_ITEMS",
    "APP_NAME",
    "BINARY_NAME",
    "BIRTHDAY",
    "BIRTHDAY_NAME",
    "CAKE_RECIPES",
    "CHRISTMAS",
    "COFFEE_RECIPES",
    "DEFAULT_CACHE_TTL",
    "DIWALI",
    "EID_AL_ADHA",
    "EID_AL_FITR",
    "ENTRY_POINT_GROUP",
    "ENVVAR_PREFIX",
    "HANUKKAH_START",
    "HOLI_DATES",
    "HOLI_RAINBOW",
    "HTTP_TIMEOUT_SECONDS",
    "LOG_FILENAME",
    "MID_AUTUMN",
    "PASSOVER_START",
    "PASTRY_RECIPES",
    "PRIDE_RAINBOW",
    "RELEASE_ASSET_URL",
    "ROSH_HASHANAH",
    "SEASONAL_PALETTES",
    "SUKKOT_START",
    "TTL_SUFFIX_MAP",
    "UPDATE_CHECK_REPO",
    "USER_AGENT",
    "VERSION_CACHE_FILENAME",
    "VERSION_CACHE_TTL_SECONDS",
]

# ── App identity ───────────────────────────────────────────────────────────

#: Import name of the package, and the directory name used under the XDG dirs.
APP_NAME = "grind"
#: The installed executable, as the user types it and as Click reports it.
BINARY_NAME = "grind"
#: Prefix for environment-variable overrides, e.g. ``GRIND_NO_COLOUR``.
ENVVAR_PREFIX = "GRIND"

LOG_FILENAME = f"{APP_NAME}.log"

# ── Update checks ──────────────────────────────────────────────────────────

UPDATE_CHECK_REPO = "mrsixw/grind"
RELEASE_ASSET_URL = (
    f"https://github.com/{UPDATE_CHECK_REPO}/releases/latest/download/{BINARY_NAME}"
)
VERSION_CACHE_FILENAME = "latest_version.json"
VERSION_CACHE_TTL_SECONDS = 86400  # 24 hours

# ── Providers ──────────────────────────────────────────────────────────────

#: Entry-point group third-party provider plugins register under.
ENTRY_POINT_GROUP = "grind.providers"
#: Per-request timeout for every provider built on HttpProvider.
HTTP_TIMEOUT_SECONDS = 30
USER_AGENT = f"{BINARY_NAME} (+https://github.com/{UPDATE_CHECK_REPO})"

# ── Cache configuration ────────────────────────────────────────────────────

DEFAULT_CACHE_TTL = 300
TTL_SUFFIX_MAP = {"s": 1, "m": 60, "h": 3600}

# ── UI & theming ───────────────────────────────────────────────────────────

SEASONAL_PALETTES = {
    "green": "\033[32m",
    "purple": "\033[38;5;141m",
    "yellow": "\033[38;5;226m",
    "orange": "\033[38;5;208m",
    "red": "\033[31m",
    "pink": "\033[38;5;218m",
    "lny": "\033[38;5;196m",
    "blue": "\033[38;5;75m",
    "spring_green": "\033[38;5;120m",
    "gold": "\033[38;5;220m",
}

# Pride Month 🏳️‍🌈 rainbow: one colour per row, cycling by index.
PRIDE_RAINBOW = [
    "\033[31m",  # red
    "\033[38;5;208m",  # orange
    "\033[38;5;226m",  # yellow
    "\033[32m",  # green
    "\033[38;5;63m",  # blue
    "\033[38;5;141m",  # purple
]

# Holi rainbow: a burst of festival colours 🎨
HOLI_RAINBOW = [
    "\033[38;5;218m",  # pink
    "\033[38;5;226m",  # yellow
    "\033[32m",  # green
    "\033[38;5;208m",  # orange
    "\033[38;5;141m",  # purple
    "\033[38;5;75m",  # blue
]

# Spinner items — coffee-shop counter themed ☕🥐🍩
APP_ITEMS = ["☕", "🫘", "🥐", "🍩", "🧋", "🫖", "🥛", "🍪", "🧁", "🥯"]

# ── Holiday date tables (2024–2045) ────────────────────────────────────────
#
# Lunar, lunisolar, and observation-based holidays have no closed-form
# Gregorian formula, so they are tabulated rather than computed. Easter and
# Lunar New Year are the exceptions and are calculated in ``ui.py``.

DIWALI: dict[int, tuple[int, int]] = {
    2024: (11, 1),
    2025: (10, 20),
    2026: (11, 8),
    2027: (10, 29),
    2028: (10, 17),
    2029: (11, 5),
    2030: (10, 26),
    2031: (11, 14),
    2032: (11, 2),
    2033: (10, 22),
    2034: (11, 11),
    2035: (11, 1),
    2036: (10, 19),
    2037: (11, 7),
    2038: (10, 28),
    2039: (10, 18),
    2040: (11, 4),
    2041: (10, 24),
    2042: (11, 13),
    2043: (11, 3),
    2044: (10, 21),
    2045: (11, 9),
}
EID_AL_ADHA: dict[int, tuple[int, int]] = {
    2024: (6, 16),
    2025: (6, 6),
    2026: (5, 26),
    2027: (5, 16),
    2028: (5, 4),
    2029: (4, 24),
    2030: (4, 13),
    2031: (4, 2),
    2032: (3, 22),
    2033: (3, 11),
    2034: (3, 1),
    2035: (2, 18),
    2036: (2, 7),
    2037: (1, 26),
    2038: (1, 16),
    2039: (12, 26),
    2040: (12, 14),
    2041: (12, 4),
    2042: (11, 23),
    2043: (11, 13),
    2044: (11, 1),
    2045: (10, 22),
}
EID_AL_FITR: dict[int, tuple[int, int]] = {
    2024: (4, 10),
    2025: (3, 30),
    2026: (3, 20),
    2027: (3, 9),
    2028: (2, 26),
    2029: (2, 15),
    2030: (2, 4),
    2031: (1, 24),
    2032: (1, 13),
    2033: (1, 2),
    2034: (12, 11),
    2035: (11, 30),
    2036: (11, 19),
    2037: (11, 8),
    2038: (10, 28),
    2039: (10, 17),
    2040: (10, 6),
    2041: (9, 25),
    2042: (9, 14),
    2043: (9, 4),
    2044: (8, 23),
    2045: (8, 12),
}
HANUKKAH_START: dict[int, tuple[int, int]] = {
    2024: (12, 25),
    2025: (12, 14),
    2026: (12, 4),
    2027: (12, 24),
    2028: (12, 12),
    2029: (12, 1),
    2030: (12, 20),
    2031: (12, 9),
    2032: (11, 27),
    2033: (12, 16),
    2034: (12, 5),
    2035: (12, 25),
    2036: (12, 13),
    2037: (12, 2),
    2038: (12, 22),
    2039: (12, 11),
    2040: (11, 29),
    2041: (12, 18),
    2042: (12, 8),
    2043: (12, 27),
    2044: (12, 15),
    2045: (12, 5),
}
HOLI_DATES: dict[int, tuple[int, int]] = {
    2024: (3, 25),
    2025: (3, 14),
    2026: (3, 3),
    2027: (3, 22),
    2028: (3, 11),
    2029: (3, 1),
    2030: (3, 20),
    2031: (3, 10),
    2032: (2, 27),
    2033: (3, 17),
    2034: (3, 7),
    2035: (3, 26),
    2036: (3, 14),
    2037: (3, 4),
    2038: (3, 23),
    2039: (3, 13),
    2040: (3, 1),
    2041: (3, 19),
    2042: (3, 8),
    2043: (3, 28),
    2044: (3, 16),
    2045: (3, 5),
}
MID_AUTUMN: dict[int, tuple[int, int]] = {
    2024: (9, 17),
    2025: (10, 6),
    2026: (9, 25),
    2027: (9, 15),
    2028: (10, 3),
    2029: (9, 22),
    2030: (9, 12),
    2031: (10, 1),
    2032: (9, 19),
    2033: (9, 8),
    2034: (9, 27),
    2035: (9, 16),
    2036: (10, 4),
    2037: (9, 24),
    2038: (9, 13),
    2039: (10, 2),
    2040: (9, 20),
    2041: (9, 9),
    2042: (9, 28),
    2043: (9, 17),
    2044: (10, 5),
    2045: (9, 24),
}
PASSOVER_START: dict[int, tuple[int, int]] = {
    2024: (4, 22),
    2025: (4, 12),
    2026: (4, 1),
    2027: (4, 21),
    2028: (4, 10),
    2029: (3, 29),
    2030: (4, 17),
    2031: (4, 7),
    2032: (3, 27),
    2033: (4, 14),
    2034: (4, 3),
    2035: (4, 23),
    2036: (4, 11),
    2037: (4, 1),
    2038: (4, 20),
    2039: (4, 9),
    2040: (3, 29),
    2041: (4, 16),
    2042: (4, 6),
    2043: (4, 25),
    2044: (4, 13),
    2045: (4, 3),
}
ROSH_HASHANAH: dict[int, tuple[int, int]] = {
    2024: (10, 2),
    2025: (9, 22),
    2026: (9, 11),
    2027: (10, 1),
    2028: (9, 20),
    2029: (9, 9),
    2030: (9, 27),
    2031: (9, 18),
    2032: (9, 5),
    2033: (9, 24),
    2034: (9, 14),
    2035: (10, 3),
    2036: (9, 21),
    2037: (9, 10),
    2038: (9, 29),
    2039: (9, 19),
    2040: (9, 7),
    2041: (9, 25),
    2042: (9, 15),
    2043: (10, 4),
    2044: (9, 22),
    2045: (9, 12),
}
SUKKOT_START: dict[int, tuple[int, int]] = {
    2024: (10, 16),
    2025: (10, 6),
    2026: (9, 25),
    2027: (10, 15),
    2028: (10, 4),
    2029: (9, 23),
    2030: (10, 12),
    2031: (10, 1),
    2032: (9, 19),
    2033: (10, 8),
    2034: (9, 28),
    2035: (10, 17),
    2036: (10, 4),
    2037: (9, 24),
    2038: (10, 13),
    2039: (10, 3),
    2040: (9, 21),
    2041: (10, 10),
    2042: (9, 30),
    2043: (10, 18),
    2044: (10, 5),
    2045: (9, 25),
}


# ── Easter eggs ────────────────────────────────────────────────────────────

#: The birthday that triggers the once-a-year cake surprise, as (month, day).
#: Scaffolding your own CLI from this template? Change it to your own, or set
#: it to None to switch the surprise off entirely.
BIRTHDAY: tuple[int, int] | None = (1, 8)
#: Whose birthday it is, as it appears in the greeting.
BIRTHDAY_NAME = "Steve"
#: The coffee surprise's fixed date.
CHRISTMAS: tuple[int, int] = (12, 25)

# Real techniques, credited. Each carries a "source" so the easter egg points
# at the person who developed it rather than passing it off as ours.
COFFEE_RECIPES = [
    {
        "title": "The Ultimate V60 Technique",
        "style": "Pour-over (Clean, Sweet, Tea-like Clarity)",
        "dose": "30g coffee to 500g water, just off the boil.",
        "grind": "Medium-fine, a little finer than you would for a drip machine.",
        "brew": (
            "Rinse the paper. Bloom with 60g water and swirl until no dry "
            "pockets remain, then wait 45 seconds. Pour to 300g by 1:15, and "
            "to 500g by 1:45. Stir gently once each way, give the brewer a "
            "final swirl, and let it draw down by about 3:30."
        ),
        "tip": (
            "The swirl after the last pour flattens the bed, which is what "
            "keeps the water from channelling down one side."
        ),
        "source": "James Hoffmann",
        "source_url": "https://www.youtube.com/watch?v=AI4ynXzkSQo",
    },
    {
        "title": "The Ultimate French Press Technique",
        "style": "Immersion (Full Body, No Sludge)",
        "dose": "30g coffee to 500g water, just off the boil.",
        "grind": "Medium, not the coarse grind the box tells you to use.",
        "brew": (
            "Pour all the water over the grounds and leave it alone for 4 "
            "minutes. Stir the crust, scoop off the foam and floating bits, "
            "then wait another 5 minutes or more. Rest the plunger on the "
            "surface without pressing, and pour gently."
        ),
        "tip": (
            "Patience is the whole recipe: the long second wait lets the "
            "fines settle, so they stay in the pot and out of the cup."
        ),
        "source": "James Hoffmann",
        "source_url": "https://www.youtube.com/watch?v=st571DYYTR8",
    },
    {
        "title": "The Ultimate AeroPress Technique",
        "style": "Immersion and Pressure (Quick, Forgiving, Travel-proof)",
        "dose": "11g coffee to 200g water, boiling for light roasts.",
        "grind": "Fine, towards the finer end of filter.",
        "brew": (
            "Brewer upright on the cup, no need to rinse the paper. Add the "
            "coffee, pour all the water, and seat the plunger to stop the "
            "drip. Wait 2 minutes, swirl gently, wait 30 seconds more, then "
            "press slowly all the way through."
        ),
        "tip": (
            "Seating the plunger creates a vacuum that holds the water in, "
            "so there is no need to brew it upside down."
        ),
        "source": "James Hoffmann",
        "source_url": "https://www.youtube.com/watch?v=j6VlT_jUVPc",
    },
    {
        "title": "The Ultimate Moka Pot Technique",
        "style": "Stovetop (Strong, Rich, Short)",
        "dose": "Fill the basket level without tamping; water to the valve.",
        "grind": "Fine, but coarser than espresso.",
        "brew": (
            "Fill the base with water straight from the kettle so the "
            "coffee spends less time cooking. Brew over a low heat with the "
            "lid up, and take it off the moment it starts to sputter."
        ),
        "tip": (
            "Run the base under a cold tap as soon as it comes off the heat. "
            "That stops the brew before the bitter last drops come through."
        ),
        "source": "James Hoffmann",
        "source_url": "https://www.youtube.com/watch?v=BfDLoIvb0w4",
    },
]

# Something to have with the coffee. The method is the classic laminated
# dough, described in general terms; the credited recipes have the exact
# quantities and timings.
PASTRY_RECIPES = [
    {
        "title": "Classic Butter Croissants",
        "style": "Laminated Yeast Dough (Flaky Shell, Honeycomb Crumb)",
        "dough": (
            "A soft, enriched yeast dough of flour, milk, sugar, salt and a "
            "little butter. Mix until just combined and chill it rather than "
            "kneading: the rolling and folding develop it instead."
        ),
        "butter": (
            "Cold unsalted butter beaten into a flat, pliable square, about "
            "half the dough's weight, and chilled until it bends without "
            "cracking."
        ),
        "shape": (
            "Lock the butter in the dough and give it three letter folds, "
            "chilling between each. Roll the dough out, cut long triangles, "
            "notch the base and roll them up loosely towards the tip, then "
            "curve the ends in."
        ),
        "bake": (
            "Proof somewhere warm but not hot until puffy and wobbly, brush "
            "with egg wash, and bake at about 400°F (200°C) until deep golden "
            "brown, 15-20 minutes."
        ),
        "tip": (
            "Keep everything cold. Butter that softens smears into the dough "
            "instead of staying a separate layer, and the layers are what "
            "make the flakes."
        ),
        "source": "King Arthur Baking",
        "source_url": "https://www.kingarthurbaking.com/recipes/bakers-croissants-recipe",
    },
    {
        "title": "Pain au Chocolat",
        "style": "Laminated Yeast Dough (Two Seams of Dark Chocolate)",
        "dough": (
            "The same yeasted, butter-laminated dough as a croissant: an "
            "enriched dough chilled overnight, so the gluten relaxes before "
            "the rolling starts."
        ),
        "butter": (
            "A cold, flat butter block locked into the dough and folded in "
            "with letter folds, chilling between each so the layers stay "
            "distinct."
        ),
        "shape": (
            "Roll the dough out and cut it into rectangles. Lay a baton of "
            "dark chocolate across one end, roll once, add a second baton and "
            "roll again, finishing seam-side down."
        ),
        "bake": (
            "Proof until puffy, brush with egg wash, and bake at about 400°F "
            "(200°C) until deep golden brown and crisp at the edges."
        ),
        "tip": (
            "Use proper baking batons, which hold their shape in the oven. A "
            "broken-up chocolate bar melts and leaks out of the layers."
        ),
        "source": "King Arthur Baking",
        "source_url": "https://www.kingarthurbaking.com/recipes/pain-au-chocolat-recipe",
    },
]

# Cake is cake, and it goes with coffee — shared verbatim with breakfast.
CAKE_RECIPES = [
    {
        "title": "Ultimate Rich & Fudgy Chocolate Cake",
        "style": "Double Chocolate Layer Cake (Rich, Moist & Fudgy)",
        "batter": (
            "250g plain flour, 300g caster sugar, 75g cocoa powder, 1.5 tsp "
            "baking powder, 1.5 tsp bicarb, 2 eggs, 250ml milk, 125ml oil, "
            "250ml freshly brewed hot coffee. Whisk dry, add wet, pour thin "
            "batter into tins."
        ),
        "frosting": (
            "200g dark chocolate melted with 200ml double cream and 50g "
            "butter into a glossy ganache."
        ),
        "bake": (
            "350°F (180°C) in two 8-inch greased sandwich tins for 25-30 min "
            "until a skewer comes out clean."
        ),
        "tip": (
            "Hot coffee blooms the cocoa powder for an intensely deep chocolate "
            "flavor without tasting like coffee!"
        ),
    },
    {
        "title": "Classic British Victoria Sponge Cake",
        "style": "Traditional Layer Sponge (Light & Fluffy)",
        "batter": (
            "200g softened butter, 200g caster sugar, 4 eggs, 200g self-raising "
            "flour, 1 tsp vanilla extract, 1-2 tbsp milk. Beat butter & sugar "
            "pale, beat in eggs, fold flour gently."
        ),
        "frosting": (
            "Generous layer of raspberry jam and freshly whipped double cream "
            "with vanilla and a dust of icing sugar."
        ),
        "bake": (
            "375°F (190°C) in two 8-inch tins for 20 min until golden and springy."
        ),
        "tip": (
            "Don't open the oven door for the first 15 minutes to keep the sponge "
            "from sinking in the centre."
        ),
    },
    {
        "title": "Spiced Carrot & Walnut Cake",
        "style": "Moist Spiced Cake (Silky Cream Cheese Frosting)",
        "batter": (
            "250g grated carrots, 250g self-raising flour, 2 tsp cinnamon, "
            "200g light brown sugar, 150ml vegetable oil, 4 eggs, 75g chopped "
            "walnuts. Whisk oil, sugar, eggs, fold flour, carrots & nuts."
        ),
        "frosting": (
            "100g softened butter, 200g cream cheese, 300g icing sugar, 1 tsp "
            "vanilla extract beaten smooth."
        ),
        "bake": (
            "350°F (180°C) in an 8-inch round cake tin for 45-50 min until "
            "golden and firm."
        ),
        "tip": (
            "Ensure the cake is completely cooled before frosting or the cream "
            "cheese icing will melt!"
        ),
    },
]
