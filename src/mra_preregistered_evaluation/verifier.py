"""Independent Decimal arithmetic and frozen Phase 7C result verification.

No source is opened and no randomization is drawn by this module. Registered
rational design/target values are supplied by the caller. Decimal.exp is
correctly rounded (Python's Decimal contract); each result is widened by one
precision-40 ulp and every other operation uses directed interval rounding.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN
from fractions import Fraction
from functools import lru_cache
import json
import math
from typing import Any

import numpy as np

PRECISION = 40
_DOWN = Context(prec=PRECISION, rounding=ROUND_FLOOR)
_UP = Context(prec=PRECISION, rounding=ROUND_CEILING)
_NEAR = Context(prec=PRECISION, rounding=ROUND_HALF_EVEN)
_ZERO = Decimal(0)
_ONE = Decimal(1)
_TWO = Decimal(2)
_FOUR = Decimal(4)
_LAMBDA = Decimal('0.1')


class VerificationError(ValueError):
    """A frozen numerical or scientific qualification condition failed."""


@lru_cache(maxsize=256)
def _fraction_point(value):
    numerator, denominator = Decimal(value.numerator), Decimal(value.denominator)
    return _DOWN.divide(numerator, denominator), _UP.divide(numerator, denominator)


def _point(value: Any) -> tuple[Decimal, Decimal]:
    if isinstance(value, Fraction):
        return _fraction_point(value)
    if isinstance(value, (float, np.floating)):
        value = Decimal.from_float(float(value))
    elif isinstance(value, (int, np.integer)):
        value = Decimal(int(value))
    elif not isinstance(value, Decimal):
        value = Decimal(str(value))
    if not value.is_finite():
        raise VerificationError('nonfinite exact input')
    return value, value


def _add(a, b):
    return _DOWN.add(a[0], b[0]), _UP.add(a[1], b[1])


def _sub(a, b):
    return _DOWN.subtract(a[0], b[1]), _UP.subtract(a[1], b[0])


def _mul(a, b):
    # Exact identities preserve directed bounds while exploiting the registered
    # sparse one-hot design. No approximate arithmetic or changed tolerance.
    if a == (_ZERO, _ZERO) or b == (_ZERO, _ZERO):
        return (_ZERO, _ZERO)
    if a == (_ONE, _ONE):
        return b
    if b == (_ONE, _ONE):
        return a
    lowers = (_DOWN.multiply(a[i], b[j]) for i in (0, 1) for j in (0, 1))
    uppers = (_UP.multiply(a[i], b[j]) for i in (0, 1) for j in (0, 1))
    return min(lowers), max(uppers)


def _divide_positive(a, denominator: Decimal):
    if denominator <= 0:
        raise VerificationError('positive denominator required')
    return _DOWN.divide(a[0], denominator), _UP.divide(a[1], denominator)


def _sqrt_upper(value: Decimal) -> Decimal:
    if value < 0:
        raise VerificationError('negative square root')
    if value == 0:
        return value
    return _NEAR.next_plus(_NEAR.sqrt(value))


def _float_upper(value: Decimal) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise VerificationError('nonfinite bound conversion')
    if Decimal.from_float(result) < value:
        result = float(np.nextafter(result, math.inf))
    return result


def _float_lower(value: Decimal) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise VerificationError('nonfinite bound conversion')
    if Decimal.from_float(result) > value:
        result = float(np.nextafter(result, -math.inf))
    return result


@dataclass(frozen=True)
class PreparedDesign:
    """Cached independent exact-input intervals; no labels or identifiers."""
    shape: tuple[int, int]
    rows: tuple[tuple[tuple[int, tuple[Decimal, Decimal]], ...], ...]
    exact_rows: tuple[tuple[Any, ...], ...]
    float_rows: tuple[tuple[float, ...], ...]
    norm_squared_upper: Decimal


def prepare_exact_design(X, exact_design=None) -> PreparedDesign:
    array = np.asarray(X, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 29 or not array.shape[0] or not np.isfinite(array).all():
        raise VerificationError('finite nonempty 29-column design required')
    if isinstance(exact_design, PreparedDesign):
        if exact_design.shape != array.shape or exact_design.float_rows != tuple(map(tuple, array)):
            raise VerificationError('prepared design does not bind exact float design')
        return exact_design
    exact = array if exact_design is None else exact_design
    if len(exact) != array.shape[0] or any(len(row) != 29 for row in exact):
        raise VerificationError('exact design shape mismatch')
    rows, exact_rows = [], []
    norm_squared_upper = _ZERO
    for float_row, exact_row in zip(array, exact):
        intervals = tuple(_point(value) for value in exact_row)
        row_norm_squared = _ZERO
        for lower, upper in intervals:
            absolute = max(lower.copy_abs(), upper.copy_abs())
            row_norm_squared = _UP.add(row_norm_squared, _UP.multiply(absolute, absolute))
        norm_squared_upper = max(norm_squared_upper, row_norm_squared)
        # The float implementation must be the nearest float of the supplied
        # normative rational/Decimal design, not a different covariate matrix.
        for actual, interval in zip(float_row, intervals):
            middle = _NEAR.divide(_NEAR.add(*interval), _TWO)
            if float(middle) != float(actual):
                raise VerificationError('float and exact design differ')
        rows.append(tuple((j, interval) for j, interval in enumerate(intervals) if interval != (_ZERO, _ZERO)))
        exact_rows.append(tuple(exact_row))
    return PreparedDesign(array.shape, tuple(rows), tuple(exact_rows), tuple(map(tuple, array)), norm_squared_upper)


# Alias retained for a solver choosing the name proposed during coordination.
build_exact_design = prepare_exact_design


def _beta_points(beta, dimension=29):
    values = np.asarray(beta, dtype=np.float64)
    if values.shape != (dimension,) or not np.isfinite(values).all():
        raise VerificationError('finite 29-coefficient model required')
    return tuple(_point(value) for value in values)


def _sigmoid_interval(logit):
    """One correctly-rounded exp, outward operations, and a Lipschitz pad."""
    midpoint = _NEAR.divide(_NEAR.add(*logit), _TWO)
    delta = max(_UP.subtract(midpoint, logit[0]), _UP.subtract(logit[1], midpoint))
    exp_mid = _NEAR.exp(midpoint.copy_negate())
    exp_lower = max(_ZERO, _NEAR.next_minus(exp_mid))
    exp_upper = _NEAR.next_plus(exp_mid)
    lower = _DOWN.divide(_ONE, _UP.add(_ONE, exp_upper))
    upper = _UP.divide(_ONE, _DOWN.add(_ONE, exp_lower))
    pad = _UP.divide(delta, _FOUR)  # sigmoid is globally 1/4-Lipschitz
    return max(_ZERO, _DOWN.subtract(lower, pad)), min(_ONE, _UP.add(upper, pad))


def _probability_intervals(prepared: PreparedDesign, beta):
    points = _beta_points(beta)
    result = []
    for row in prepared.rows:
        logit = (_ZERO, _ZERO)
        for j, coefficient in row:
            logit = _add(logit, _mul(coefficient, points[j]))
        result.append(_sigmoid_interval(logit))
    return tuple(result)


def gradient_enclosure(X, beta, targets, *, exact_design=None, exact_targets=None):
    """Outward enclosure of the normative exact objective's true gradient."""
    prepared = prepare_exact_design(X, exact_design)
    values = np.asarray(targets, dtype=np.float64)
    if values.shape != (prepared.shape[0],) or not np.isfinite(values).all():
        raise VerificationError('finite target vector required')
    exact = values if exact_targets is None else exact_targets
    if len(exact) != len(values):
        raise VerificationError('exact target shape mismatch')
    intervals = tuple(_point(value) for value in exact)
    for actual, interval in zip(values, intervals):
        if float(_NEAR.divide(_NEAR.add(*interval), _TWO)) != float(actual):
            raise VerificationError('float and exact targets differ')
    probabilities = _probability_intervals(prepared, beta)
    sums = [(_ZERO, _ZERO) for _ in range(29)]
    for row, probability, target in zip(prepared.rows, probabilities, intervals):
        residual = _sub(probability, target)
        for j, coefficient in row:
            sums[j] = _add(sums[j], _mul(coefficient, residual))
    beta_points = _beta_points(beta)
    n = Decimal(prepared.shape[0])
    gradients = tuple(_add(_divide_positive(total, n), _mul((_LAMBDA, _LAMBDA), b)) for total, b in zip(sums, beta_points))
    square_upper = _ZERO
    uncertainty_square_upper = _ZERO
    for lower, upper in gradients:
        absolute = max(lower.copy_abs(), upper.copy_abs())
        square_upper = _UP.add(square_upper, _UP.multiply(absolute, absolute))
        radius = _UP.divide(_UP.subtract(upper, lower), _TWO)
        uncertainty_square_upper = _UP.add(uncertainty_square_upper, _UP.multiply(radius, radius))
    norm = _sqrt_upper(square_upper)
    uncertainty = _sqrt_upper(uncertainty_square_upper)
    return {
        'schema': 'mra-phase7c-true-gradient-enclosure/1.0',
        'precision_decimal_digits': PRECISION,
        'norm_upper': _float_upper(norm),
        'norm_upper_decimal': str(norm),
        'arithmetic_uncertainty_upper': _float_upper(uncertainty),
        'arithmetic_uncertainty_upper_decimal': str(uncertainty),
        'component_intervals': [[str(lo), str(hi)] for lo, hi in gradients],
        'accepted': norm <= Decimal('1e-12') and uncertainty <= Decimal('5e-13'),
        'design_and_targets': 'supplied normative exact rational values',
        'method': 'Decimal40 directed finite operations; correctly-rounded exp widened one ulp; sigmoid Lipschitz padding',
    }


