from sqlmodel import Session, SQLModel, create_engine

from db import schema
from env import env

DATABASE_URL = f"sqlite:///./{env.db_name}.sqlite"
# DATABASE_URL = f"postgresql://postgres:{env.db_password}@{env.db_url}/{env.db_name}"

engine = create_engine(DATABASE_URL, echo=False)


def create_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
