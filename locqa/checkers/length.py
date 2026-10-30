from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from locqa.checkers.base import BaseChecker
from locqa.llm import GeminiClient
from locqa.models import ArbFile, Finding, IssueType, Severity


class LengthOverflowChecker(BaseChecker):
    """Detects translations that are disproportionately longer than the source text,
    especially for compact UI elements like buttons, tabs, headers, chips, and menu labels.
    
    Operates purely on string length metrics, length ratios, and UI element naming heuristics.
    No hardcoded phrases or dataset-specific strings.
    """

    UI_KEYWORDS = re.compile(
        r"(btn|button|tab|title|header|label|short|action|menu|nav|chip|item|select|name)",
        re.IGNORECASE,
    )

    @property
    def issue_type(self) -> IssueType:
        return IssueType.LENGTH_OVERFLOW

    def check(
        self,
        source: ArbFile,
        target: ArbFile,
        context: Dict[str, Any] | None = None,
    ) -> List[Finding]:
        context = context or {}
        max_source_len = context.get("length_max_source_len", 30)
        min_ratio = context.get("length_min_ratio", 2.0)
        min_abs_diff = context.get("length_min_abs_diff", 12)
        gemini: Optional[GeminiClient] = context.get("gemini_client")

        findings: List[Finding] = []

        for key, src_entry in source.entries.items():
            tgt_entry = target.entries.get(key)
            if tgt_entry is None:
                continue

            src_val = src_entry.value.strip()
            tgt_val = tgt_entry.value.strip()

            if not src_val or not tgt_val:
                continue

            len_src = len(src_val)
            len_tgt = len(tgt_val)
            ratio = len_tgt / max(len_src, 1)
            diff = len_tgt - len_src

            is_ui_key = bool(self.UI_KEYWORDS.search(key))

            # Fully generic criteria for UI length overflow:
            # 1. Very short source (<= 12 chars) with 3x growth and +15 characters
            # 2. UI key (button/tab/title) with >= 1.8x growth and +10 characters
            # 3. Short element (<= 25 chars) with >= 2.0x growth and +12 characters
            is_overflow = False
            confidence = 0.80
            severity = Severity.MEDIUM

            if len_src <= 12 and ratio >= 3.0 and diff >= 15:
                is_overflow = True
                severity = Severity.HIGH
                confidence = 0.95
            elif is_ui_key and len_src <= max_source_len and ratio >= 1.8 and diff >= 10:
                is_overflow = True
                severity = Severity.HIGH
                confidence = 0.92
            elif len_src <= 25 and ratio >= min_ratio and diff >= min_abs_diff:
                is_overflow = True
                severity = Severity.MEDIUM
                confidence = 0.85

            if is_overflow:
                ui_desc = "ключ относится к UI-элементу" if is_ui_key else "короткий элемент интерфейса"
                evidence = (
                    f"{len_tgt} символов против {len_src} в исходнике "
                    f"(рост в {ratio:.1f}x, +{diff} симв.), {ui_desc}"
                )

                findings.append(
                    Finding(
                        key=key,
                        issue_type=self.issue_type,
                        severity=severity,
                        source=src_val,
                        target=tgt_val,
                        evidence=evidence,
                        suggestion=None,
                        confidence=confidence,
                        reviewed_by_human=False,
                    )
                )

        return findings