def certified_probabilities(X, beta, *, exact_design=None):
    """Deterministic midpoint floats with independent outward absolute bounds."""
    prepared = prepare_exact_design(X, exact_design)
    intervals = _probability_intervals(prepared, beta)
    values, bound = [], _ZERO
    for lower, upper in intervals:
        midpoint = _NEAR.divide(_NEAR.add(lower, upper), _TWO)
        value = float(midpoint)
        actual = Decimal.from_float(value)
        error = max(_UP.subtract(actual, lower).copy_abs(), _UP.subtract(upper, actual).copy_abs())
        bound = max(bound, error)
        values.append(value)
    return np.asarray(values, dtype=np.float64), {
        'schema': 'mra-phase7c-probability-enclosure/1.0',
        'precision_decimal_digits': PRECISION,
        'maximum_absolute_error_upper': _float_upper(bound),
        'max_absolute_error_upper': _float_upper(bound),
        'maximum_absolute_error_upper_decimal': str(bound),
        'intervals': [[str(lo), str(hi)] for lo, hi in intervals],
        'method': 'Decimal40 outward sigmoid with nearest binary64 midpoint conversion',
    }


def formal_gain_error_accounting(*, maximum_probability_error=Decimal('1.2e-16'), design_norm=Decimal(2), gradient_norm=Decimal('1e-12')):
    """An analytic IEEE-754 bound, separate from empirical fit agreement.

    Assumes nonnegative chronological binary64 sums and no nonfinite output.
    For k operations gamma_k=k*u/(1-k*u), u=2^-53. Probability error is
    enclosed independently by certified_probabilities rather than assumed
    from any platform's exp. The counts deliberately exceed actual scoring
    operation counts. Float sums of at most 16384 numbers in [-1,1] have
    absolute error bounded using sum absolute values, not relative error.
    """
    probability = Decimal(str(maximum_probability_error))
    norm = Decimal(str(design_norm))
    gradient = Decimal(str(gradient_norm))
    if probability < 0 or probability > Decimal('1.2e-16') or norm > 2 or gradient > Decimal('1e-12'):
        raise VerificationError('formal gain error premises exceed frozen limits')
    u = _UP.divide(_ONE, Decimal(9007199254740992))
    def gamma(k):
        product = _UP.multiply(Decimal(k), u)
        return _UP.divide(product, _DOWN.subtract(_ONE, product))
    optimization = _UP.divide(_UP.multiply(norm, gradient), _LAMBDA)  # two-route bound R*g/lambda
    brier_probability = _UP.add(_UP.multiply(_TWO, probability), _UP.multiply(probability, probability))
    # Each square uses subtraction/multiplication, then <=56 chronological
    # frame accumulations/division; gains one subtraction. The complete-law
    # mean accumulates 16384 signed gains and divides once. Worst-case loss
    # values <=1 and absolute gain <=1, padded to2 for rounding.
    single_frame = _UP.add(brier_probability, gamma(64))
    paired_frame = _UP.add(_UP.multiply(_TWO, single_frame), gamma(2))
    outer_mean = _UP.multiply(_TWO, gamma(16386))
    arithmetic = _UP.add(paired_frame, outer_mean)
    total = _UP.add(optimization, arithmetic)
    if arithmetic > Decimal('9.8e-10') or total > Decimal('1e-9'):
        raise VerificationError('formal numerical error exceeds frozen guard')
    return {
        'schema': 'mra-phase7c-formal-gain-error/1.0',
        'optimization_gain_error_upper': _float_upper(optimization),
        'scoring_accumulation_gain_error_upper': _float_upper(arithmetic),
        'formal_total_gain_error_upper': _float_upper(total),
        'fixed_guard': 1e-9,
        'unit_roundoff': str(u),
        'maximum_probability_error_upper': str(probability),
        'proof': 'Strong convexity lambda=1/10, R<=2; independent sigmoid enclosures; gamma64 frame, gamma2 pairing, twice gamma16386 signed outer accumulation; chronological binary64 arithmetic.',
        'scope': 'fixed-frame Brier paired gain only; empirical agreement is not the proof',
        'passed': True,
    }


