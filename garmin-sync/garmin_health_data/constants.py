"""
This module defines the data types and API methods used in the Garmin Connect data
pipeline.

It provides a registry for easy access to Garmin data types and their associated
metadata.
"""

import re
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Dict, List, Optional


class APIMethodTimeParam(Enum):
    """
    Classification of how each data type is iterated by the extractor.

    The value drives :meth:`GarminExtractor._extract_data_by_type` dispatch: DAILY loops
    day-by-day, RANGE makes one call covering the full requested window, NO_DATE makes
    one call with no date parameters, and PER_ACTIVITY is fetched per activity ID
    (handled separately by :meth:`GarminExtractor.extract_fit_activities`, which
    iterates the ACTIVITIES_LIST output rather than calendar dates).
    """

    DAILY = "daily"  # Single date parameter: get_method(date_str).
    RANGE = "range"  # Date range parameters: get_method(start_str, end_str).
    NO_DATE = "no_date"  # No date parameters: get_method().
    MONTH = "month"  # (year, month) parameters: get_method(year, month).
    PER_ACTIVITY = "per_activity"  # Per-activity ID parameter: get_method(activity_id).


@dataclass
class GarminDataType:
    """
    Definition for a single Garmin Connect data type.

    Defines the API method, time parameter type, endpoint, and metadata for extracting a
    specific type of data from Garmin Connect.
    """

    name: str  # "SLEEP".
    api_method: str  # "get_sleep_data()".
    api_method_time_param: APIMethodTimeParam  # DAILY / RANGE / NO_DATE / PER_ACTIVITY.
    api_endpoint: str  # API endpoint string.
    description: str  # Description of the data type.
    emoji: str  # Emoji for pretty logging.


