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
    - Missing braces around raw identifiers (e.g. 'time' instead of '{time}')
    - Truncated or misspelled placeholders (e.g. '{leve}' instead of '{level}')
    """

    PLACEHOLDER_REGEX = re.compile(r"\{([a-zA-Z0-9_]+)\}")
    PRINTF_REGEX = re.compile(r"%\d*\$?[a-zA-Z%]")

    @property
    def issue_type(self) -> IssueType:
        return IssueType.PLACEHOLDER_MISMATCH

    def extract_placeholders(self, text: str) -> List[str]:
        # If the string is a URL, it does not use printf placeholders
        if text.startswith("http://") or text.startswith("https://"):
            return [f"{{{m}}}" for m in self.PLACEHOLDER_REGEX.findall(text)]

        # Mask URL percent encoding (%20, %D1, etc.) before checking printf
        clean_printf = re.sub(r"%[0-9a-fA-F]{2}", "", text)

        named = [f"{{{m}}}" for m in self.PLACEHOLDER_REGEX.findall(text)]
        printf = self.PRINTF_REGEX.findall(clean_printf)
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

            # Check for real unclosed / orphan curly braces
            # Remove all valid placeholders first
            cleaned_tgt = self.PLACEHOLDER_REGEX.sub("", tgt_val)
            # Find any stray unclosed or orphan brace that is not part of ICU plural or normal text
            stray_open = [m.group(0) for m in re.finditer(r"\{[^\s\}\"\'\<\>]*", cleaned_tgt) if m.group(0).strip()]
            stray_close = [m.group(0) for m in re.finditer(r"[^\s\{\"\'\<\>]*\}", cleaned_tgt) if m.group(0).strip()]

            if stray_open or stray_close:
                # If stray braces exist and cannot be part of plural
                if "plural," not in tgt_val.lower():
                    evidence_stray = f"Сломанный синтаксис фигурных скобок: {stray_open + stray_close}"
                    findings.append(
                        Finding(
                            key=key,
                            issue_type=self.issue_type,
                            severity=Severity.HIGH,
                            source=src_val,
                            target=tgt_val,
                            evidence=evidence_stray,
                            suggestion=None,
                            confidence=0.99,
                            reviewed_by_human=False,
                        )
                    )
                    continue

            # If placeholder sets match completely and count is identical, it's 100% valid
            if src_set == tgt_set and len(src_phs) == len(tgt_phs):
                continue

            missing = set(src_set) - set(tgt_set)
            extra = set(tgt_set) - set(src_set)

            evidence_parts: List[str] = []
            suggested_text = tgt_val

            # Step 1: Detect typos/truncation via Levenshtein distance e.g. {leve} -> {level}
            typo_corrections: Dict[str, str] = {}
            for ex in list(extra):
                # Compare similarity with missing
                matches = difflib.get_close_matches(ex, list(missing), n=1, cutoff=0.6)
                if matches:
                    expected = matches[0]
                    typo_corrections[ex] = expected
                    missing.remove(expected)
                    extra.remove(ex)
                    suggested_text = suggested_text.replace(ex, expected)

            if typo_corrections:
                corrections_desc = ", ".join(f"'{k}' -> '{v}'" for k, v in typo_corrections.items())
                evidence_parts.append(f"Искажен плейсхолдер: {corrections_desc}")

            # Step 2: Detect raw placeholder identifiers written without curly braces e.g. 'time' instead of '{time}'
            fixed_raw_identifiers: List[str] = []
            for m in list(missing):
                raw_id = m.strip("{}")
                # Pattern matches raw identifier as standalone word or with hyphenated suffix e.g. 'min-нан'
                pattern = rf"\b{re.escape(raw_id)}([-–—][а-яәғқңөұүһіА-ЯӘҒҚҢӨҰҮҺІ]+)?\b"
                match = re.search(pattern, suggested_text)
                if match:
                    sfx = match.group(1) or ""
                    suggested_text = re.sub(pattern, f"{{{raw_id}}}{sfx}", suggested_text, count=1)
                    missing.remove(m)
                    fixed_raw_identifiers.append(f"'{raw_id}' -> '{m}'")

            if fixed_raw_identifiers:
                evidence_parts.append(f"Пропущены фигурные скобки у переменной: {', '.join(fixed_raw_identifiers)}")

            # Step 3: Handle any remaining completely missing placeholders
            if missing:
                evidence_parts.append(f"Отсутствуют в переводе: {sorted(list(missing))}")
                for m in sorted(list(missing)):
                    # Prepend placeholder so runtime doesn't throw MissingParameterException
                    if m not in suggested_text:
                        suggested_text = f"{m} " + suggested_text

            # Step 4: Handle any remaining extra placeholders
            if extra:
                evidence_parts.append(f"Лишние/неизвестные плейсхолдеры: {sorted(list(extra))}")

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
                    confidence=0.99 if (typo_corrections or fixed_raw_identifiers or missing) else 0.90,
                    reviewed_by_human=False,
                )
            )

        return findings
