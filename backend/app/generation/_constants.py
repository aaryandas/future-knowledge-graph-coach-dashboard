from typing import Final

SECTION_SPLITS: Final = (
    ("warm-up", 0.15),
    ("main", 0.70),
    ("cool-down", 0.15),
)
SECTION_ORDER: Final = ("warm-up", "main", "cool-down")
MINIMUM_WINDOW_MINUTES: Final = 20

WARM_UP_PATTERNS: Final = frozenset({"mobility - dynamic", "car"})
COOL_DOWN_PATTERNS: Final = frozenset({"mobility - static", "massage", "regen", "yoga"})

FOCUS_PATTERN_PREFIXES: Final = (
    ("upper-body", ("upper ", "arms ", "shoulders ")),
    ("lower-body", ("lower ", "legs ")),
    ("core", ("core ",)),
    ("conditioning", ("cardio", "total body")),
    ("mobility", ("mobility ",)),
)
FOCUS_PATTERNS: Final = (
    ("mobility", frozenset({"balance", "car", "quadruped", "regen", "yoga"})),
)

GOAL_MATCH_WEIGHT: Final = 1
COVERAGE_GAIN_WEIGHT: Final = 1
PRIORITY_TIER_WEIGHT: Final = 1
CAUTION_PENALTY: Final = 1
DISLIKE_PENALTY: Final = 1

WARM_UP_SETS: Final = 1
WARM_UP_REPS: Final = 10
WARM_UP_REST_MINUTES: Final = 0.25
WARM_UP_HOLD_MINUTES: Final = 1.0

MAIN_SETS: Final = 3
MAIN_REDUCED_SETS: Final = 2
MAIN_REPS: Final = 8
MAIN_REST_MINUTES: Final = 1.0
MAIN_HOLD_MINUTES: Final = 3.0

COOL_DOWN_SETS: Final = 1
COOL_DOWN_REST_MINUTES: Final = 0.25
COOL_DOWN_HOLD_MINUTES: Final = 1.0

PER_SIDE_COUNT: Final = 2
SINGLE_SIDE_COUNT: Final = 1
REST_INTERVAL_OFFSET: Final = 1
MINIMUM_SECTION_ENTRIES: Final = 1
ZERO_SCORE: Final = 0
ZERO_MINUTES: Final = 0.0
TIME_DECIMAL_PLACES: Final = 2
TIME_COMPARISON_TOLERANCE: Final = 1e-9
