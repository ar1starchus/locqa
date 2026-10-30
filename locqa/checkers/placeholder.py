from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Set, Tuple

from locqa.checkers.base import BaseChecker
from locqa.models import ArbFile, Finding, IssueType, Severity


class PlaceholderChecker(BaseChecker):
    """Detects missing, extra, misspelled, or corrupted placeholders
    between source and target strings.
    
    Supports:
    - Named Flutter/ICU placeholders: {name}, {count}, {actId}
    - Positional placeholders: {0}, {1}
    - Printf style specifiers: %s, %d, %1$s, %.2f
    """

    PLACEHOLDER_REGEX = re.compile(r"\{[a-zA-Z0-9_]+\}")
    PRINTF_REGEX = re.compile(r"%\d*\$?[a-zA-Z%]")

    @property
    def issue_type(self) -> IssueType:
        return IssueType.PLACEHOLDER_MISMATCH

    def extract_placeholders(self, text: str) -> List[str]:
        named = self.PLACEHOLDER_REGEX.findall(text)
        printf = self.PRINTF_REGEX.findall(text)
        # Filter out %% literal in printf
        printf = [p for p in printf if p != "%%"]
        return named + printf

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

            src_phs = self.extract_placeholders(src_val)
            tgt_phs = self.extract_placeholders(tgt_val)

            src_set = set(src_phs)
            tgt_set = set(tgt_phs)

            if src_set == tgt_set and len(src_phs) == len(tgt_phs):
                # Also check for unclosed or malformed braces e.g. "{name" or "name}"
                unclosed = re.findall(r"\{[a-zA-Z0-9_]+(?!\})", tgt_val)
                if unclosed:
                    findings.append(
                        Finding(
                            key=key,
                            issue_type=self.issue_type,
                            severity=Severity.HIGH,
                            source=src_val,
                            target=tgt_val,
                            evidence=f"Обнаружен незакрытый плейсхолдер: {unclosed}",
                            suggestion=None,
                            confidence=0.99,
                            reviewed_by_human=False,
                        )
                    )
                continue

            missing = src_set - tgt_set
            extra = tgt_set - src_set

            # Check if an extra placeholder is actually a typo/truncation of a missing one
            # E.g., missing {level}, extra {leve}
            typo_corrections: Dict[str, str] = {}
            for ex in list(extra):
                # Compare similarity with missing
                matches = difflib.get_close_matches(ex, list(missing), n=1, cutoff=0.6)
                if matches:
                    expected = matches[0]
                    typo_corrections[ex] = expected
                    missing.remove(expected)
                    extra.remove(ex)

            evidence_parts: List[str] = []
            suggested_text = tgt_val

            if typo_corrections:
                corrections_desc = ", ".join(f"'{k}' -> '{v}'" for k, v in typo_corrections.items())
                evidence_parts.append(f"Искажен плейсхолдер: {corrections_desc}")
                # Apply fix directly to suggestion
                for wrong_ph, correct_ph in typo_corrections.items():
                    suggested_text = suggested_text.replace(wrong_ph, correct_ph)

            if missing:
                evidence_parts.append(f"Отсутствуют плейсхолдеры: {sorted(list(missing))}")
                # If target completely omitted the placeholder, suggest appending or note
                for m in missing:
                    if m not in suggested_text:
                        suggested_text = suggested_text + f" {m}"

            if extra:
                evidence_parts.append(f"Лишние/неизвестные плейсхолдеры: {sorted(list(extra))}")

            # Check counts if sets match but counts differ (e.g. source has {item} twice, target once)
            if not missing and not extra and not typo_corrections:
                evidence_parts.append(
                    f"Количество вхождений плейсхолдеров не совпадает: исходник {src_phs}, перевод {tgt_phs}"
                )

            evidence_str = "; ".join(evidence_parts)

            findings.append(
                Finding(
                    key=key,
                    issue_type=self.issue_type,
                    severity=Severity.HIGH,
                    source=src_val,
                    target=tgt_val,
                    evidence=evidence_str,
                    suggestion=suggested_text if suggested_text != tgt_val else None,
                    confidence=0.99 if typo_corrections or missing else 0.90,
                    reviewed_by_human=False,
                )
            )

        return findings