def guarded_interval(mean_gain):
    """Independent outward bounds for frozen M18/N16384/alpha1/20 rule."""
    value = _point(mean_gain)[0]
    if not -1 <= value <= 1:
        raise VerificationError('mean gain outside [-1,1]')
    # Decimal ln and sqrt are correctly rounded. Enclose both by one ulp.
    logarithm = _NEAR.ln(Decimal(720))
    ln_lo, ln_hi = _NEAR.next_minus(logarithm), _NEAR.next_plus(logarithm)
    argument_lo = _DOWN.divide(_DOWN.multiply(_TWO, ln_lo), Decimal(16384))
    argument_hi = _UP.divide(_UP.multiply(_TWO, ln_hi), Decimal(16384))
    radius_lo = _DOWN.add(_NEAR.next_minus(_NEAR.sqrt(argument_lo)), Decimal('1e-9'))
    radius_hi = _UP.add(_NEAR.next_plus(_NEAR.sqrt(argument_hi)), Decimal('1e-9'))
    lower = max(Decimal(-1), _DOWN.subtract(value, radius_hi))
    upper = min(_ONE, _UP.add(value, radius_hi))
    verdict = 'pass' if lower > 0 else 'fail' if upper <= 0 else 'inconclusive'
    return {'mean_gain': float(value), 'lower': _float_lower(lower), 'upper': _float_upper(upper), 'lower_decimal': str(lower), 'upper_decimal': str(upper), 'radius_upper_decimal': str(radius_hi), 'radius_lower_decimal': str(radius_lo), 'verdict': verdict}


