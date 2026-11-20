from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid7

from sqlmodel import JSON, CheckConstraint, Field, SQLModel, UniqueConstraint


def utc_now() -> datetime:
    return datetime.now(UTC)


class EntityClass(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    name: str = Field(index=True)
    definition: str = Field(unique=True, index=True)


class Entity(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid7, primary_key=True)

    name: str = Field(index=True)
    definition: str = Field(unique=True, index=True)


class EntityClassMembership(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("entity_id", "class_id"),)
    id: UUID = Field(default_factory=uuid7, primary_key=True)

    entity_id: UUID = Field(foreign_key="entity.id")
    class_id: UUID = Field(foreign_key="class.id")


class PredicateArity(str, Enum):
    unary = "unary"
    binary = "binary"
    scalar = "scalar"
    categorical = "categorical"


class Predicate(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid7, primary_key=True)

    name: str = Field(index=True)
    definition: str
    arity: PredicateArity


class Variable(SQLModel, table=True):
    __table_args__ = UniqueConstraint("entity_id", "predicate_id", "context_key")
    id: UUID = Field(default_factory=uuid7, primary_key=True)

    entity_id: UUID = Field(foreign_key="entity.id")
    predicate_id: UUID = Field(foreign_key="predicate.id")


class Claim(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid7, primary_key=True)

    source_variable_id: UUID = Field(foreign_key="variable.id", index=True)
    relation_predicate_id: UUID = Field(foreign_key="predicate.id", index=True)
    target_variable_id: UUID = Field(foreign_key="variable.id")
    # Conditions should be included in the variables


class Market(SQLModel, table=True):
    __table_args__ = (
        CheckConstraint(
            """
            (variable_id IS NOT NULL AND claim_id IS NULL)
            OR
            (variable_id IS NULL AND claim_id IS NOT NULL)
            """,
            name="ck_market_single_target",
        ),
    )

    id: UUID = Field(default_factory=uuid7, primary_key=True)

    question: str

    # A market measures either a variable or a claim.
    variable_id: UUID | None = Field(
        default=None,
        foreign_key="variable.id",
    )

    claim_id: UUID | None = Field(
        default=None,
        foreign_key="claim.id",
    )


class Relationship(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    predicate_id: UUID = Field(foreign_key="predicate.id")

    definition: str


class RelationshipParticipant(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid7, primary_key=True)

    relationship_id: UUID = Field(foreign_key="relationship.id")
    variable_id: UUID = Field(foreign_key="variable.id")

    role: str
    position: int


class Assumption(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    name: str
    definition: str


# Saying Class Country has assumption has a population
class AssumptionMatching(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    __table_args__ = (
        UniqueConstraint("class_id", "assumption_id", name="uq_class_assumption"),
    )
    class_id: UUID = Field(foreign_key="class.id")
    assumption_id: UUID = Field(foreign_key="assumption.id")


class EntityKind(str, Enum):
    object = "object"
    class_ = "class"


class Is_(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("a_id", "b_id"),)
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    a_id: UUID = Field(index=True)
    a_kind: EntityKind
    b_id: UUID = Field(foreign_key="class.id")
    belief: float | None = None


class Value(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid7, primary_key=True)

    class_id: UUID = Field(foreign_key="class.id")
    object_id: UUID = Field(foreign_key="object.id")

    value: int
    #: how much the number is believed; a parametric market collapsed to a point.
    belief: float | None = None