class GarminDataRegistry:
    """
    Registry for Garmin Connect data types with fast lookup and filtering.

    Provides O(1) lookups by name and efficient filtering by API method time parameters.
    """

    def __init__(self):
        self._data_types_by_name: Dict[str, GarminDataType] = {}
        self._data_types_by_time_param: Dict[
            APIMethodTimeParam, List[GarminDataType]
        ] = {
            APIMethodTimeParam.DAILY: [],
            APIMethodTimeParam.RANGE: [],
            APIMethodTimeParam.NO_DATE: [],
            APIMethodTimeParam.MONTH: [],
            APIMethodTimeParam.PER_ACTIVITY: [],
        }
        self._all_data_types: List[GarminDataType] = []

        # Register all data types on initialization.
        self._register_all_types()

    def _register_all_types(self):
        """
        Register all Garmin Connect data types.
        """
        data_types = [
            # Daily Data - Single date parameter: get_method(date_str)
            GarminDataType(
                "SLEEP",
                "get_sleep_data",
                APIMethodTimeParam.DAILY,
                "/wellness-service/wellness/dailySleepData/{display_name}"
                "?date={date}&nonSleepBufferMinutes=60",
                "Sleep stage duration, movement, levels, restless moments, "
                "heart rate (redundant with Heart Rate dataset), stress levels "
                "(redundant with Stress dataset), respiration (redundant with "
                "Respiration dataset), body battery (redundant with Stress dataset), "
                "HRV (redundant with Sleep HRV dataset), breathing disruptions, "
                "scores, current need, next need.",
                "💤",
            ),
            GarminDataType(
                "STRESS",
                "get_stress_data",
                APIMethodTimeParam.DAILY,
                "/wellness-service/wellness/dailyStress/{date}",
                "Stress level and body battery measurements (3 mins interval "
                "time-series).",
                "🔋",
            ),
            GarminDataType(
                "RESPIRATION",
                "get_respiration_data",
                APIMethodTimeParam.DAILY,
                "/wellness-service/wellness/daily/respiration/{date}",
                "Breathing rate readings (2 mins interval and 1 hour aggregates "
                "time-series) and aggregated statistics.",
                "🫁",
            ),
            GarminDataType(
                "HEART_RATE",
                "get_heart_rates",
                APIMethodTimeParam.DAILY,
                "/wellness-service/wellness/dailyHeartRate/{display_name}?date={date}",
                "Heart rate readings (2 mins interval time-series).",
                "💓",
            ),
            GarminDataType(
                "TRAINING_READINESS",
                "get_training_readiness",
                APIMethodTimeParam.DAILY,
                "/metrics-service/metrics/trainingreadiness/{date}",
                "Daily training readiness scores (generated multiple times a day) and "
                "associated features.",
                "🏋️",
            ),
            GarminDataType(
                "TRAINING_STATUS",
                "get_training_status",
                APIMethodTimeParam.DAILY,
                "/metrics-service/metrics/trainingstatus/aggregated/{date}",
                "VO2 max (generic and cycling) including heat and altitude "
                "acclimation, training load balance (low and high aerobic, anaerobic) "
                "with targets, acute/chronic workload ratio (ACWR), and feedback.",
                "📊",
            ),
            GarminDataType(
                "STEPS",
                "get_steps_data",
                APIMethodTimeParam.DAILY,
                "/wellness-service/wellness/dailySummaryChart/{display_name}"
                "?date={date}",
                "Number of steps and activity level (sedentary, sleeping, active, "
                "etc.) (15 mins interval time-series).",
                "👣",
            ),
            GarminDataType(
                "FLOORS",
                "get_floors",
                APIMethodTimeParam.DAILY,
                "/wellness-service/wellness/floorsChartData/daily/{date}",
                "Floors climbed and descended (15 mins interval time-series).",
                "🪜",
            ),
            GarminDataType(
                "INTENSITY_MINUTES",
                "get_intensity_minutes_data",
                APIMethodTimeParam.DAILY,
                "/wellness-service/wellness/daily/im/{date}",
                "Weekly and daily moderate/vigorous intensity minutes with "
                "time-series data and goal tracking.",
                "⚡",
            ),
            GarminDataType(
                "DAILY_EVENTS",
                "get_daily_events",
                APIMethodTimeParam.DAILY,
                "/wellness-service/wellness/dailyEvents?calendarDate={date}",
                "Auto-detected daily events (e.g. auto-detected activities) with "
                "per-event start/end timestamps.",
                "📅",
            ),
            GarminDataType(
                "BODY_BATTERY_EVENTS",
                "get_body_battery_events",
                APIMethodTimeParam.DAILY,
                "/wellness-service/wellness/bodyBattery/events/{date}",
                "Body battery events (sleep, stress, naps, activities) with start "
                "time, duration, and body-battery impact. Source for individual "
                "nap start/end times.",
                "😴",
            ),
            GarminDataType(
                "DAILY_SUMMARY",
                "get_daily_summary",
                APIMethodTimeParam.DAILY,
                "/usersummary-service/usersummary/daily/{display_name}"
                "?calendarDate={date}",
                "All-day dashboard rollup: total/active/resting/BMR calories, "
                "distance, active/sedentary/highly-active seconds, floors and "
                "intensity-minute goals, average/max stress, body battery range.",
                "📈",
            ),
            GarminDataType(
                "HRV",
                "get_hrv_data",
                APIMethodTimeParam.DAILY,
                "/hrv-service/hrv/{date}",
                "All-day heart rate variability readings and HRV status "
                "(distinct from the sleep-window HRV in the Sleep dataset).",
                "💗",
            ),
            GarminDataType(
                "RESTING_HR",
                "get_resting_hr",
                APIMethodTimeParam.DAILY,
                "/userstats-service/wellness/daily/{display_name}"
                "?fromDate={date}&untilDate={date}&metricId=60",
                "Daily resting heart rate trend.",
                "❤️",
            ),
            GarminDataType(
                "SPO2_DAILY",
                "get_spo2_data",
                APIMethodTimeParam.DAILY,
                "/wellness-service/wellness/daily/spo2/{date}",
                "All-day pulse oximetry (SpO2) readings and daily aggregates "
                "(distinct from the sleep-window SpO2 in the Sleep dataset).",
                "🩸",
            ),
            GarminDataType(
                "MAX_METRICS",
                "get_max_metrics",
                APIMethodTimeParam.DAILY,
                "/metrics-service/metrics/maxmet/daily/{date}/{date}",
                "Max metrics: VO2 max / MET values and fitness-age inputs.",
                "🫀",
            ),
            GarminDataType(
                "FITNESS_AGE",
                "get_fitness_age",
                APIMethodTimeParam.DAILY,
                "/fitnessage-service/fitnessage/{date}",
                "Fitness age and its contributing components.",
                "🎂",
            ),
            GarminDataType(
                "HYDRATION",
                "get_hydration_data",
                APIMethodTimeParam.DAILY,
                "/usersummary-service/usersummary/hydration/daily/{date}",
                "Daily fluid intake, goal, daily average, and sweat loss.",
                "💧",
            ),
            GarminDataType(
                "LIFESTYLE_LOGGING",
                "get_lifestyle_logging_data",
                APIMethodTimeParam.DAILY,
                "/lifestylelogging-service/dailyLog/{date}",
                "Daily lifestyle logging entries.",
                "📔",
            ),
            GarminDataType(
                "MENSTRUAL_CYCLE_DAY",
                "get_menstrual_data_for_date",
                APIMethodTimeParam.DAILY,
                "/periodichealth-service/menstrualcycle/dayview/{date}",
                "Daily menstrual cycle log: phase, day-in-cycle, period length, "
                "logged symptoms/moods/discharge, flow, sex drive, sexual activity, "
                "freeform notes, ovulation and baby-movement flags.",
                "🩸",
            ),
            GarminDataType(
                "ENDURANCE_SCORE",
                "get_endurance_score",
                APIMethodTimeParam.DAILY,
                "/metrics-service/metrics/endurancescore",
                "Daily endurance score.",
                "💪",
            ),
            GarminDataType(
                "HILL_SCORE",
                "get_hill_score",
                APIMethodTimeParam.DAILY,
                "/metrics-service/metrics/hillscore",
                "Daily hill score (climbing endurance).",
                "⛰️",
            ),
            GarminDataType(
                "NUTRITION",
                "get_nutrition_daily_food_log",
                APIMethodTimeParam.DAILY,
                "/nutrition-service/food/logs/{date}",
                "Daily nutrition food-log summary.",
                "🍎",
            ),
            # Range Data - Date range parameters: get_method(start_str, end_str)
            GarminDataType(
                "BODY_COMPOSITION",
                "get_body_composition",
                APIMethodTimeParam.RANGE,
                "/weight-service/weight/daterangesnapshot",
                "Scale weigh-ins: weight, BMI, body fat %, body water %, bone mass, "
                "muscle mass, physique rating, visceral fat, metabolic age. Multiple "
                "entries per day if the user weighs more than once.",
                "⚖️",
            ),
            GarminDataType(
                "MENSTRUAL_CYCLE_SUMMARY",
                "get_menstrual_calendar_data",
                APIMethodTimeParam.RANGE,
                "/periodichealth-service/menstrualcycle/calendar/{start}/{end}",
                "Per-cycle summaries (observed and predicted): start date, period "
                "length, predicted flag. Calendar endpoint has a 92-day max range "
                "per request; the wrapper paginates longer windows transparently. "
                "Unsplittable: the extractor writes one file stamped with end_date "
                "(not per-day) because the processor's wipe-and-replace policy for "
                "predicted cycles needs to see the full new set atomically.",
                "🩸",
            ),
            GarminDataType(
                "ACTIVITIES_LIST",
                "get_activities_by_date",
                APIMethodTimeParam.RANGE,
                "/activitylist-service/activities/search/activities",
                "Numerous aggregated metrics for user-recorded activities.",
                "📋",
            ),
            GarminDataType(
                "CALORIES_DAILY",
                "get_calories_daily",
                APIMethodTimeParam.RANGE,
                "/userstats-service/wellness/daily",
                "Daily active + resting (BMR) calories.",
                "🔥",
            ),
            GarminDataType(
                "WEIGH_INS",
                "get_weigh_ins",
                APIMethodTimeParam.RANGE,
                "/weight-service/weight/range/{start}/{end}",
                "Standalone manual weigh-ins.",
                "⚖️",
            ),
            GarminDataType(
                "BLOOD_PRESSURE",
                "get_blood_pressure",
                APIMethodTimeParam.RANGE,
                "/bloodpressure-service/bloodpressure/range/{start}/{end}",
                "Blood pressure measurements.",
                "🩺",
            ),
            GarminDataType(
                "RUNNING_TOLERANCE",
                "get_running_tolerance",
                APIMethodTimeParam.RANGE,
                "/metrics-service/metrics/runningtolerance/stats",
                "Running tolerance trend (daily aggregation).",
                "🏃",
            ),
            # No Date Data - No date parameters: get_method()
            # In case of backfilling, comment out PERSONAL_RECORD data type, since PRs
            # reference activity IDs that may not exist yet.
            GarminDataType(
                "PERSONAL_RECORDS",
                "get_personal_record",
                APIMethodTimeParam.NO_DATE,
                "/personalrecord-service/personalrecord/prs/{display_name}",
                "All-time personal bests steps, running, cycling, swimming, strength.",
                "🏆",
            ),
            GarminDataType(
                "RACE_PREDICTIONS",
                "get_race_predictions",
                APIMethodTimeParam.NO_DATE,
                "/metrics-service/metrics/racepredictions/latest/{display_name}",
                "Predicted running times based on current fitness level.",
                "🏁",
            ),
            GarminDataType(
                "USER_PROFILE",
                "get_user_profile",
                APIMethodTimeParam.NO_DATE,
                "/userprofile-service/userprofile/settings",
                "User profile settings including gender, weight, height, birthday, "
                "VO2 max (running and cycling), and lactate threshold (speed and heart "
                "rate).",
                "👤",
            ),
            GarminDataType(
                "GEAR",
                "get_gear",
                APIMethodTimeParam.NO_DATE,
                "/gear-service/gear/filterGear?userProfilePk={user_profile_pk}",
                "User-registered gear (shoes, bikes, and other equipment): make, "
                "model, type, status, usage limit, and begin/end dates.",
                "⚙️",
            ),
            GarminDataType(
                "HEART_RATE_ZONES",
                "get_heart_rate_zones",
                APIMethodTimeParam.NO_DATE,
                "/biometric-service/heartRateZones",
                "User's configured heart-rate zone definitions per sport "
                "(zone number and low/high BPM bounds).",
                "❤️",
            ),
            GarminDataType(
                "POWER_ZONES",
                "get_power_zones",
                APIMethodTimeParam.NO_DATE,
                "/biometric-service/powerZones",
                "User's configured power zone definitions per sport "
                "(zone number and low/high watt bounds).",
                "⚡",
            ),
            GarminDataType(
                "GOALS",
                "get_goals",
                APIMethodTimeParam.NO_DATE,
                "/goal-service/goal/goals",
                "User's daily goals (steps, sleep, active minutes, floors, etc.).",
                "🎯",
            ),
            GarminDataType(
                "DEVICES",
                "get_devices",
                APIMethodTimeParam.NO_DATE,
                "/device-service/deviceregistration/devices",
                "User's registered Garmin devices and their metadata.",
                "📟",
            ),
            GarminDataType(
                "WORKOUTS",
                "get_workouts",
                APIMethodTimeParam.NO_DATE,
                "/workout-service/workouts",
                "User's workout library (interval/step definitions).",
                "🏋️",
            ),
            GarminDataType(
                "TRAINING_PLANS",
                "get_training_plans",
                APIMethodTimeParam.NO_DATE,
                "/trainingplan-service/trainingplan/plans",
                "User's training plans.",
                "📅",
            ),
            GarminDataType(
                "PREGNANCY",
                "get_pregnancy_summary",
                APIMethodTimeParam.NO_DATE,
                "/periodichealth-service/menstrualcycle/pregnancysnapshot",
                "Pregnancy summary (empty when not applicable).",
                "🤰",
            ),
            GarminDataType(
                "ACTIVITY_TYPES",
                "get_activity_types",
                APIMethodTimeParam.NO_DATE,
                "/activity-service/activity/activityTypes",
                "Static Garmin activity-type catalog.",
                "🏷️",
            ),
            GarminDataType(
                "EARNED_BADGES",
                "get_earned_badges",
                APIMethodTimeParam.NO_DATE,
                "/badge-service/badge/earned",
                "User's earned badges.",
                "🏅",
            ),
            # Month Data - (year, month) parameters: get_method(year, month).
            GarminDataType(
                "CALENDAR",
                "get_calendar",
                APIMethodTimeParam.MONTH,
                "/calendar-service/year/{year}/month/{month}",
                "Training calendar: planned workouts, training-plan sessions, "
                "races, and wellness events for a given month (one call per "
                "year/month, month is 1-based).",
                "🗓️",
            ),
            # Per-Activity Data - Activity ID parameter: get_method(activity_id).
            # Iterated per activity (not per calendar date) by
            # ``GarminExtractor.extract_fit_activities``, which sources the activity
            # ID list from the ACTIVITIES_LIST output.
            GarminDataType(
                "EXERCISE_SETS",
                "get_activity_exercise_sets",
                APIMethodTimeParam.PER_ACTIVITY,
                "/activity-service/activity/{activity_id}/exerciseSets",
                "Per-set granular strength training data with "
                "ML-classified exercises, reps, weight, duration, "
                "and set type.",
                "💪",
            ),
            GarminDataType(
                "ACTIVITY_DETAILS",
                "get_activity_details",
                APIMethodTimeParam.PER_ACTIVITY,
                "/activity-service/activity/{activity_id}",
                "Rich per-activity metadata including stamina "
                "(begin/end/min potential stamina), performance condition, "
                "detailed respiration/temperature, recovery heart rate, and "
                "other summary fields absent from the compact ACTIVITIES_LIST.",
                "📊",
            ),
            GarminDataType(
                "ACTIVITY",
                "download_activity",
                APIMethodTimeParam.PER_ACTIVITY,
                "/download-service/files/activity/{activity_id}",
                "Binary FIT files containing detailed time-series activity data.",
                "🏃",
            ),
            GarminDataType(
                "ACTIVITY_WEATHER",
                "get_activity_weather",
                APIMethodTimeParam.PER_ACTIVITY,
                "/activity-service/activity/{activity_id}/weather",
                "Weather record attached to an activity (temperature, humidity, wind).",
                "🌤️",
            ),
            GarminDataType(
                "SPLIT_SUMMARIES",
                "get_activity_split_summaries",
                APIMethodTimeParam.PER_ACTIVITY,
                "/activity-service/activity/{activity_id}/split_summaries",
                "Garmin's own per-split pace/time/distance summaries.",
                "⏱️",
            ),
            GarminDataType(
                "ACTIVITY_GEAR",
                "get_activity_gear",
                APIMethodTimeParam.PER_ACTIVITY,
                "/gear-service/gear/filterGear?activityId={activity_id}",
                "Gear items used during an activity.",
                "👟",
            ),
        ]

        for data_type in data_types:
            self.register(data_type)

    def register(self, data_type: GarminDataType):
        """
        Register a Garmin data type.

        :param data_type: GarminDataType to register.
        :raises ValueError: If a data type with the same name already exists.
        """
        if data_type.name in self._data_types_by_name:
            raise ValueError(f"Data type with name '{data_type.name}' already exists.")

        self._data_types_by_name[data_type.name] = data_type
        self._data_types_by_time_param[data_type.api_method_time_param].append(
            data_type
        )
        self._all_data_types.append(data_type)

    def get_by_name(self, name: str) -> Optional[GarminDataType]:
        """
        Get data type by name.

        :param name: Name of the data type to retrieve.
        :return: GarminDataType if found, None otherwise.
        """
        return self._data_types_by_name.get(name)

    def get_by_time_param(
        self, api_method_time_param: APIMethodTimeParam
    ) -> List[GarminDataType]:
        """
        Get all data types of a specific API method time parameter.

        :param api_method_time_param: API method time parameter.
        :return: List of GarminDataType data types for the specified time param.
        """
        return self._data_types_by_time_param[api_method_time_param].copy()

    @property
    def all_data_types(self) -> List[GarminDataType]:
        """
        Get all registered data types.

        :return: Copy of all registered data types.
        """
        return self._all_data_types.copy()

    @property
    def daily_data_types(self) -> List[GarminDataType]:
        """
        Get all daily data types (shorthand).

        :return: List of data types with DAILY time parameter.
        """
        return self.get_by_time_param(APIMethodTimeParam.DAILY)

    @property
    def range_data_types(self) -> List[GarminDataType]:
        """
        Get all range data types (shorthand).

        :return: List of data types with RANGE time parameter.
        """
        return self.get_by_time_param(APIMethodTimeParam.RANGE)

    @property
    def no_date_data_types(self) -> List[GarminDataType]:
        """
        Get all no-date data types (shorthand).

        :return: List of data types with NO_DATE time parameter.
        """
        return self.get_by_time_param(APIMethodTimeParam.NO_DATE)

    @property
    def month_data_types(self) -> List[GarminDataType]:
        """
        Get all month-based data types (shorthand).

        :return: List of data types with MONTH time parameter.
        """
        return self.get_by_time_param(APIMethodTimeParam.MONTH)

    @property
    def per_activity_data_types(self) -> List[GarminDataType]:
        """
        Get all per-activity data types (shorthand).

        :return: List of data types with PER_ACTIVITY time parameter.
        """
        return self.get_by_time_param(APIMethodTimeParam.PER_ACTIVITY)


