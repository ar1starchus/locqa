from __future__ import annotations

from typing import Any, Dict, List

from locqa.checkers.base import BaseChecker
from locqa.models import ArbFile, Finding, IssueType, Severity


class UntranslatedChecker(BaseChecker):
    """Detects keys present in the source file that are completely missing
    or empty/whitespace in the target file.
    """

    @property
    def issue_type(self) -> IssueType:
        return IssueType.UNTRANSLATED

    def check(
        self,
        source: ArbFile,
        target: ArbFile,
        context: Dict[str, Any] | None = None,
    ) -> List[Finding]:
        findings: List[Finding] = []

        for key, src_entry in source.entries.items():
            src_val = src_entry.value
            # Skip if source itself is empty
            if not src_val.strip():
                continue

            tgt_entry = target.entries.get(key)
            if tgt_entry is None:
                findings.append(
                    Finding(
                        key=key,
                        issue_type=self.issue_type,
                        severity=Severity.HIGH,
                        source=src_val,
                        target="",
                        evidence=f"Ключ отсутствует в целевом файле локализации (строка {src_entry.line_number} в исходнике)",
                        suggestion=src_val,
                        confidence=1.0,
                        reviewed_by_human=False,
                    )
                )
            elif not tgt_entry.value.strip() and src_val.strip():
                findings.append(
                    Finding(
                        key=key,
                        issue_type=self.issue_type,
                        severity=Severity.HIGH,
                        source=src_val,
                        target=tgt_entry.value,
                        evidence=f"Перевод пустой при непустом исходнике (строка {tgt_entry.line_number})",
                        suggestion=src_val,
                        confidence=1.0,
                        reviewed_by_human=False,
                    )
                )

        return findings
