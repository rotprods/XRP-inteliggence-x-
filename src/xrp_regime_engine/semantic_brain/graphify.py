from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .models import ClaimRecord, EdgeRecord, EntityRecord, EpistemicStatus, GraphDocument, SourceTier


@dataclass
class EntityResolver:
    by_alias: dict[str, str] = field(default_factory=dict)
    entities: dict[str, EntityRecord] = field(default_factory=dict)

    def register(self, entity: EntityRecord) -> EntityRecord:
        keys = {entity.canonical_name, *entity.aliases}
        normalized = {key.casefold().strip() for key in keys if key.strip()}
        collisions = {self.by_alias[k] for k in normalized if k in self.by_alias}
        if collisions and collisions != {entity.entity_id}:
            raise ValueError(f"ambiguous entity alias: {sorted(collisions)}")
        self.entities[entity.entity_id] = entity
        for key in normalized:
            self.by_alias[key] = entity.entity_id
        return entity

    def resolve(self, value: str) -> EntityRecord | None:
        entity_id = self.by_alias.get(value.casefold().strip())
        return self.entities.get(entity_id) if entity_id else None


@dataclass
class ClaimLedger:
    claims: dict[str, ClaimRecord] = field(default_factory=dict)

    def append(self, claim: ClaimRecord) -> ClaimRecord:
        previous = self.claims.get(claim.claim_id)
        if previous and previous.statement != claim.statement:
            raise ValueError("claim id collision")
        self.claims[claim.claim_id] = claim
        return claim

    def link_contradiction(self, left_id: str, right_id: str) -> None:
        if left_id == right_id:
            raise ValueError("claim cannot contradict itself")
        left, right = self.claims[left_id], self.claims[right_id]
        left.contradicts.add(right_id)
        right.contradicts.add(left_id)
        if left.status == EpistemicStatus.FACT and right.status == EpistemicStatus.FACT:
            left.status = EpistemicStatus.DISPUTED
            right.status = EpistemicStatus.DISPUTED

    def promote(self, claim_id: str, target: EpistemicStatus, source_tiers: set[SourceTier]) -> ClaimRecord:
        claim = self.claims[claim_id]
        if target == EpistemicStatus.FACT:
            primary = {SourceTier.T0_PRIMARY_MACHINE, SourceTier.T1_PRIMARY_DOCUMENT}
            if not source_tiers.intersection(primary):
                raise ValueError("FACT requires primary evidence")
            if source_tiers == {SourceTier.T4_SOCIAL_CLAIM}:
                raise ValueError("social repetition cannot promote truth")
            if claim.contradicts:
                raise ValueError("unresolved contradiction blocks FACT promotion")
        claim.status = target
        return claim


@dataclass
class ContradictionGraph:
    adjacency: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def add(self, left: str, right: str) -> None:
        self.adjacency[left].add(right)
        self.adjacency[right].add(left)

    def neighbors(self, claim_id: str) -> set[str]:
        return set(self.adjacency.get(claim_id, set()))


@dataclass
class SemanticGraph:
    entities: dict[str, EntityRecord]
    claims: dict[str, ClaimRecord]
    edges: dict[str, EdgeRecord]
    contradictions: ContradictionGraph


class GraphifyCompiler:
    def compile(self, documents: list[GraphDocument]) -> SemanticGraph:
        resolver = EntityResolver()
        ledger = ClaimLedger()
        edges: dict[str, EdgeRecord] = {}
        contradictions = ContradictionGraph()

        for document in documents:
            for entity in document.entities:
                resolver.register(entity)
            for claim in document.claims:
                ledger.append(claim)
            for edge in document.edges:
                if edge.edge_id in edges and edges[edge.edge_id] != edge:
                    raise ValueError(f"edge id collision: {edge.edge_id}")
                edges[edge.edge_id] = edge

        for claim in ledger.claims.values():
            for other in claim.contradicts:
                if other in ledger.claims:
                    contradictions.add(claim.claim_id, other)

        return SemanticGraph(resolver.entities, ledger.claims, edges, contradictions)