COMPARATORS = ('independent_rr', 'clean_matched_logistic', 'clean_persistence', 'clean_seasonal_naive', 'clean_expanding_month_rate', 'clean_expanding_logistic')
DOMAINS = ('moh', 'mas', 'msf')


def verify_mandatory_results(slots):
    if len(slots) != 18:
        raise VerificationError('all 18 mandatory slots must be retained')
    expected = tuple((domain, comparator) for domain in DOMAINS for comparator in COMPARATORS)
    actual = tuple((slot.get('domain'), slot.get('comparator')) for slot in slots)
    if actual != expected:
        raise VerificationError('mandatory slot identity/order differs')
    verdicts = []
    for slot in slots:
        if slot['domain'] in ('moh', 'msf'):
            if slot.get('verdict') != 'not_evaluable':
                raise VerificationError('unsupported mandatory slot acquired a verdict')
            for key in ('mean_gain', 'lower', 'upper', 'candidate_loss', 'comparator_loss'):
                if slot.get(key) is not None:
                    raise VerificationError('unsupported mandatory slot acquired a numeric value')
        else:
            interval = guarded_interval(slot['mean_gain'])
            if slot.get('verdict') != interval['verdict']:
                raise VerificationError('primary verdict does not follow guarded unrounded bounds')
            if slot.get('lower') is not None and slot['lower'] > interval['lower']:
                raise VerificationError('reported lower endpoint rounds inward')
            if slot.get('upper') is not None and slot['upper'] < interval['upper']:
                raise VerificationError('reported upper endpoint rounds inward')
        verdicts.append(slot['verdict'])
    aggregate = 'fail' if 'fail' in verdicts else 'not_evaluable' if 'not_evaluable' in verdicts else 'inconclusive' if 'inconclusive' in verdicts else 'pass'
    return {'schema': 'mra-phase7c-independent-mandatory-results/1.0', 'mandatory_slots': 18, 'family_size': 18, 'aggregate': aggregate, 'all_domain_readiness': 'not_evaluable', 'agency_practical_margin': None, 'agency_acceptance': 'pending', 'authorization_effect': 'none', 'passed': True}


