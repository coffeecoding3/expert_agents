"""
Memory Schemas
"""

from enum import Enum
from typing import List


class LTMType(str, Enum):
    LTM = "long_term_memory"
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"

    @classmethod
    def values(cls) -> List[str]:
        return [
            cls.LTM.value,
            cls.SEMANTIC.value,
            cls.EPISODIC.value,
            cls.PROCEDURAL.value,
        ]

    @classmethod
    def is_valid(cls, value: str | None) -> bool:
        if not value:
            return False
        return value in cls.values()
