"""Validate the fixed MOH, MAS and MSF public aggregate feature encodings.

This deterministic qualification derives no binary targets, retained bits,
models or draws. It preserves publisher series and period identities and returns
only legal public predictors plus three exact source references for future
preregistered label construction. Published aggregate cells are not people.
"""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import re
from typing import Any

SCHEMA = "mra-qualified-encoding-audit/1.0"
AGENCIES = ("moh", "mas", "msf")
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_OBSERVATIONS = 65536
MAX_AUDIT_BYTES = 16 * 1024 * 1024
FEATURES = ("target_year", "target_period", "series_code", "previous_level_bin")
MOH_WEEKS = {year: 53 if year in (2014, 2020) else 52 for year in range(2012, 2023)}
MOH_SERIES = (
    "Acute Viral Hepatitis A", "Acute Viral Hepatitis E",
    "Acute Viral hepatitis B", "Acute Viral hepatitis C", "Avian Influenza",
    "Botulism", "Campylobacter enteritis", "Campylobacterenterosis",
    "Chikungunya", "Chikungunya Fever", "Cholera", "Dengue Fever",
    "Dengue Haemorrhagic Fever", "Diphtheria", "Ebola Virus Disease",
    "Encephalitis", "HFMD", "Haemophilus influenzae type b",
    "Hand, Foot Mouth Disease", "Japanese Encephalitis", "Legionellosis",
    "Leptospirosis", "Malaria", "Measles", "Melioidosis",
    "Meningococcal Infection", "Monkeypox", "Mumps", "Murine Typhus",
    "Nipah", "Nipah virus infection", "Paratyphoid", "Pertussis", "Plague",
    "Pneumococcal Disease (invasive)", "Poliomyelitis", "Rubella", "SARS",
    "Salmonellosis(non-enteric fevers)", "Tetanus", "Typhoid",
    "Viral Hepatitis A", "Viral Hepatitis E", "Yellow Fever", "Zika",
    "Zika Virus Infection",
)
MSF_SERIES = (
    "Comcare Long Term Assistance For Households",
    "Comcare Short-To-Medium Term Assistance For Households",
    "Overall Comcare Schemes For Households",
    "Student Care Fee Assistance For Households",
)
HEADERS = {
    "moh": ("epi_week", "disease", "no._of_cases"),
    "mas": ("month", "cards_main", "cards_supplementary", "total_billings", "rollover_balance"),
    "msf": ("DataSeries", "2024", "2023", "2022", "2021", "2020", "2019"),
}
VOCABULARIES = {"moh": MOH_SERIES, "mas": ("Credit and charge card total billings",), "msf": MSF_SERIES}
SPLIT_YEARS = {
    "moh": {"train": (2014, 2018), "auxiliary": (2019, 2019), "test": (2020, 2022)},
    "mas": {"train": (1993, 2005), "auxiliary": (2006, 2010), "test": (2011, 2015)},
    "msf": {"train": (2021, 2021), "auxiliary": (2022, 2022), "test": (2023, 2024)},
}
CALENDARS = {
    "moh": "Literal publisher Sunday-Saturday epidemiological periods; 2014 and 2020 have 53 weeks, other pinned 2012-2022 years have 52; no ISO conversion.",
    "mas": "Literal YYYY-MM calendar months with integer month ordinals.",
    "msf": "Literal integer calendar years from explicitly named annual CSV columns.",
}
UNITS = {"moh": "published cases", "mas": "S$ million total billings", "msf": "households within each published scheme"}
LEVEL_BINS = (
    "known zero", "(0,1)", "[1,10)", "[10,100)", "[100,1000)",
    "[1000,10000)", "[10000,100000)", "[100000,1000000)",
    "[1000000,10000000)", "[10000000,100000000)",
    "[100000000,1000000000)", "[1000000000,10000000000)",
    "[10000000000,100000000000)", "[100000000000,1000000000000)",
    "exact bounded maximum 1000000000000",
)
_INTEGER = re.compile(r"(?:0|[1-9][0-9]{0,12})\Z")
_AMOUNT = re.compile(r"(?:0|[1-9][0-9]{0,12})(?:\.[0-9]{1,6})?\Z")
_WEEK = re.compile(r"([0-9]{4})-W([0-9]{2})\Z")
_MONTH = re.compile(r"([0-9]{4})-([0-9]{2})\Z")
_MAX_NUMBER = Decimal("1000000000000")


