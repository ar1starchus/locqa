from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IssueType(str, Enum):
    UNTRANSLATED = "untranslated"
    SAME_AS_SOURCE = "same_as_source"
    PLACEHOLDER_MISMATCH = "placeholder_mismatch"
    PLURAL_MISMATCH = "plural_mismatch"
    GLOSSARY_VIOLATION = "glossary_violation"
    LENGTH_OVERFLOW = "length_overflow"
    MACHINE_TRANSLATION_SUSPECT = "machine_translation_suspect"
    INCONSISTENT_TERM = "inconsistent_term"
    SUFFIX_HARMONY = "suffix_harmony"
    ORTHOGRAPHY = "orthography"
    WRONG_LANGUAGE = "wrong_language"


@dataclass
class Finding:
    key: str
    issue_type: IssueType | str
    severity: Severity | str
    source: str
    target: str
    evidence: str
    suggestion: Optional[str] = None
    options: Optional[List[str]] = None
    confidence: float = 1.0
    reviewed_by_human: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if isinstance(self.issue_type, IssueType):
            data["issue_type"] = self.issue_type.value
        if isinstance(self.severity, Severity):
            data["severity"] = self.severity.value
        return data


@dataclass
class ArbEntry:
    key: str
    value: str
    raw_line: str
    line_number: int
    section: Optional[str] = None
    is_meta: bool = False
    meta_for_key: Optional[str] = None
    meta_attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ArbFile:
    path: str
    locale: str
    entries: Dict[str, ArbEntry] = field(default_factory=dict)
    metadata: Dict[str, ArbEntry] = field(default_factory=dict)
    sections: List[str] = field(default_factory=list)
    raw_lines: List[str] = field(default_factory=list)

    def get_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        entry = self.entries.get(key)
        return entry.value if entry else default

    def contains(self, key: str) -> bool:
        return key in self.entries