def _create_garmin_file_types() -> type:
    """
    Dynamically create GarminFileTypes enum from GarminDataRegistry, following the class
    signature specified in the lib.filesystem_utils.DefaultFileTypes class.

    This ensures that file type patterns stay synchronized with registered
    data types without manual maintenance. Each data type gets a corresponding
    file pattern with the appropriate extension based on its data format.

    Pattern format: .*_{data_type.name}_.*\\.{extension}$
    Extensions:
    - JSON files: .json (for most data types)
    - FIT/TCX files: .fit or .tcx (for ACTIVITY data type)

    :return: Enum class with file type patterns for Garmin Connect data pipeline.
    """
    patterns = {}

    # Sort longest-name-first so a name that is a prefix/suffix of another
    # (e.g. HEART_RATE_ZONES vs HEART_RATE, ACTIVITY_GEAR vs GEAR) is matched
    # by its own pattern before a shorter name's loose ``.*_{name}_.*`` pattern
    # can claim the file. ``_classify_files_by_type`` breaks on the first match,
    # so most-specific-first makes classification unambiguous.
    data_types = sorted(
        GARMIN_DATA_REGISTRY.all_data_types,
        key=lambda dt: len(dt.name),
        reverse=True,
    )

    # Add patterns for each data type in registry.
    for data_type in data_types:
        if data_type.name == "ACTIVITY":
            pattern = re.compile(rf".*_ACTIVITY_.*\.(fit|tcx)$")
        else:
            pattern = re.compile(rf".*_{data_type.name}_.*\.json$")
        patterns[data_type.name] = pattern

    # Create dynamic enum class.
    return Enum("GarminFileTypes", patterns)