class QualificationError(ValueError):
    """The fixed public source cannot support the declared encoding contract."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def parse_nonnegative_number(value: Any, *, integer: bool = False) -> Decimal:
    """Parse a bounded canonical source number without binary rounding."""
    if type(integer) is not bool or type(value) is not str or not (_INTEGER if integer else _AMOUNT).fullmatch(value):
        raise QualificationError("A known bounded nonnegative decimal is required; missing values and sentinels are not code zero")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise QualificationError("A source number is invalid") from exc
    if not result.is_finite() or result < 0 or result > _MAX_NUMBER:
        raise QualificationError("A source number exceeds the fixed public bound")
    return result


def level_bin(value: Any) -> int:
    """Fixed powers-of-ten bins; code zero denotes a verified actual zero."""
    if type(value) is not Decimal or not value.is_finite() or not Decimal(0) <= value <= _MAX_NUMBER:
        raise QualificationError("Level encoding requires a validated bounded Decimal")
    if value == 0:
        return 0
    if value < 1:
        return 1
    return value.adjusted() + 2


def _csv_rows(agency: str, raw: bytes) -> list[tuple[int, dict[str, str]]]:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_SOURCE_BYTES:
        raise QualificationError("A captured bounded source byte string is required")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise QualificationError("Public CSV must be valid UTF-8") from exc
    if "\x00" in text:
        raise QualificationError("Public CSV contains a NUL character")
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader)
        if tuple(header) != HEADERS[agency]:
            raise QualificationError("Public CSV columns differ from the fixed agency schema")
        result = []
        for values in reader:
            if len(values) != len(header) or any(len(value) > 160 for value in values):
                raise QualificationError("Public CSV has damaged, extra or oversized cells")
            result.append((reader.line_num, dict(zip(header, values))))
            if len(result) > MAX_OBSERVATIONS:
                raise QualificationError("Public CSV exceeds the fixed row bound")
        if not result:
            raise QualificationError("Public CSV has no observations")
        return result
    except (StopIteration, csv.Error) as exc:
        raise QualificationError("Public CSV is incomplete or malformed") from exc


def _period(agency: str, literal: str) -> tuple[int, int, int]:
    if agency == "moh":
        match = _WEEK.fullmatch(literal)
        if not match:
            raise QualificationError("MOH requires a literal YYYY-Www publisher period")
        year, part = (int(value) for value in match.groups())
        if year not in MOH_WEEKS or not 1 <= part <= MOH_WEEKS[year]:
            raise QualificationError("MOH week is outside the pinned publisher calendar")
        ordinal = sum(MOH_WEEKS[y] for y in MOH_WEEKS if y < year) + part
        return year, part, ordinal
    if agency == "mas":
        match = _MONTH.fullmatch(literal)
        if not match:
            raise QualificationError("MAS requires a literal YYYY-MM period")
        year, part = (int(value) for value in match.groups())
        if not 1991 <= year <= 2015 or not 1 <= part <= 12 or (year == 2015 and part > 8):
            raise QualificationError("MAS month is outside the pinned historical calendar")
        return year, part, year * 12 + part
    if literal not in HEADERS["msf"][1:]:
        raise QualificationError("MSF requires an explicitly named pinned annual column")
    year = int(literal)
    return year, 1, year


def _observation(agency: str, series: str, period: str, value: Decimal, line: int, column: str) -> dict[str, Any]:
    if series not in VOCABULARIES[agency]:
        raise QualificationError("An unrecognized public series cannot be silently merged or encoded as zero")
    year, part, ordinal = _period(agency, period)
    return {"series": series, "period": period, "year": year, "part": part, "ordinal": ordinal,
            "value": value, "line": line, "column": column}


def _observations(agency: str, raw: bytes) -> list[dict[str, Any]]:
    observations = []
    for line, row in _csv_rows(agency, raw):
        if agency == "moh":
            observations.append(_observation(agency, row["disease"], row["epi_week"],
                parse_nonnegative_number(row["no._of_cases"], integer=True), line, "no._of_cases"))
        elif agency == "mas":
            for column in ("cards_main", "cards_supplementary"):
                parse_nonnegative_number(row[column], integer=True)
            for column in ("total_billings", "rollover_balance"):
                parse_nonnegative_number(row[column])
            observations.append(_observation(agency, VOCABULARIES["mas"][0], row["month"],
                parse_nonnegative_number(row["total_billings"]), line, "total_billings"))
        else:
            for period in HEADERS["msf"][1:]:
                observations.append(_observation(agency, row["DataSeries"], period,
                    parse_nonnegative_number(row[period], integer=True), line, period))
    seen = set()
    for item in observations:
        identity = item["series"], item["ordinal"]
        if identity in seen:
            raise QualificationError("Duplicate series-period identity in the public source")
        seen.add(identity)
    periods = {item["ordinal"] for item in observations}
    if periods != set(range(min(periods), max(periods) + 1)):
        raise QualificationError("The captured whole public calendar has an interior missing period")
    return observations


def _reference(item: dict[str, Any]) -> dict[str, Any]:
    return {"line": item["line"], "period": item["period"], "column": item["column"]}


def qualify_source(agency: Any, raw: Any) -> dict[str, Any]:
    """Qualify one fixed source, with no caller-supplied encoding or split rules."""
    if type(agency) is not str or agency not in AGENCIES:
        raise QualificationError("Only the fixed MOH, MAS and MSF public sources are allowed")
    observations = _observations(agency, raw)
    groups: dict[str, dict[int, dict[str, Any]]] = {}
    for item in observations:
        groups.setdefault(item["series"], {})[item["ordinal"]] = item
    rows, counts = [], dict.fromkeys(("train", "auxiliary", "test"), 0)
    exclusions = dict.fromkeys(("insufficient_initial_history", "missing_predecessor_period", "pretraining_years"), 0)
    gaps, triplets = {}, 0
    for series in sorted(groups):
        group = groups[series]
        ordered = sorted(group)
        gaps[series] = sum(b - a - 1 for a, b in zip(ordered, ordered[1:]))
        for index, ordinal in enumerate(ordered):
            target = group[ordinal]
            if index < 2:
                exclusions["insufficient_initial_history"] += 1
                continue
            if ordinal - 1 not in group or ordinal - 2 not in group:
                exclusions["missing_predecessor_period"] += 1
                continue
            triplets += 1
            split = next((name for name, (first, last) in SPLIT_YEARS[agency].items()
                          if first <= target["year"] <= last), None)
            if split is None:
                exclusions["pretraining_years"] += 1
                continue
            previous, earlier = group[ordinal - 1], group[ordinal - 2]
            identity = [agency, series, target["period"]]
            key = hashlib.sha256(b"mra-qualified-public-observation/v1:" + _canonical(identity)).hexdigest()
            rows.append({"key": key, "period": target["period"], "series": series, "split": split,
                         "features": [target["year"], target["part"], VOCABULARIES[agency].index(series) + 1, level_bin(previous["value"])],
                         "label_recipe_references": [_reference(earlier), _reference(previous), _reference(target)]})
            counts[split] += 1
    rows.sort(key=lambda row: (_period(agency, row["period"])[2], row["series"], row["key"]))
    if len({row["key"] for row in rows}) != len(rows):
        raise QualificationError("Public forecast identities must be unique")
    limits = [
        "The representative scope is every eligible observation in the pinned published finite frame, not residents, patients, bank customers or future periods.",
        "Time-series cells are not iid population observations; complete finite-frame evaluation has no sampling confidence interval.",
        "Raw published values have public histories; historically untouched outcomes are not claimed.",
        "These are frozen historical published vintages. Actual as-of lag availability, reporting delays and subsequent revisions are not verified; tasks are retrospective forecasts only.",
        "No binary labels, retained responses, fresh draws, fits or usefulness verdicts are produced by qualification.",
        "Three chronological cohorts differ in period; the clean public-only comparison is the declared earlier auxiliary cohort, not a target-matched population oracle.",
    ]
    if agency == "moh":
        limits.append("Exact renamed disease strings remain separate series; unsupported alias harmonization is refused.")
    elif agency == "mas":
        limits.append("The MAS frame ends in August 2015 and provides no current monetary-policy effectiveness evidence.")
    else:
        limits.append("Only 24 published household-scheme cells, 16 eligible forecast rows and 8 target rows exist; future and operational inference are severely limited.")
    result = {"agency": agency, "source_sha256": hashlib.sha256(raw).hexdigest(),
              "raw_observations": len(observations), "consecutive_triplets": triplets,
              "eligible_observations": len(rows), "split_counts": counts, "split_years": SPLIT_YEARS[agency],
              "features": list(FEATURES), "feature_contract": {
                  "target_year": "Semantic integer calendar year; no lexical unknown-year code.",
                  "target_period": "Publisher week/month number starting at 1; annual period is the legitimate constant 1.",
                  "series_code": "Stable explicit vocabulary index starting at 1; unknown and missing series are rejected.",
                  "previous_level_bin": {"unit": UNITS[agency], "bins": list(LEVEL_BINS),
                      "basis": "Only validated t-1 published level; no target t or prior-direction bit."}},
              "unknown_or_missing_encodings": 0, "legitimate_zero_lag_features": sum(row["features"][3] == 0 for row in rows),
              "calendar_method": CALENDARS[agency], "series_vocabulary": list(VOCABULARIES[agency]),
              "present_series": sorted(groups), "source_period_bounds": [
                  min(observations, key=lambda item: item["ordinal"])["period"],
                  max(observations, key=lambda item: item["ordinal"])["period"]],
              "exclusions": exclusions, "interior_absent_periods_by_series": gaps,
              "target_frame": "Census of every eligible test-split published observation; no subsampling or outcome-based selection.",
              "label_recipe": "References are t-2,t-1,t in order. Later registered execution may set z=1[level(t-1)>level(t-2)] and y=1[level(t)>level(t-1)]; qualification does not compute them.",
              "limitations": limits, "rows": rows}
    if len(_canonical(result)) > MAX_AUDIT_BYTES:
        raise QualificationError("Qualified public frame exceeds the bounded artifact size")
    return result


def qualify_sources(source_bytes: Any) -> dict[str, Any]:
    """Qualify all three mandatory agencies without encoding/task overrides."""
    if type(source_bytes) is not dict or set(source_bytes) != set(AGENCIES):
        raise QualificationError("Exactly the three mandatory public source byte strings are required")
    result = {"schema": SCHEMA, "status": "validated", "no_labels_derived": True,
              "no_fits": True, "no_random_draws": True, "agencies_order": list(AGENCIES),
              "agencies": {agency: qualify_source(agency, source_bytes[agency]) for agency in AGENCIES},
              "authorization_effect": "none", "production_execution_qualified": False}
    if len(_canonical(result)) > MAX_AUDIT_BYTES:
        raise QualificationError("Qualified public frames exceed the bounded artifact size")
    return result
