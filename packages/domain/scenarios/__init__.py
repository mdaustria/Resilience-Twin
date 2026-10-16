"""Review structured scenario targets and derive independent seeded draws."""

import hashlib
from dataclasses import asdict

from packages.contracts.checkpoints import canonical_json
from packages.contracts.scenarios import (
    Scenario,
    ScenarioEvent,
    ScenarioSuite,
    SuiteMember,
)

GENERATOR_VERSION = "sha256_entity_draw_v1"


def validate_scenario(
    scenario: Scenario, *, edge_ids: frozenset[str], asset_ids: frozenset[str],
    vehicle_ids: frozenset[str], shelter_ids: frozenset[str],
) -> None:
    targets = {"edge_closed": edge_ids, "asset_closed": asset_ids,
               "vehicle_outage": vehicle_ids, "shelter_capacity": shelter_ids}
    for event in scenario.events:
        if event.effect not in targets or event.target_id not in targets[event.effect]:
            raise ValueError(f"invalid scenario target: {event.id}")


def independent_draw(seed: int, member_id: str, effect: str, entity_id: str) -> int:
    """Return a stable 64-bit draw without process-randomized hash or shared RNG state."""
    if type(seed) is not int or seed < 0 or not member_id or not effect or not entity_id:
        raise ValueError("seeded draw needs stable nonempty keys")
    material = canonical_json([GENERATOR_VERSION, seed, member_id, effect, entity_id])
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def freeze_suite(
    suite_id: str, seed: int, horizon_seconds: int, member_ids: tuple[str, ...],
    candidates: tuple[ScenarioEvent, ...], probability_numerator: int,
    probability_denominator: int,
) -> ScenarioSuite:
    if (type(probability_numerator) is not int or type(probability_denominator) is not int
            or not 0 <= probability_numerator <= probability_denominator
            or probability_denominator <= 0):
        raise ValueError("invalid event inclusion probability")
    if len(set(member_ids)) != len(member_ids):
        raise ValueError("duplicate suite member ID")
    members = []
    for member_id in member_ids:
        selected = tuple(sorted((event for event in candidates if
            independent_draw(seed, member_id, event.effect, event.target_id)
            % probability_denominator < probability_numerator),
            key=lambda event: (event.effective_seconds, event.id)))
        members.append(SuiteMember(
            member_id, seed, Scenario(f"{suite_id}:{member_id}", horizon_seconds, selected),
        ))
    return ScenarioSuite(suite_id, GENERATOR_VERSION, tuple(members))


def suite_hash(suite: ScenarioSuite) -> str:
    return hashlib.sha256(canonical_json(asdict(suite))).hexdigest()


__all__ = ("GENERATOR_VERSION", "freeze_suite", "independent_draw", "suite_hash",
           "validate_scenario")
