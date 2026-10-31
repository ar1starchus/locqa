from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, DefaultDict, Dict, List, Set

from locqa.checkers.base import BaseChecker
from locqa.models import ArbFile, Finding, IssueType, Severity


class SameAsSourceChecker(BaseChecker):
    """Detects strings in target that are identical to source,
    intelligently filtering legitimate matches (brands, IDs, numbers, formulas, technical tags).

    Uses cross-ARB translation evidence to distinguish genuinely untranslated strings
    (where the Russian word is translated elsewhere in the file) from legitimate same-string
    cases: game item names, international borrowings, or proper nouns that stay identical in KK.

    Algorithm:
    1. Build an internal 'translation evidence' index by scanning all source→target pairs
       where the strings actually DIFFER. Count how many times each Russian word root (3+ chars)
       appears in a genuine translation context.
    2. For each same_as_source hit, extract Russian words from the source string and check
       if any of them have translation evidence (i.e. are translated differently elsewhere):
         - HAS evidence  → word is translatable; this is a real bug → keep original severity.
         - NO  evidence  → word only appears identical across the ARB (proper name / borrowing)
                           → downgrade to LOW severity and reduce confidence.
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
        if re.fullmatch(r"[\d\s\W%_{}\\\\/–—#@\$\+\*\:\;\,\.\?\!\(\)\[\]\uea34]+", s):
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

    @staticmethod
    def _build_translation_evidence(source: ArbFile, target: ArbFile) -> DefaultDict[str, int]:
        """Scan all source→target pairs where strings differ and build a frequency map
        of how many times each Russian word root (3+ chars) appears in a genuinely
        translated context. Used to distinguish untranslated strings from legitimate
        same-script borrowings or game-specific names.
        """
        evidence: DefaultDict[str, int] = defaultdict(int)
        for key, src_entry in source.entries.items():
            tgt_entry = target.entries.get(key)
            if tgt_entry is None:
                continue
            src_val = src_entry.value.strip()
            tgt_val = tgt_entry.value.strip()
            # Only count keys where a translation actually differs (genuine translations)
            if not src_val or not tgt_val or src_val.lower() == tgt_val.lower():
                continue
            for word in re.findall(r"[а-яёА-ЯЁ]{3,}", src_val.lower()):
                evidence[word] += 1
        return evidence

    def check(
        self,
        source: ArbFile,
        target: ArbFile,
        context: Dict[str, Any] | None = None,
    ) -> List[Finding]:
        context = context or {}
        custom_whitelist: Set[str] = set(context.get("brand_whitelist", []))
        active_whitelist = self.DEFAULT_BRAND_WHITELIST | {w.lower() for w in custom_whitelist}

        # Build translation evidence index from the full ARB corpus
        translation_evidence = self._build_translation_evidence(source, target)

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

                # Extract meaningful Russian word roots from the source string
                ru_words = re.findall(r"[а-яёА-ЯЁ]{3,}", src_val.lower())

                # Does any Russian word in this string have cross-ARB translation evidence?
                # i.e. is this word translated (differently) in at least one other key?
                has_translation_evidence = any(
                    translation_evidence.get(w, 0) > 0 for w in ru_words
                )

                # Measure base severity from length / word count
                word_count = len(src_val.split())
                char_count = len(src_val)

                if has_translation_evidence:
                    # Word(s) ARE translated elsewhere → genuine untranslated string
                    if word_count >= 3 or char_count >= 25:
                        severity = Severity.HIGH
                        confidence = 0.98
                        evidence = (
                            f"Строка ({char_count} симв., {word_count} слов) полностью оставлена "
                            f"на языке оригинала без перевода"
                        )
                    elif word_count >= 2 or char_count >= 10:
                        severity = Severity.MEDIUM
                        confidence = 0.85
                        evidence = (
                            f"Словосочетание дословно совпадает с оригиналом ({char_count} симв.)"
                        )
                    else:
                        severity = Severity.MEDIUM
                        confidence = 0.80
                        evidence = (
                            f"Слово '{src_val}' не переведено: в других строках оно переведено иначе"
                        )
                else:
                    # No cross-ARB evidence that this word is translatable
                    # → likely a game-specific name, proper noun, or international borrowing
                    # that the translators deliberately kept identical (e.g. Алхимия, Клоун as item names)
                    severity = Severity.LOW
                    confidence = 0.45
                    if word_count >= 3 or char_count >= 25:
                        evidence = (
                            f"Строка совпадает с оригиналом, но ни одно из её слов не переводится "
                            f"в других строках — возможно, это название или заимствование"
                        )
                    else:
                        evidence = (
                            f"'{src_val}' совпадает с оригиналом; похоже на игровое название, "
                            f"заимствование или международный термин"
                        )

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
