import os
from dataclasses import dataclass, fields
from typing import Any

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    db_url: str
    db_name: str
    db_password: str

    @classmethod
    def from_env(cls) -> "Config":
        values: dict[str, Any] = {}

        for field in fields(cls):
            # TODO: Validate types
            value = os.environ[field.name.upper()]
            values[field.name] = field.type(value)

        return cls(**values)


env = Config.from_env()
