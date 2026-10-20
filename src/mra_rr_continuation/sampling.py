"""Exact conditional sampling for one verified retained-RR block.

This research kernel does not reserve an authoritative complete history or
provide a production-private execution boundary. Repeated blocks for the same
unit require a new complete-law/accounting argument. No secrets or internal
correctness strata are included in returned samples.
"""
from __future__ import annotations

from fractions import Fraction
from itertools import product
from math import comb, lcm
import secrets
from threading import RLock
from typing import Callable

from .certificates import (
    RRParameters, ResearchContext, verify_certificate,
)

MAX_TICKET_BITS = 32768
MAX_ENUMERATION_R = 8


class SamplingError(ValueError):
    """Invalid input, redraw, or random-source failure in the one-block kernel."""


def _validate_bits(labels: object, retained_response: object, r: int) -> tuple[int, ...]:
    if not isinstance(labels, (tuple, list)) or len(labels) != r + 1:
        raise SamplingError("A complete preexisting label vector is required")
    if any(type(bit) is not int or bit not in (0, 1) for bit in labels):
        raise SamplingError("Labels must be integer binary values")
    if type(retained_response) is not int or retained_response not in (0, 1):
        raise SamplingError("The actual retained response must be an integer binary value")
    return tuple(labels)


def _integer_weights(probabilities: tuple[Fraction, ...]) -> tuple[tuple[int, ...], int]:
    denominator = 1
    for probability in probabilities:
        denominator = lcm(denominator, probability.denominator)
        if denominator.bit_length() > MAX_TICKET_BITS:
            raise SamplingError("Exact sampling exceeds the integer-ticket resource limit")
    weights = tuple(p.numerator * (denominator // p.denominator) for p in probabilities)
    if any(weight <= 0 for weight in weights) or sum(weights) != denominator:
        raise SamplingError("The verified conditional law is not normalized")
    return weights, denominator


def _unrank_subset(r: int, h: int, rank: int) -> tuple[int, ...]:
    """Lexicographic uniform h-subset without enumerating the binary cube."""
    chosen: list[int] = []
    remaining = h
    for index in range(r):
        if remaining == 0:
            break
        count = comb(r - index - 1, remaining - 1)
        if rank < count:
            chosen.append(index)
            remaining -= 1
        else:
            rank -= count
    if remaining or rank:
        raise SamplingError("Invalid uniform subset rank")
    return tuple(chosen)


class ConditionalSampler:
    """Verified one-block sampler with a default OS-backed random source.

    ``randbelow`` injection is for explicit deterministic tests only. The
    default is ``secrets.randbelow``; no floating-point probabilities or
    seeded global PRNG are used. Each public record ID is reserved once per
    instance, including after a random-source failure. This is an in-memory
    guard, not a durable ledger or proof of institutional source authenticity.
    """
    __slots__ = ("_verified", "_weights", "_randbelow", "_digest", "_used", "_lock")

    def __init__(
        self,
        document: object,
        *,
        expected_parameters: RRParameters,
        expected_context: ResearchContext,
        expected_certificate_sha256: str | None = None,
        randbelow: Callable[[int], int] | None = None,
    ) -> None:
        # Reverify raw certificate against external expectations; accepting a
        # caller-constructed verification flag would not bind this execution.
        verified = verify_certificate(
            document,
            expected_parameters=expected_parameters,
            expected_context=expected_context,
            expected_certificate_sha256=expected_certificate_sha256,
        )
        if verified.claim == "infeasible" or verified.shells is None:
            raise SamplingError("An infeasible certificate cannot be sampled")
        self._verified = verified
        p0 = verified.parameters.d / (1 + verified.parameters.d)
        probabilities = (p0, 1 - p0)
        self._weights = tuple(
            _integer_weights(tuple(
                Fraction(comb(verified.parameters.r, h)) * mass / probabilities[b]
                for h, mass in enumerate(verified.shells[b])
            )) for b in (0, 1)
        )
        if randbelow is not None and not callable(randbelow):
            raise SamplingError("The test random source must be callable")
        self._randbelow = secrets.randbelow if randbelow is None else randbelow
        self._digest = verified.digest
        self._used: set[str] = set()
        self._lock = RLock()

    @property
    def certificate_sha256(self) -> str:
        return self._digest

    @property
    def parameters(self) -> RRParameters:
        return self._verified.parameters

    def _draw(self, bound: int) -> int:
        try:
            value = self._randbelow(bound)
        except Exception:
            raise SamplingError("The random source failed; this record remains reserved") from None
        if type(value) is not int or not 0 <= value < bound:
            raise SamplingError("The random source returned an invalid integer")
        return value

    def sample(
        self, labels: tuple[int, ...] | list[int], retained_response: int, *, record_id: str,
    ) -> tuple[int, ...]:
        """Return fresh randomized labels, keeping the retained response unchanged.

        Caller must supply truthful preexisting labels and retained response
        provenance under the externally registered context. Record identifiers
        and the block schedule must be fixed public inputs. No raw label,
        error-stratum flag, shell index, seed or random tape is returned.
        """
        bits = _validate_bits(labels, retained_response, self.parameters.r)
        if type(record_id) is not str or not record_id or len(record_id) > 256:
            raise SamplingError("A bounded public record identifier is required")
        with self._lock:
            if record_id in self._used:
                raise SamplingError("This record already has a draw reserved in the block")
            self._used.add(record_id)
            weights, total = self._weights[bits[0] ^ retained_response]
            ticket = self._draw(total)
            h = 0
            for h, weight in enumerate(weights):
                if ticket < weight:
                    break
                ticket -= weight
            choices = comb(self.parameters.r, h)
            rank = 0 if choices == 1 else self._draw(choices)
            flipped = set(_unrank_subset(self.parameters.r, h, rank))
            return tuple(bit ^ int(index in flipped) for index, bit in enumerate(bits[1:]))

    def conditional_distribution(
        self, labels: tuple[int, ...] | list[int], retained_response: int,
    ) -> tuple[tuple[tuple[int, ...], Fraction], ...]:
        """Operator-only exact small-domain test aid; never a recipient output.

        This inspection accesses protected inputs. It is not a DP release and
        is intentionally absent from the sampling CLI. Enumeration is bounded
        to r<=8; actual sampling remains compact through r=128.
        """
        bits = _validate_bits(labels, retained_response, self.parameters.r)
        if self.parameters.r > MAX_ENUMERATION_R:
            raise SamplingError("Analytical enumeration exceeds the test-aid limit")
        b = bits[0] ^ retained_response
        p0 = self.parameters.d / (1 + self.parameters.d)
        pb = p0 if b == 0 else 1 - p0
        return tuple(
            (fresh, self._verified.shells[b][sum(a != x for a, x in zip(fresh, bits[1:]))] / pb)
            for fresh in product((0, 1), repeat=self.parameters.r)
        )