def _decimal_value(value, ctx):
    if isinstance(value, Fraction):
        return ctx.divide(Decimal(value.numerator), Decimal(value.denominator))
    return _point(value)[0]


def reference_fit(X, targets, *, exact_design=None, exact_targets=None, precision=70):
    """Independent Decimal Newton/Cholesky fit; never uses NumPy solver code."""
    prepared = prepare_exact_design(X, exact_design)
    ctx = Context(prec=precision, rounding=ROUND_HALF_EVEN)
    rows = tuple(tuple(_decimal_value(v, ctx) for v in row) for row in prepared.exact_rows)
    supplied_targets = targets if exact_targets is None else exact_targets
    labels = tuple(_decimal_value(v, ctx) for v in supplied_targets)
    if len(labels) != len(rows):
        raise VerificationError('reference target shape mismatch')
    n, d = Decimal(len(rows)), 29
    beta = [_ZERO] * d
    threshold = Decimal('1e-35')
    def dot(a, b):
        result = _ZERO
        for x, y in zip(a, b):
            result = ctx.add(result, ctx.multiply(x, y))
        return result
    def probabilities(coefficients):
        logits = [dot(row, coefficients) for row in rows]
        p = [ctx.divide(_ONE, ctx.add(_ONE, ctx.exp(z.copy_negate()))) for z in logits]
        return logits, p
    def objective(coefficients):
        logits, _ = probabilities(coefficients)
        total = _ZERO
        for z, v in zip(logits, labels):
            # Stable softplus at independent precision.
            softplus = ctx.add(max(z, _ZERO), ctx.ln(ctx.add(_ONE, ctx.exp(z.copy_abs().copy_negate()))))
            total = ctx.add(total, ctx.subtract(softplus, ctx.multiply(v, z)))
        return ctx.add(ctx.divide(total, n), ctx.multiply(Decimal('0.05'), dot(coefficients, coefficients)))
    for iteration in range(256):
        logits, probs = probabilities(beta)
        gradient = [_ZERO] * d
        hessian = [[_ZERO] * d for _ in range(d)]
        for row, p, v in zip(rows, probs, labels):
            residual = ctx.subtract(p, v)
            weight = ctx.multiply(p, ctx.subtract(_ONE, p))
            active = [(j, x) for j, x in enumerate(row) if x]
            for j, x in active:
                gradient[j] = ctx.add(gradient[j], ctx.multiply(x, residual))
                for k, y in active:
                    if k <= j:
                        hessian[j][k] = ctx.add(hessian[j][k], ctx.multiply(weight, ctx.multiply(x, y)))
        for j in range(d):
            gradient[j] = ctx.add(ctx.divide(gradient[j], n), ctx.multiply(_LAMBDA, beta[j]))
            for k in range(j + 1):
                value = ctx.divide(hessian[j][k], n)
                if j == k:
                    value = ctx.add(value, _LAMBDA)
                hessian[j][k] = value
                hessian[k][j] = value
        norm = ctx.sqrt(dot(gradient, gradient))
        if norm <= threshold:
            return {'beta_decimal': [str(v) for v in beta], 'beta': np.asarray([float(v) for v in beta]), 'objective_decimal': str(objective(beta)), 'gradient_norm_decimal': str(norm), 'iterations': iteration, 'precision_decimal_digits': precision, 'method': 'independent Decimal Newton/Cholesky, all coefficients penalized, zero initialization'}
        lower = [[_ZERO] * d for _ in range(d)]
        for j in range(d):
            for k in range(j + 1):
                subtotal = dot(lower[j][:k], lower[k][:k])
                remainder = ctx.subtract(hessian[j][k], subtotal)
                if j == k:
                    if remainder <= 0:
                        raise VerificationError('independent reference Cholesky failed')
                    lower[j][k] = ctx.sqrt(remainder)
                else:
                    lower[j][k] = ctx.divide(remainder, lower[k][k])
        temporary = [_ZERO] * d
        for j in range(d):
            temporary[j] = ctx.divide(ctx.subtract(gradient[j].copy_negate(), dot(lower[j][:j], temporary[:j])), lower[j][j])
        step = [_ZERO] * d
        for j in range(d - 1, -1, -1):
            subtotal = dot([lower[k][j] for k in range(j + 1, d)], step[j + 1:])
            step[j] = ctx.divide(ctx.subtract(temporary[j], subtotal), lower[j][j])
        old = objective(beta)
        directional = dot(gradient, step)
        amount = _ONE
        for _ in range(61):
            proposal = [ctx.add(b, ctx.multiply(amount, s)) for b, s in zip(beta, step)]
            armijo = ctx.add(old, ctx.multiply(Decimal('0.0001'), ctx.multiply(amount, directional)))
            if objective(proposal) <= armijo:
                beta = proposal
                break
            amount = ctx.divide(amount, _TWO)
        else:
            raise VerificationError('independent reference line-search cap reached')
    raise VerificationError('independent reference iteration cap reached')


