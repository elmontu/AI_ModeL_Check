"""Exact, scoped certificates for retained binary randomized-response continuation.

This separate research package has no MRAP registration or release-authority
side effect. Its mathematical results are conditional on the bound declarations;
source authenticity, applicability, retained-history completeness and deployment
conformance are not established by hashing or exact arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from math import comb
import re
from typing import Any

SCHEMA = "mra-retained-rr-shell-certificate/1.0"
SOURCE_PDF_SHA256 = "f1f8207831a94365a21ec152ef5e77b3d199e44aa3c2eb79f2e49b17a2f50f21"
MAX_R = 128
MAX_JSON_BYTES = 524288
_MAX_RATIONAL_DIGITS = 2048
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RATIONAL = re.compile(r"-?(?:0|[1-9][0-9]*)/[1-9][0-9]*\Z")


class CertificateError(ValueError):
    """Malformed, unbound, unsupported or mathematically invalid evidence."""


def _fraction(value: Any, name: str) -> Fraction:
    if type(value) is int:
        value = Fraction(value)
    if type(value) is not Fraction:
        raise CertificateError(f"{name} must be an exact Fraction or integer")
    if abs(value.numerator).bit_length() > 7000 or value.denominator.bit_length() > 7000:
        raise CertificateError(f"{name} exceeds the exact input size limit")
    if len(str(abs(value.numerator))) > _MAX_RATIONAL_DIGITS or len(str(value.denominator)) > _MAX_RATIONAL_DIGITS:
        raise CertificateError(f"{name} exceeds the exact input size limit")
    return value


def rational_string(value: Fraction) -> str:
    """Canonical rational wire format, including the denominator for integers."""
    value = _fraction(value, "rational")
    return f"{value.numerator}/{value.denominator}"


def _parse_rational(value: Any, name: str) -> Fraction:
    if type(value) is not str or len(value) > 2 * _MAX_RATIONAL_DIGITS + 2 or not _RATIONAL.fullmatch(value):
        raise CertificateError(f"{name} must be a canonical rational string")
    try:
        numerator, denominator = value.split("/")
        result = _fraction(Fraction(int(numerator), int(denominator)), name)
    except (ValueError, ZeroDivisionError) as exc:
        raise CertificateError(f"invalid rational in {name}") from exc
    if rational_string(result) != value:
        raise CertificateError(f"{name} is not normalized")
    return result


def _keys(value: Any, expected: set[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise CertificateError(f"{name} requires exactly {sorted(expected)}")
    return value


def _sha(value: Any, name: str) -> str:
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise CertificateError(f"{name} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True)
class RRParameters:
    r: int
    d: Fraction
    L: Fraction
    tau: Fraction

    def __post_init__(self) -> None:
        if type(self.r) is not int or not 1 <= self.r <= MAX_R:
            raise CertificateError(f"r must be an integer in [1,{MAX_R}]")
        for name in ("d", "L", "tau"):
            object.__setattr__(self, name, _fraction(getattr(self, name), name))
        if not 1 <= self.d <= self.L:
            raise CertificateError("parameters require 1 <= d <= L")
        if not 0 <= self.tau <= 1:
            raise CertificateError("tau must be in [0,1]")

    @property
    def stratum_probabilities(self) -> tuple[Fraction, Fraction]:
        return self.d / (1 + self.d), Fraction(1) / (1 + self.d)

    def to_dict(self) -> dict[str, Any]:
        return {"r": self.r, "d": rational_string(self.d), "L": rational_string(self.L), "tau": rational_string(self.tau)}

    @classmethod
    def from_dict(cls, value: Any) -> RRParameters:
        value = _keys(value, {"r", "d", "L", "tau"}, "parameters")
        return cls(value["r"], *(_parse_rational(value[name], name) for name in ("d", "L", "tau")))


@dataclass(frozen=True)
class ResearchContext:
    """Externally registered identities and explicitly unverified premises.

    Digests bind content identity only. The caller must supply the expected
    context from its registration, rather than accepting the document's copy.
    """
    retained_law_sha256: str
    retained_response_sha256: str
    complete_history_sha256: str
    request_plan_sha256: str
    source_pdf_sha256: str = SOURCE_PDF_SHA256
    full_binary_cube: bool = True
    full_vector_replacement: bool = True
    preexisting_labels: bool = True
    public_fixed_features_membership_linkage: bool = True
    public_fixed_requests: bool = True

    def __post_init__(self) -> None:
        for name in ("retained_law_sha256", "retained_response_sha256", "complete_history_sha256", "request_plan_sha256", "source_pdf_sha256"):
            _sha(getattr(self, name), name)
        if self.source_pdf_sha256 != SOURCE_PDF_SHA256:
            raise CertificateError("this profile binds the reviewed v34 source PDF only")
        for name in ("full_binary_cube", "full_vector_replacement", "preexisting_labels", "public_fixed_features_membership_linkage", "public_fixed_requests"):
            if getattr(self, name) is not True:
                raise CertificateError(f"unsupported applicability declaration: {name}")

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, value: Any) -> ResearchContext:
        return cls(**_keys(value, set(cls.__dataclass_fields__), "context"))


@dataclass(frozen=True)
class ReducedFrontier:
    lower: Fraction
    upper: Fraction
    zero_slope_failure: bool
    maximum_marginal_accuracy: Fraction | None

    @property
    def feasible(self) -> bool:
        return not self.zero_slope_failure and self.lower <= self.upper

    def to_dict(self) -> dict[str, Any]:
        return {
            "lower": rational_string(self.lower),
            "upper": rational_string(self.upper),
            "zero_slope_failure": self.zero_slope_failure,
            "maximum_marginal_accuracy": None if self.maximum_marginal_accuracy is None else rational_string(self.maximum_marginal_accuracy),
        }

    @classmethod
    def from_dict(cls, value: Any) -> ReducedFrontier:
        value = _keys(value, {"lower", "upper", "zero_slope_failure", "maximum_marginal_accuracy"}, "frontier")
        if type(value["zero_slope_failure"]) is not bool:
            raise CertificateError("zero_slope_failure must be a boolean")
        maximum = value["maximum_marginal_accuracy"]
        return cls(_parse_rational(value["lower"], "lower"), _parse_rational(value["upper"], "upper"), value["zero_slope_failure"], None if maximum is None else _parse_rational(maximum, "maximum_marginal_accuracy"))


@dataclass(frozen=True)
class VerifiedCertificate:
    parameters: RRParameters
    context: ResearchContext
    claim: str
    m: Fraction | None
    shells: tuple[tuple[Fraction, ...], tuple[Fraction, ...]] | None
    conditional_accuracies: tuple[Fraction, Fraction] | None
    marginal_accuracy: Fraction | None
    frontier: ReducedFrontier | None
    digest: str
    canonical_json: str

    @property
    def status(self) -> str:
        return self.claim

    @property
    def release_authorized(self) -> bool:
        return False

    @property
    def authorization_effect(self) -> str:
        return "none"

    @property
    def premises_independently_verified(self) -> bool:
        return False


def _envelopes(parameters: RRParameters) -> tuple[tuple[int, ...], tuple[Fraction, ...]]:
    r, L = parameters.r, parameters.L
    counts = tuple(comb(r, h) for h in range(r + 1))
    slopes = tuple((L * sum(counts[h] * (k - h) for h in range(k)) - sum(counts[h] * (h - k) for h in range(k + 1, r + 1))) / r for k in range(r + 1))
    return counts, slopes


def _success_envelope(p: Fraction, m: Fraction, r: int, slopes: tuple[Fraction, ...]) -> Fraction:
    return min(p * Fraction(r - k, r) + slope * m for k, slope in enumerate(slopes))


def _frontier(parameters: RRParameters) -> tuple[ReducedFrontier, Fraction | None]:
    """Replay all floor halfspaces and scan every envelope fill breakpoint.

    Row fill transitions occur at p_b/(N+(L-1)*C_h). Between the
    transitions both envelopes are affine, so interval endpoints suffice.
    This is O(r^2) rational operations and O(r) retained shell storage;
    integer bit complexity and process memory are not included.
    """
    r, L = parameters.r, parameters.L
    counts, slopes = _envelopes(parameters)
    p0, p1 = parameters.stratum_probabilities
    N = 1 << r
    lower, upper = p0 / (N * L), p1 / N
    zero_failure = False
    for p in (p0, p1):
        for k, slope in enumerate(slopes):
            required = p * (parameters.tau - Fraction(r - k, r))
            if slope > 0:
                lower = max(lower, required / slope)
            elif slope < 0:
                upper = min(upper, required / slope)
            elif required > 0:
                zero_failure = True
    if zero_failure or lower > upper:
        return ReducedFrontier(lower, upper, zero_failure, None), None
    candidates = {lower, upper}
    cumulative = 0
    for h in range(r):
        cumulative += counts[h]
        for p in (p0, p1):
            point = p / (N + (L - 1) * cumulative)
            if lower <= point <= upper:
                candidates.add(point)
    best_m = min(candidates)
    maximum = _success_envelope(p0, best_m, r, slopes) + _success_envelope(p1, best_m, r, slopes)
    for m in sorted(candidates):
        value = _success_envelope(p0, m, r, slopes) + _success_envelope(p1, m, r, slopes)
        if value > maximum:
            maximum, best_m = value, m
    return ReducedFrontier(lower, upper, False, maximum), best_m


def reduced_frontier(parameters: RRParameters) -> ReducedFrontier:
    """Exact analysis under the declared shell theorem; not release authority."""
    if type(parameters) is not RRParameters:
        raise CertificateError("parameters must be RRParameters")
    return _frontier(parameters)[0]


def _fill(parameters: RRParameters, m: Fraction) -> tuple[tuple[Fraction, ...], tuple[Fraction, ...]]:
    counts = tuple(comb(parameters.r, h) for h in range(parameters.r + 1))
    rows = []
    for p in parameters.stratum_probabilities:
        residual = p - (1 << parameters.r) * m
        row = []
        for count in counts:
            extra = min(count * (parameters.L - 1) * m, max(Fraction(0), residual))
            row.append(m + extra / count)
            residual -= extra
        if residual != 0:
            raise CertificateError("internal exact fill did not preserve the retained row")
        rows.append(tuple(row))
    return rows[0], rows[1]


def _accuracy(parameters: RRParameters, shells: tuple[tuple[Fraction, ...], tuple[Fraction, ...]]) -> tuple[tuple[Fraction, Fraction], Fraction]:
    successes = tuple(sum((Fraction(comb(parameters.r, h) * (parameters.r - h), parameters.r) * q for h, q in enumerate(row)), Fraction(0)) for row in shells)
    p0, p1 = parameters.stratum_probabilities
    return (successes[0] / p0, successes[1] / p1), successes[0] + successes[1]


def build_certificate(parameters: RRParameters, context: ResearchContext, claim: str = "optimal") -> dict[str, Any]:
    """Build a replayable exact shell witness, or an empty-interval proof.

    'feasible' deliberately omits optimality evidence. If the registered floor
    is impossible under this theorem, either requested kind returns infeasible.
    """
    if type(parameters) is not RRParameters or type(context) is not ResearchContext:
        raise CertificateError("builder requires typed parameters and context")
    if claim not in ("feasible", "optimal"):
        raise CertificateError("builder claim must be feasible or optimal")
    frontier, m = _frontier(parameters)
    witness = None
    if m is None:
        status = "infeasible"
    else:
        status = claim
        shells = _fill(parameters, m)
        conditional, marginal = _accuracy(parameters, shells)
        witness = {"m": rational_string(m), "shell_masses": [[rational_string(q) for q in row] for row in shells], "conditional_accuracies": [rational_string(q) for q in conditional], "marginal_accuracy": rational_string(marginal)}
    return {"schema": SCHEMA, "parameters": parameters.to_dict(), "context": context.to_dict(), "status": status, "witness": witness, "frontier": None if status == "feasible" else frontier.to_dict(), "premise_status": "declared_not_independently_verified", "authorization_effect": "none"}


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CertificateError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _bad_constant(value: str) -> None:
    raise CertificateError(f"nonfinite JSON value: {value}")


def _load(document: dict[str, Any] | str | bytes) -> dict[str, Any]:
    try:
        if type(document) is dict:
            encoded = json.dumps(document, allow_nan=False, ensure_ascii=True, separators=(",", ":"))
        elif type(document) is bytes:
            encoded = document.decode("utf-8", errors="strict")
        elif type(document) is str:
            encoded = document
        else:
            raise CertificateError("certificate must be a JSON object, UTF-8 bytes or text")
        if len(encoded.encode("utf-8")) > MAX_JSON_BYTES:
            raise CertificateError("certificate exceeds the JSON size limit")
        value = json.loads(encoded, object_pairs_hook=_object_pairs, parse_constant=_bad_constant)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise CertificateError(f"invalid certificate JSON: {exc}") from exc
    return _keys(value, {"schema", "parameters", "context", "status", "witness", "frontier", "premise_status", "authorization_effect"}, "certificate")


def _parse(document: dict[str, Any] | str | bytes) -> tuple[dict[str, Any], RRParameters, ResearchContext, str, Any, ReducedFrontier | None]:
    value = _load(document)
    if value["schema"] != SCHEMA or value["premise_status"] != "declared_not_independently_verified" or value["authorization_effect"] != "none":
        raise CertificateError("unsupported schema, premise status or authority claim")
    parameters = RRParameters.from_dict(value["parameters"])
    context = ResearchContext.from_dict(value["context"])
    status = value["status"]
    if type(status) is not str or status not in ("feasible", "optimal", "infeasible"):
        raise CertificateError("unsupported certificate status")
    frontier = None if value["frontier"] is None else ReducedFrontier.from_dict(value["frontier"])
    if (status == "feasible") != (frontier is None):
        raise CertificateError("only feasible-only certificates omit the exact frontier")
    witness = value["witness"]
    if status == "infeasible":
        if witness is not None:
            raise CertificateError("infeasible certificates must have a null witness")
        parsed_witness = None
    else:
        witness = _keys(witness, {"m", "shell_masses", "conditional_accuracies", "marginal_accuracy"}, "witness")
        raw_rows, raw_conditional = witness["shell_masses"], witness["conditional_accuracies"]
        if type(raw_rows) is not list or len(raw_rows) != 2 or any(type(row) is not list or len(row) != parameters.r + 1 for row in raw_rows):
            raise CertificateError("shell_masses must contain exactly two rows of r+1 entries")
        if type(raw_conditional) is not list or len(raw_conditional) != 2:
            raise CertificateError("conditional_accuracies must contain exactly two entries")
        rows = tuple(tuple(_parse_rational(q, "shell mass") for q in row) for row in raw_rows)
        conditional = tuple(_parse_rational(q, "conditional accuracy") for q in raw_conditional)
        parsed_witness = (_parse_rational(witness["m"], "m"), rows, conditional, _parse_rational(witness["marginal_accuracy"], "marginal_accuracy"))
    return value, parameters, context, status, parsed_witness, frontier


def certificate_json(document: dict[str, Any] | str | bytes) -> str:
    """Canonical structurally valid JSON; this alone is not mathematical replay."""
    value = _parse(document)[0]
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def certificate_digest(document: dict[str, Any] | str | bytes) -> str:
    """Domain-separated digest of the canonical versioned certificate."""
    return hashlib.sha256(SCHEMA.encode("ascii") + b"\0" + certificate_json(document).encode("utf-8")).hexdigest()


def verify_certificate(document: dict[str, Any] | str | bytes, *, expected_parameters: RRParameters, expected_context: ResearchContext, expected_certificate_sha256: str | None = None) -> VerifiedCertificate:
    """Replay without trusting the submitted law, frontier or context claims.

    Expected registration bindings are mandatory. The optional externally
    retained digest additionally refuses a changed certificate. Neither input
    declarations nor content-addressing prove the premises true in deployment.
    Invalid or missing evidence raises; it is never reported as infeasibility.
    """
    if type(expected_parameters) is not RRParameters or type(expected_context) is not ResearchContext:
        raise CertificateError("expected parameters and context must be externally supplied typed registrations")
    value, parameters, context, status, witness, frontier = _parse(document)
    if parameters != expected_parameters or context != expected_context:
        raise CertificateError("certificate does not match the expected registered parameters and context")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    digest = hashlib.sha256(SCHEMA.encode("ascii") + b"\0" + canonical.encode("utf-8")).hexdigest()
    if expected_certificate_sha256 is not None and digest != _sha(expected_certificate_sha256, "expected_certificate_sha256"):
        raise CertificateError("certificate digest differs from the expected retained identity")
    if status != "feasible":
        replayed = _frontier(parameters)[0]
        if frontier != replayed:
            raise CertificateError("submitted frontier does not match independent exact replay")
        if status == "infeasible":
            if replayed.feasible:
                raise CertificateError("infeasibility claim has a nonempty feasible interval")
            return VerifiedCertificate(parameters, context, status, None, None, None, None, frontier, digest, canonical)
        if not replayed.feasible:
            raise CertificateError("claimed optimal law has an empty feasible interval")
    m, shells, conditional, marginal = witness
    p0, p1 = parameters.stratum_probabilities
    N = 1 << parameters.r
    if m <= 0 or not p0 / (N * parameters.L) <= m <= p1 / N:
        raise CertificateError("positive common privacy-box bound is outside the retained-row interval")
    for p, row in zip((p0, p1), shells):
        if any(q <= 0 or not m <= q <= parameters.L * m for q in row):
            raise CertificateError("shell mass violates the common positive privacy box")
        if sum((comb(parameters.r, h) * q for h, q in enumerate(row)), Fraction(0)) != p:
            raise CertificateError("multiplicity-weighted shell row does not preserve the retained law")
    computed_conditional, computed_marginal = _accuracy(parameters, shells)
    if conditional != computed_conditional or marginal != computed_marginal:
        raise CertificateError("claimed accuracy does not equal exact multiplicity-weighted replay")
    if any(accuracy < parameters.tau for accuracy in computed_conditional):
        raise CertificateError("one or both old-error strata violate the registered conditional floor")
    if status == "optimal" and marginal != frontier.maximum_marginal_accuracy:
        raise CertificateError("feasible law does not attain the independently replayed optimum")
    return VerifiedCertificate(parameters, context, status, m, shells, computed_conditional, computed_marginal, frontier, digest, canonical)
