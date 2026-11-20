from sqlmodel import select

from db.db import create_db, get_session
from db.schema import Assumption, Class, Object

create_db()

objects: list[Object] = [
    Object(name="NS", definition="Dutch NS railway"),
    Object(name="Sweden", definition="Sweden"),
    Object(name="2030", definition="Year 2030"),
    Object(name="FC Barcelona", definition="Football Team A Club"),
    Object(name="Nottingham FC", definition="Football Team B Club"),
]

classes = [
    Class(name="scammer", definition="scams people"),
    Class(name="country", definition="country"),
    Class(name="GDP", definition="GDP"),
    Class(name="ceo", definition="ceo"),
    Class(name="company", definition="An organization that sells stuff"),
    Class(name="date_founded", definition="Founding date of an entity"),
    Class(name="safety_index", definition="Safety of X from 0-10"),
    Class(name="is_public", definition="Is X a public company"),
    Class(
        name="football team", definition="An organization that primarily plays football"
    ),
]

assumptions = [
    Assumption(name="Makes a profit", definition="Makes a profit"),
    Assumption(name="Has a population", definition="Has a population"),
    Assumption(
        name="Has an intention to make profit",
        definition="Has an intention to make profit",
    ),
    Assumption(
        name="Deliberately deceives people", definition="Deliberately deceives people"
    ),
    Assumption(name="Is an organization", definition="Is an organization"),
]


def load_db() -> None:
    with get_session() as session:
        seed_records = (
            (Object, objects),
            (Class, classes),
            (Assumption, assumptions),
        )
        for model, records in seed_records:
            for record in records:
                exists = session.exec(
                    select(model).where(model.definition == record.definition)
                ).first()

                if exists:
                    continue

                print(f"Creating {model.__name__}: {record.name}")
                session.add(record)

        session.commit()


if __name__ == "__main__":
    load_db()

    print("Loaded DB successfully")