# Global registry instance.
GARMIN_DATA_REGISTRY = GarminDataRegistry()

# Dynamically created file types enum based on registered data types.
GARMIN_FILE_TYPES = _create_garmin_file_types()


class SleepStage(IntEnum):
    """
    Discrete sleep stage classification used by Garmin Connect.

    Values map to the integer codes found in the SLEEP JSON response under
    sleepLevels[*].activityLevel. The enum name (e.g. "DEEP") is stored in
    sleep_level.stage_label as a denormalized human-readable label.
    """

    DEEP = 0
    LIGHT = 1
    REM = 2
    AWAKE = 3


class MenstrualCyclePhase(IntEnum):
    """
    Discrete menstrual cycle phase classification used by Garmin Connect.

    Values map to the integer codes found in the MENSTRUAL_CYCLE_DAY JSON response under
    daySummary.currentPhase. The enum name (e.g. "MENSTRUAL") is stored in
    menstrual_cycle_day.current_phase as a denormalized human-readable label; the
    integer index is not persisted.
    """

    MENSTRUAL = 1
    FOLLICULAR = 2
    OVULATORY = 3
    LUTEAL = 4


PR_TYPE_LABELS = {
    1: "Run: 1 km",
    2: "Run: 1 mile",
    3: "Run: 5 km",
    4: "Run: 10 km",
    7: "Run: Longest",
    8: "Bike: Longest",
    9: "Bike: Max Total Ascent",
    10: "Bike: 20 min Avg Power",
    11: "Bike: 40 km",
    12: "Steps: Most in a Day",
    13: "Steps: Most in a Week",
    14: "Steps: Most in a Month",
    15: "Steps: Longest Goal Streak",
    16: "Steps: Unknown Type",
    17: "Swim: Longest",
    18: "Swim: 100 m",
    19: "Swim: 100 yd",
    20: "Swim: 400 m",
    21: "Swim: 500 yd",
    22: "Swim: 750 m",
    23: "Swim: 1000 m",
    24: "Swim: 1000 yd",
    25: "Swim: 1500 m",
    26: "Swim: 1650 yd",
}


# ----------------------------------------------------------------------------------------
# FIT FILE FIELD CONVERSIONS
# ----------------------------------------------------------------------------------------

# Garmin stores GPS coordinates as raw semicircle integers in FIT files.
# To convert to decimal degrees, multiply by (180 / 2^31).
# Reference: https://developer.garmin.com/fit/cookbook/decoding-activity-files
SEMICIRCLES_TO_DEGREES = 180.0 / 2**31
