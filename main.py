from sqlmodel import select

from db.db import get_session
from db.schema import Assumption, AssumptionMatching, Class, EntityKind, Is_, Object


class ObjectNotFoundError(Exception):
    pass


class ClassNotFoundError(Exception):
    pass


class AssumptionNotFoundError(Exception):
    pass


def get_object(name: str) -> Object:
    with get_session() as session:
        object: Object | None = session.exec(
            select(Object).where(Object.name == name)
        ).first()

        if not object:
            raise ObjectNotFoundError(f"Object {name} not found")

        return object


def get_class(name: str) -> Class:
    with get_session() as session:
        class_: Class | None = session.exec(
            select(Class).where(Class.name == name)
        ).first()

        if not class_:
            raise ClassNotFoundError(f"Class {name} not found")

        return class_


def set_is(a: Object | Class, b: Class) -> Is_:
    with get_session() as session:
        exists: Is_ | None = session.exec(
            select(Is_).where(Is_.a_id == a.id).where(Is_.b_id == b.id)
        ).first()

        if exists:
            return exists

        is_ = Is_(
            a_id=a.id,
            a_kind=EntityKind.object if isinstance(a, Object) else EntityKind.class_,
            b_id=b.id,
        )

        session.add(is_)
        session.commit()
        session.refresh(is_)
        return is_


def set_assumption(class_: Class, assumption: Assumption) -> AssumptionMatching:
    with get_session() as session:
        exists: AssumptionMatching | None = session.exec(
            select(AssumptionMatching)
            .where(AssumptionMatching.class_id == class_.id)
            .where(AssumptionMatching.assumption_id == assumption.id)
        ).first()

        if exists:
            return exists

        is_ = AssumptionMatching(
            class_id=class_.id,
            assumption_id=assumption.id,
        )

        session.add(is_)
        session.commit()
        session.refresh(is_)
        return is_


def get_assumption(name: str) -> Assumption:
    with get_session() as session:
        assumption: Assumption | None = session.exec(
            select(Assumption).where(Assumption.name == name)
        ).first()

        if not assumption:
            raise AssumptionNotFoundError(f"Assumption {name} not found")

        return assumption


def set_has(class_: Class, assumption: Assumption) -> AssumptionMatching:
    with get_session() as session:
        exists: AssumptionMatching | None = session.exec(
            select(AssumptionMatching)
            .where(AssumptionMatching.class_id == class_.id)
            .where(AssumptionMatching.assumption_id == assumption.id)
        ).first()

        if exists:
            return exists

        is_ = AssumptionMatching(
            class_id=class_.id,
            assumption_id=assumption.id,
        )

        session.add(is_)
        session.commit()
        session.refresh(is_)
        return is_