def compare_reference_fit(X, targets, fitted, *, exact_design=None, exact_targets=None, evaluation_X=None, evaluation_exact_design=None, evaluation_y=None):
    beta = np.asarray(fitted.beta if hasattr(fitted, 'beta') else fitted['beta'], dtype=np.float64)
    reference = reference_fit(X, targets, exact_design=exact_design, exact_targets=exact_targets)
    discrepancy = float(np.max(np.abs(beta - reference['beta'])))
    fitted_gradient = gradient_enclosure(X, beta, targets, exact_design=exact_design, exact_targets=exact_targets)
    fitted_prob, _ = certified_probabilities(X, beta, exact_design=exact_design)
    reference_prob, _ = certified_probabilities(X, reference['beta'], exact_design=exact_design)
    probability_discrepancy = float(np.max(np.abs(fitted_prob - reference_prob)))
    # Objective difference measured independently using exact Decimal values.
    ctx = Context(prec=70, rounding=ROUND_HALF_EVEN)
    prepared = prepare_exact_design(X, exact_design)
    exact = targets if exact_targets is None else exact_targets
    total = _ZERO
    for row, label in zip(prepared.exact_rows, exact):
        z = _ZERO
        for x, b in zip(row, beta):
            z = ctx.add(z, ctx.multiply(_decimal_value(x, ctx), Decimal.from_float(float(b))))
        softplus = ctx.add(max(z, _ZERO), ctx.ln(ctx.add(_ONE, ctx.exp(z.copy_abs().copy_negate()))))
        total = ctx.add(total, ctx.subtract(softplus, ctx.multiply(_decimal_value(label, ctx), z)))
    penalty = _ZERO
    for b in beta:
        db = Decimal.from_float(float(b))
        penalty = ctx.add(penalty, ctx.multiply(db, db))
    objective = ctx.add(ctx.divide(total, Decimal(len(prepared.rows))), ctx.multiply(Decimal('0.05'), penalty))
    objective_discrepancy = float(ctx.subtract(objective, Decimal(reference['objective_decimal'])).copy_abs())
    loss_discrepancy = 0.0
    if evaluation_X is not None:
        if evaluation_y is None:
            raise VerificationError('reference evaluation requires read-only truth')
        q, _ = certified_probabilities(evaluation_X, beta, exact_design=evaluation_exact_design)
        r, _ = certified_probabilities(evaluation_X, reference['beta'], exact_design=evaluation_exact_design)
        y = np.asarray(evaluation_y, dtype=np.float64)
        loss_discrepancy = abs(float(np.mean((q - y) ** 2)) - float(np.mean((r - y) ** 2)))
    passed = max(discrepancy, probability_discrepancy, objective_discrepancy, loss_discrepancy) <= 1e-10 and fitted_gradient['accepted']
    if not passed:
        raise VerificationError('independent high-precision fit qualification failed')
    return {'schema': 'mra-phase7c-independent-fit-check/1.0', 'coefficient_max_abs_difference': discrepancy, 'probability_max_abs_difference': probability_discrepancy, 'objective_absolute_difference': objective_discrepancy, 'brier_absolute_difference': loss_discrepancy, 'gradient_norm_upper': fitted_gradient['norm_upper'], 'gradient_arithmetic_uncertainty_upper': fitted_gradient['arithmetic_uncertainty_upper'], 'reference_gradient_norm_decimal': reference['gradient_norm_decimal'], 'reference_precision_decimal_digits': 70, 'passed': True}


