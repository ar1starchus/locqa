from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from locqa.checkers.base import BaseChecker
from locqa.models import ArbFile, Finding, IssueType, Severity


class SameAsSourceChecker(BaseChecker):
    """Detects strings in target that are identical to source,
    intelligently filtering legitimate matches (brands, IDs, numbers, formulas, technical tags).
    """

    # Common brand / technical entities that legitimately stay identical across locales
    DEFAULT_BRAND_WHITELIST: Set[str] = {
        "grand mobile",
        "grand rp",
        "grand",
        "role play",
        "google",
        "apple",
        "discord",
        "twitter",
        "vk",
        "vk id",
        "vk pay",
        "telegram",
        "battle pass",
        "grand pass",
        "grand market",
        "grand chicken",
        "rostics",
        "jackpot",
        "fps",
        "hud",
        "cdn",
        "api",
        "dev",
        "id",
        "vip",
        "lvl",
        "exp",
        "gc",
        "latin",
        "spain",
    }

    @property
    def issue_type(self) -> IssueType:
        return IssueType.SAME_AS_SOURCE

    def is_legitimate_match(self, text: str, key: str, whitelist: Set[str]) -> bool:
        s = text.strip()
        if not s:
            return True

        # 1. Pure numbers, punctuation, currencies, special characters or placeholders
        if re.fullmatch(r"[\d\s\W%_{}\\\/–—#@\$\+\*\:\;\,\.\?\!\(\)\[\]\uea34]+", s):
            return True

        # 2. Pure ASCII / Latin technical acronyms, codes, brands, URLs
        # e.g. "BATTLE PASS", "LATAM / Spain", "X%s", "LVL", "EXP", "Grand Mobile"
        if re.fullmatch(r"[A-Za-z0-9\s/._+&#'\"\-:()]+", s):
            # If it's purely Latin and target language is Cyrillic, it's typically a brand or code
            return True

        # 3. Very short formatting symbols (length <= 2) e.g. "м", "с", "д", "ч"
        if len(s) <= 2:
            return True

        # 4. Check brand / terms whitelist (case-insensitive)
        cleaned = re.sub(r"[\W_]+", " ", s.lower()).strip()
        if cleaned in whitelist:
            return True

        return False

    def check(
        self,
        source: ArbFile,
        target: ArbFile,
        context: Dict[str, Any] | None = None,
    ) -> List[Finding]:
        context = context or {}
        custom_whitelist: Set[str] = set(context.get("brand_whitelist", []))
        active_whitelist = self.DEFAULT_BRAND_WHITELIST | {w.lower() for w in custom_whitelist}

        findings: List[Finding] = []

        for key, src_entry in source.entries.items():
            tgt_entry = target.entries.get(key)
            if tgt_entry is None:
                continue

            src_val = src_entry.value.strip()
            tgt_val = tgt_entry.value.strip()

            if not src_val or not tgt_val:
                continue

            # Exact match check
            if src_val == tgt_val:
                if self.is_legitimate_match(tgt_val, key, active_whitelist):
                    continue

                # Measure severity: multi-word sentences or long strings are definitely untranslated Russian
                word_count = len(src_val.split())
                char_count = len(src_val)

                if word_count >= 3 or char_count >= 25:
                    severity = Severity.HIGH
                    confidence = 0.98
                    evidence = (
                        f"Строка ({char_count} симв., {word_count} слов) полностью оставлена на языке оригинала без перевода"
                    )
                elif word_count >= 2 or char_count >= 10:
                    severity = Severity.MEDIUM
                    confidence = 0.85
                    evidence = f"Словосочетание дословно совпадает с оригиналом ({char_count} симв.)"
                else:
                    severity = Severity.LOW
                    confidence = 0.65
                    evidence = f"Одиночное слово совпадает с оригиналом, возможно интернациональный термин или заимствование"

                findings.append(
                    Finding(
                        key=key,
                        issue_type=self.issue_type,
                        severity=severity,
                        source=src_entry.value,
                        target=tgt_entry.value,
                        evidence=evidence,
                        suggestion=None,
                        confidence=confidence,
                        reviewed_by_human=False,
                    )
                )

        return findings
