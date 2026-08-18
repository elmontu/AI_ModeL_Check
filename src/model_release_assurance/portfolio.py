from __future__ import annotations

import json
from collections.abc import Mapping, Sequence


def joint_observations(releases: Sequence[Mapping[str, str]]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not releases:
        raise ValueError("at least one release is required")
    candidate_sets = [set(release) for release in releases]
    if any(candidates != candidate_sets[0] for candidates in candidate_sets[1:]):
        raise ValueError("all releases must cover exactly the same candidate identifiers")
    candidate_ids = tuple(sorted(candidate_sets[0]))
    observations = tuple(
        json.dumps(tuple(release[candidate] for release in releases), separators=(",", ":"))
        for candidate in candidate_ids
    )
    return candidate_ids, observations


def joint_uniform_linkage_value(releases: Sequence[Mapping[str, str]]) -> float:
    _, observations = joint_observations(releases)
    if not observations:
        raise ValueError("candidate set cannot be empty")
    return len(set(observations)) / len(observations)


def joint_uniform_secret_guess_value(
    secret_by_candidate: Mapping[str, str],
    releases: Sequence[Mapping[str, str]],
) -> float:
    """Exact Bayes success for a finite secret under the joint release transcript."""
    candidate_ids, observations = joint_observations(releases)
    if set(secret_by_candidate) != set(candidate_ids):
        raise ValueError("secret mapping and release candidate sets must match exactly")
    cells: dict[str, dict[str, int]] = {}
    for candidate, observation in zip(candidate_ids, observations, strict=True):
        secret_counts = cells.setdefault(observation, {})
        secret = secret_by_candidate[candidate]
        secret_counts[secret] = secret_counts.get(secret, 0) + 1
    return sum(max(counts.values()) for counts in cells.values()) / len(candidate_ids)
