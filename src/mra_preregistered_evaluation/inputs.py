"""Strict captured-vintage MAS parsing and the frozen retrospective design.

No file is read here. The execution store supplies one already verified byte
buffer only after reserving the frozen runtime. Clean truth stays on the
operator side of the randomized fitter boundary.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
import csv
import hashlib
import io
import json
import re
import numpy as np

SOURCE_SHA256 = 'b984e77e8069f43be583f7d09b1e9357660b51ddf691528af9a7db4031d97e71'
SOURCE_BYTES = 15542
TITLE = ['MSB I.17 Credit and Charge Card Statistics (Discontinued from July 2019)', '', '', '', '', '', '']
HEADERS = ['PERIOD', 'NUMBER OF LOCAL CARDHOLDERS - MAIN *', 'NUMBER OF LOCAL CARDHOLDERS - SUPPLEMENTARY *', 'S$ MILLION - TOTAL CARD BILLINGS', 'S$ MILLION - ROLLOVER BALANCE ^', 'S$ MILLION - BAD DEBTS WRITTEN OFF', 'PERCENT - CHARGE-OFF RATES #']
FOOTER = 'The notes and footnotes for this table can be found on the online Monthly Statistical Bulletin database.'
MONTHS = ('Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec')
NUMBER = re.compile(r'(?:0|[1-9][0-9]*)(?:\.[0-9]{1,6})?\Z', re.ASCII)
DATE = re.compile(r'([0-9]{4}) ([A-Z][a-z]{2})\Z', re.ASCII)
SERIES = 'S$ MILLION - TOTAL CARD BILLINGS'
COEFFICIENT_NAMES = ['intercept', 'year_scaled'] + [f'month_{i:02}' for i in range(1,13)] + [f'previous_level_bin_{i:02}' for i in range(15)]

class InputError(ValueError):
    pass


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def level_bin(value):
    if type(value) is not Decimal or not value.is_finite() or value < 0 or value > Decimal('1000000000000'):
        raise InputError('Lag value must be a finite nonnegative Decimal <=1e12')
    if value == 0:
        return 0
    if value < 1:
        return 1
    if value == Decimal('1000000000000'):
        return 14
    return value.adjusted() + 2


def _decimal(text):
    if type(text) is not str or not NUMBER.fullmatch(text):
        raise InputError('Malformed non-exponent decimal or more than six fractional digits')
    value = Decimal(text)
    if not value.is_finite() or value < 0:
        raise InputError('Negative or nonfinite public numeric value')
    return value


def encode_design(public_rows):
    """Return float design and exact rational design from calendar/lag bins."""
    exact = []
    for year, month, lag_bin in public_rows:
        if (type(year) is not int or not 1991 <= year <= 2019 or type(month) is not int
                or not 1 <= month <= 12 or type(lag_bin) is not int or not 0 <= lag_bin <= 14):
            raise InputError('Out-of-contract public design')
        row = [Fraction(1), Fraction(year - 1991, 30)] + [Fraction(int(month == i)) for i in range(1,13)] + [Fraction(int(lag_bin == i)) for i in range(15)]
        if sum(x*x for x in row) > Fraction(871,225):
            raise InputError('Fixed design norm proof failed')
        exact.append(tuple(row))
    array = np.array(exact, dtype=np.float64)
    array.setflags(write=False)
    return array, tuple(exact)


@dataclass(frozen=True)
class SourceFrame:
    document: dict
    X: np.ndarray
    exact_design: tuple
    y: np.ndarray
    z: np.ndarray
    seasonal: np.ndarray
    months: np.ndarray
    keys: tuple

    def artifacts(self):
        return {'cohorts.json': canonical_bytes(self.document)}


def capture_and_derive(source_bytes, *, expected_sha256=SOURCE_SHA256, mode='retrospective_observation_index', require_pinned=True):
    if mode != 'retrospective_observation_index':
        raise InputError('Calendar-origin mode refused: original historical release vintages are unresolved')
    if type(source_bytes) is not bytes:
        raise InputError('One immutable captured byte buffer required')
    actual = hashlib.sha256(source_bytes).hexdigest()
    if actual != expected_sha256 or (require_pinned and (expected_sha256 != SOURCE_SHA256 or len(source_bytes) != SOURCE_BYTES)):
        raise InputError('Captured source differs from frozen byte identity')
    try:
        rows = list(csv.reader(io.StringIO(source_bytes.decode('utf-8-sig'), newline='')))
    except (UnicodeError, csv.Error) as exc:
        raise InputError('Malformed captured UTF-8 CSV') from exc
    if len(rows) < 3 or rows[0] != TITLE or rows[1] != HEADERS:
        raise InputError('Exact title/header required in fixed order')
    values = {}
    footer_seen = False
    for row in rows[2:]:
        if row == []:
            # The captured export has empty separator records. They carry no data.
            continue
        if row == [FOOTER]:
            if footer_seen:
                raise InputError('Duplicate footer')
            footer_seen = True
            continue
        if footer_seen or len(row) != len(HEADERS) or row == HEADERS:
            raise InputError('Unknown nondata row, duplicate header or malformed width')
        match = DATE.fullmatch(row[0])
        if not match or match.group(2) not in MONTHS:
            raise InputError('Malformed YYYY Mon period')
        year, month = int(match.group(1)), MONTHS.index(match.group(2)) + 1
        ordinal = year * 12 + month - 1
        if not 1991*12 <= ordinal <= 2019*12+5 or ordinal in values:
            raise InputError('Duplicate or out-of-frame month')
        # Only the registered billings field is admitted. Unrelated charge-off
        # cells are historically missing in the already audited source; they
        # are neither parsed nor imputed, and never become target/features.
        billings = _decimal(row[3])
        level_bin(billings)
        values[ordinal] = billings
    expected = list(range(1991*12,2019*12+6))
    if not footer_seen or sorted(values) != expected or len(values) != 342:
        raise InputError('Exact complete 342-month calendar and footer required')
    keys, public_rows, truth, prior_truth, seasonal = [], [], [], [], []
    cells = []
    for ordinal in expected[2:]:
        year, zero_month = divmod(ordinal,12)
        month = zero_month + 1
        period = f'{year:04}-{month:02}'
        key = f'mas:monthly-total-card-billings:{period}'
        y = int(values[ordinal] > values[ordinal-1])
        z = int(values[ordinal-1] > values[ordinal-2])
        lag_bin = level_bin(values[ordinal-1])
        sy = None if ordinal - 13 not in values else int(values[ordinal-12] > values[ordinal-13])
        cohort = 'training' if ordinal <= 2010*12+11 else 'validation' if ordinal <= 2015*12+7 else 'final'
        keys.append(key); public_rows.append((year,month,lag_bin)); truth.append(y); prior_truth.append(z); seasonal.append(-1 if sy is None else sy)
        cells.append({'key':key,'period':period,'year':year,'month':month,'previous_level_bin':lag_bin,'y':y,'z':z,'seasonal_direction':sy,'cohort':cohort})
    counts = {name:sum(c['cohort']==name for c in cells) for name in ('training','validation','final')}
    if counts != {'training':238,'validation':56,'final':46} or any(v < 0 for v in seasonal[238:]):
        raise InputError('Frozen cohort/seasonal membership failed')
    X, exact = encode_design(public_rows)
    arrays = [np.array(v, dtype=np.int64) for v in (truth,prior_truth,seasonal,[r[1] for r in public_rows])]
    for a in arrays:
        a.setflags(write=False)
    document = {'schema':'mra-phase7c-source-cohorts/1.0','source_sha256':actual,'source_bytes':len(source_bytes),'published_series':SERIES,'mode':mode,'source_periods':['1991-01','2019-06'],'source_months':342,'all_triplets':340,'counts':counts,'predetermined_final_refit':294,'coefficient_names':COEFFICIENT_NAMES,'design_dimension':29,'exact_year_denominator':30,'design_norm_squared_upper':'871/225','cells':cells,'historically_unobserved':False,'real_time_validity':'unresolved','authorization_effect':'none'}
    return SourceFrame(document,X,exact,*arrays,tuple(keys))