def verify_actual_reference(reference_payload):
    """Actual source reference-trial checks; invoked only after runtime freeze."""
    checks = []
    fits = reference_payload.get('fits', [])
    if not fits:
        raise VerificationError('reference replication-0 fit payload absent')
    expected = {(route, cohort) for route in ('candidate', 'independent_rr', 'clean_matched_logistic') for cohort in ('validation', 'final')}
    for ordinal in range(2011*12, 2019*12+6):
        year, month = divmod(ordinal,12)
        expected.add(('clean_expanding_logistic', f'mas:monthly-total-card-billings:{year:04}-{month+1:02}'))
    identities = [(fit.get('route'),fit.get('cohort')) for fit in fits]
    if len(identities) != 108 or len(set(identities)) != 108 or set(identities) != expected:
        raise VerificationError('all108 mandatory reference and clean origin fits required')
    for fit in fits:
        if fit['cohort'] in ('validation','final'):
            train_count, evaluation_count = (238,56) if fit['cohort'] == 'validation' else (294,46)
        else:
            year, month = map(int,fit['cohort'].rsplit(':',1)[1].split('-'))
            train_count, evaluation_count = year*12+month-1-(1991*12+2), 1
        if len(fit['X']) != train_count or len(fit.get('evaluation_X',())) != evaluation_count:
            raise VerificationError('mandatory reference fit chronology differs')
        certified, certificate = certified_probabilities(fit['evaluation_X'],fit['beta'],exact_design=fit.get('evaluation_exact_design'))
        if 'probabilities' not in fit or not np.array_equal(certified,np.asarray(fit['probabilities'],dtype=np.float64)):
            raise VerificationError('captured reference predictions differ from independently certified model')
        check = compare_reference_fit(fit['X'], fit['targets'], {'beta': fit['beta']}, exact_design=fit.get('exact_design'), exact_targets=fit.get('exact_targets'), evaluation_X=fit.get('evaluation_X'), evaluation_exact_design=fit.get('evaluation_exact_design'), evaluation_y=fit.get('evaluation_y'))
        check['route'] = fit.get('route')
        check['cohort'] = fit.get('cohort')
        checks.append(check)
    slots = reference_payload.get('slots')
    aggregate = verify_mandatory_results(slots) if slots is not None else None
    result = {'schema': 'mra-phase7c-independent-actual-reference/1.0', 'independent_verified': True, 'reference_replication': 0, 'fit_checks': checks, 'mandatory_results': aggregate, 'passed': all(check['passed'] for check in checks)}
    return result



