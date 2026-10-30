from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from locqa.checkers.base import BaseChecker
from locqa.models import ArbFile, Finding, IssueType, Severity


class PluralChecker(BaseChecker):
    """Detects broken, incomplete, or mismatched ICU plural forms.
    
    Validates:
    - ICU plural pattern: {var, plural, [offset:N] case{submessage} ...}
    - Presence of mandatory 'other' clause
    - Matching plural presence between source and target
    - Balanced braces and valid submessages
    """

    ICU_PLURAL_START = re.compile(r"\{([a-zA-Z0-9_]+)\s*,\s*plural\s*,", re.IGNORECASE)
    VALID_CATEGORIES = {"zero", "one", "two", "few", "many", "other"}

    @property
    def issue_type(self) -> IssueType:
        return IssueType.PLURAL_MISMATCH

    def parse_icu_plurals(self, text: str) -> List[Dict[str, Any]]:
        plurals: List[Dict[str, Any]] = []
        for match in self.ICU_PLURAL_START.finditer(text):
            var_name = match.group(1)
            start_pos = match.start()
            
            # Find closing brace by tracking brace depth
            depth = 0
            end_pos = -1
            for idx in range(start_pos, len(text)):
                ch = text[idx]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end_pos = idx
                        break

            if end_pos == -1:
                # Syntax error: unclosed ICU expression
                plurals.append({
                    "var": var_name,
                    "is_syntax_error": True,
                    "error": "Не закрыта фигурная скобка ICU плюрала",
                    "raw": text[start_pos:],
                    "categories": set(),
                })
                continue

            raw_body = text[match.end() : end_pos].strip()
            # Parse cases e.g. =0{...} one{...} other{...}
            # Regex to find category tags followed by '{'
            cases = re.findall(r"(=?\w+)\s*\{", raw_body)
            category_set = set()
            for c in cases:
                if c.startswith("="):
                    category_set.add(c)
                else:
                    category_set.add(c.lower())

            plurals.append({
                "var": var_name,
                "is_syntax_error": False,
                "error": None,
                "raw": text[start_pos : end_pos + 1],
                "categories": category_set,
            })

        return plurals

    def check(
        self,
        source: ArbFile,
        target: ArbFile,
        context: Dict[str, Any] | None = None,
    ) -> List[Finding]:
        findings: List[Finding] = []

        for key, src_entry in source.entries.items():
            tgt_entry = target.entries.get(key)
            if tgt_entry is None:
                continue

            src_val = src_entry.value
            tgt_val = tgt_entry.value

            src_plurals = self.parse_icu_plurals(src_val)
            tgt_plurals = self.parse_icu_plurals(tgt_val)

            # Check 1: Target has unclosed ICU plural
            for p in tgt_plurals:
                if p["is_syntax_error"]:
                    findings.append(
                        Finding(
                            key=key,
                            issue_type=self.issue_type,
                            severity=Severity.HIGH,
                            source=src_val,
                            target=tgt_val,
                            evidence=f"Синтаксическая ошибка в ICU-форме: {p['error']}",
                            suggestion=None,
                            confidence=1.0,
                            reviewed_by_human=False,
                        )
                    )

            # Check 2: Missing mandatory 'other' category in target ICU plural
            for p in tgt_plurals:
                if not p["is_syntax_error"]:
                    if "other" not in p["categories"]:
                        findings.append(
                            Finding(
                                key=key,
                                issue_type=self.issue_type,
                                severity=Severity.HIGH,
                                source=src_val,
                                target=tgt_val,
                                evidence=f"В ICU plural '{p['var']}' отсутствует обязательная категория 'other'",
                                suggestion=None,
                                confidence=0.98,
                                reviewed_by_human=False,
                            )
                        )

            # Check 3: Source has ICU plural, but target does not
            if src_plurals and not tgt_plurals:
                findings.append(
                    Finding(
                        key=key,
                        issue_type=self.issue_type,
                        severity=Severity.HIGH,
                        source=src_val,
                        target=tgt_val,
                        evidence=f"В исходнике используется ICU plural ({[p['var'] for p in src_plurals]}), а в переводе обычный текст",
                        suggestion=None,
                        confidence=0.95,
                        reviewed_by_human=False,
                    )
                )

            # Check 4: Variable name mismatch
            if src_plurals and tgt_plurals:
                src_vars = {p["var"] for p in src_plurals}
                tgt_vars = {p["var"] for p in tgt_plurals}
                if src_vars != tgt_vars:
                    findings.append(
                        Finding(
                            key=key,
                            issue_type=self.issue_type,
                            severity=Severity.HIGH,
                            source=src_val,
                            target=tgt_val,
                            evidence=f"Не совпадают переменные плюралов: исходник {src_vars}, перевод {tgt_vars}",
                            suggestion=None,
                            confidence=0.95,
                            reviewed_by_human=False,
                        )
                    )

        return findings
