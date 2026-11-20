from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid7

from sqlmodel import Field, SQLModel, UniqueConstraint


def utc_now() -> datetime:
    return datetime.now(UTC)


class Class(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid7, primary_key=True)

    name: str
    definition: str


class Object(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid7, primary_key=True)

    name: str
    definition: str


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


class Market(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid7, primary_key=True)
    question: str = ""
