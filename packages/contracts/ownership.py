"""Owner identity shared across application and persistence ports."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Actor:
    kind: Literal["temporary", "account"]
    owner_id: str