def synthetic_fixtures():
    """Fixed, public, source-independent fixtures; no seeded search or draws."""
    fixtures = []
    rows, exact, labels = [], [], []
    for i in range(24):
        row = [Fraction(0)] * 29
        row[0], row[1] = Fraction(1), Fraction(i % 15, 30)
        row[2 + i % 12], row[14 + i % 15] = Fraction(1), Fraction(1)
        exact.append(tuple(row))
        rows.append([float(value) for value in row])
        labels.append(Fraction(17, 14) if (i % 3) else Fraction(-3, 14))
    fixtures.append(('decoded_outside_unit_interval', np.asarray(rows), tuple(exact), tuple(labels)))
    exact = []
    for i in range(20):
        row = [Fraction(0)] * 29
        row[0], row[1], row[2], row[3] = Fraction(1), Fraction(1, 2), Fraction(1, 2), Fraction(1, 2)
        row[4] = Fraction(i % 2, 2)
        exact.append(tuple(row))
    fixtures.append(('constant_and_collinear_columns', np.asarray([[float(v) for v in row] for row in exact]), tuple(exact), tuple(Fraction(3, 2) if i % 4 else Fraction(-1, 2) for i in range(20))))
    exact = []
    extremes = (Decimal('1e-300'), Decimal('-1e-300'), Decimal('1.5'), Decimal('-1.5'))
    for i in range(16):
        row = [Decimal(0)] * 29
        row[0], row[1], row[2], row[3] = Decimal(1), extremes[i % 4], Decimal('1e-150'), Decimal('0.5')
        exact.append(tuple(row))
    fixtures.append(('extreme_finite_covariates', np.asarray([[float(v) for v in row] for row in exact]), tuple(exact), tuple(Fraction(i % 2) for i in range(16))))
    return tuple(fixtures)


def qualify_synthetic(*, runtime_sha256):
    """Qualification envelope bound to supplied external frozen runtime hash."""
    from .numerics import fit_logistic, objective_gradient_hessian, arithmetic_error_account
    import time
    start = time.perf_counter()
    checks = []
    blocking = []
    proof = formal_gain_error_accounting()
    for name, X, exact, labels in synthetic_fixtures():
        try:
            y = np.asarray([float(v) for v in labels])
            fitted = fit_logistic(X, y, exact_design=exact, exact_targets=labels)
            check = compare_reference_fit(X, y, fitted, exact_design=exact, exact_targets=labels, evaluation_X=X, evaluation_exact_design=exact, evaluation_y=np.asarray([i % 2 for i in range(len(X))]))
            _, float_gradient, _ = objective_gradient_hessian(X, fitted.beta, y)
            enclosure = gradient_enclosure(X, fitted.beta, y, exact_design=exact, exact_targets=labels)
            component_difference = 0.0
            for value, (lower, upper) in zip(float_gradient, enclosure['component_intervals']):
                midpoint = _NEAR.divide(_NEAR.add(Decimal(lower), Decimal(upper)), _TWO)
                component_difference = max(component_difference, float(_NEAR.subtract(Decimal.from_float(float(value)), midpoint).copy_abs()))
            if component_difference > 1e-10:
                raise VerificationError('independent gradient discrepancy exceeds1e-10')
            check.update(fixture=name, gradient_max_abs_difference=component_difference, source_derived=False)
            checks.append(check)
        except Exception as exc:
            blocking.append({'fixture': name, 'error': type(exc).__name__, 'message': str(exc)})
    return {
        'schema': 'mra-phase7c-numerical-qualification/1.0',
        'passed': not blocking and len(checks) == 3,
        'scientific_specification_sha256': '93a124607498c5cec6a93d06b4e3648094b683983ae59518a7fd22169a62d915',
        'execution_contract_sha256': 'f40128dfe794a9cd7ef8a95e1a09fb3cc17e53c3cc2cf47d216cad6742f0d159',
        'runtime_sha256': runtime_sha256,
        'source_outcomes_derived': False,
        'synthetic_only': True,
        'formal_total_gain_error_upper': proof['formal_total_gain_error_upper'],
        'gradient_arithmetic_uncertainty_upper': max((check['gradient_arithmetic_uncertainty_upper'] for check in checks), default=0.0),
        'blocking_issues': blocking,
        'independent_reference_fixtures': checks,
        'formal_error_account': proof,
        'numerical_implementation_account': arithmetic_error_account(),
        'wall_seconds': time.perf_counter() - start,
        'independent_agent': '/root/phase7c_verify',
        'no_agency_acceptance': True,
        'no_protected_release_authority': True,
    }




