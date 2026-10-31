from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Set

from locqa.checkers.base import BaseChecker
from locqa.models import ArbFile, Finding, IssueType, Severity


class SameAsSourceChecker(BaseChecker):
    """Detects strings in target that are identical to source,
    intelligently filtering legitimate matches (brands, IDs, numbers, formulas, technical tags).
    """

    _KZ_DICT: Optional[Set[str]] = None

    # Optional default brand whitelist (empty by default; configured dynamically via context)
    DEFAULT_BRAND_WHITELIST: Set[str] = set()

    # Standard technical metric units, time formatting, and abbreviations
    METRIC_UNITS: Set[str] = {
        "мин", "сек", "с", "м", "ч", "сағ", "күн", "ай", "жыл",
        "км", "км/ч", "км/сағ", "кг", "см", "мм", "г", "т",
        "fps", "hp", "mp", "xp", "id", "lvl", "gc", "k", "к",
        "шт", "ур", "ур.", "x", "х", "%", "№",
    }

    # Kazakh grammatical affixes (case, plural, possessive, adjectival, verbal noun)
    KZ_AFFIX_REGEX = re.compile(
        r"^(?:"
        r"да|де|та|те|ға|ге|қа|ке|на|не|"
        r"ның|нің|дың|дің|тың|тің|"
        r"ны|ні|ды|ді|ты|ті|"
        r"дан|ден|тан|тен|нан|нен|"
        r"мен|пен|бен|"
        r"лар|лер|дар|дер|тар|тер|"
        r"ы|і|сы|сі|ым|ім|ың|ің|ыңыз|іңіз|ымыз|іміз|"
        r"лық|лік|дық|дік|тық|тік|"
        r"дағы|дегі|тағы|тегі|"
        r"шы|ші|лау|леу|тау|теу|дау|деу"
        r")(?:[а-яәғқңөұүһі]*)$"
    )

    @property
    def issue_type(self) -> IssueType:
        return IssueType.SAME_AS_SOURCE

    def is_metric_pattern(self, text: str) -> bool:
        """Checks if text consists solely of technical units, time formats, or placeholders.
        e.g. '{minutes} мин. {seconds} сек.', '%s км', '{count} шт.', 'СЕК', 'МИН'.
        """
        clean = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>", " ", text)
        clean = re.sub(r"%\d*(?:\$|\b)[a-zA-Z]?", " ", clean)
        clean = re.sub(r"[\d\s\W_–—#@\$\+\*\:\;\,\.\?\!\(\)\[\]\uea34\\\/%]+", " ", clean).strip().lower()
        if not clean:
            return True
        tokens = clean.split()
        return all(t in self.METRIC_UNITS for t in tokens)

    def is_short_adapted_term(self, text: str, corpus_words: Set[str], whitelist: Set[str]) -> bool:
        """In-game corpus affix mining:
        If a short term (1-2 words, e.g. 'Гараж', 'Бизнес', 'Арена', 'Донат', 'Рулетка')
        has derived or inflected forms with Kazakh grammatical suffixes in the target ARB,
        it proves that the game corpus recognizes this root as a legitimate loanword.
        """
        clean = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>", " ", text)
        words = re.findall(r"[а-яәғқңөұүһіА-ЯӘҒҚҢӨҰҮҺІa-zA-Z]+", clean)
        if not words or len(words) > 2:
            return False

        for w in words:
            if re.fullmatch(r"[a-zA-Z]+", w) or w.lower() in whitelist:
                continue
            if len(w) <= 2:
                continue

            w_lower = w.lower()
            adapted = False
            for cw in corpus_words:
                if cw.startswith(w_lower) and len(cw) > len(w_lower):
                    suffix = cw[len(w_lower):]
                    if self.KZ_AFFIX_REGEX.match(suffix):
                        adapted = True
                        break
            if not adapted:
                return False

        return True

    @classmethod
    def get_kz_dictionary(cls, custom_path: Optional[str] = None) -> Set[str]:
        """Loads and caches the official Kazakh Hunspell dictionary words."""
        if cls._KZ_DICT is not None:
            return cls._KZ_DICT

        candidates = [
            custom_path,
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "kk_KZ.dic"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "kk_dictionary.txt"),
            os.path.join(os.getcwd(), "kk_KZ.dic"),
        ]

        words: Set[str] = set()
        for p in candidates:
            if p and os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            w = line.strip().split("/")[0].lower()
                            if w and not w.isdigit():
                                words.add(w)
                    if words:
                        break
                except Exception:
                    pass

        cls._KZ_DICT = words
        return words

    def is_in_kz_dictionary(self, text: str, kz_dict: Set[str], whitelist: Set[str]) -> bool:
        """Checks if all content words in a 1-2 word string exist in the official Kazakh dictionary.
        e.g. 'Алхимия', 'Металл', 'Маска', 'Картон', 'Айсберг', 'Торт', 'Пластик', 'Неон'.
        """
        if not kz_dict:
            return False

        clean = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>", " ", text)
        words = re.findall(r"[а-яәғқңөұүһіА-ЯӘҒҚҢӨҰҮҺІa-zA-Z]+", clean)
        if not words or len(words) > 2:
            return False

        for w in words:
            if re.fullmatch(r"[a-zA-Z]+", w) or w.lower() in whitelist:
                continue
            if len(w) <= 2:
                continue
            if w.lower() not in kz_dict:
                return False

        return True

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

        # 4. Character names (proper entities / storyline NPC names)
        if key.lower().endswith("charactername"):
            return True

        # 5. Check brand / terms whitelist (case-insensitive)
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

        # Load official Kazakh Hunspell dictionary (Layer 2)
        dict_path = context.get("kz_dictionary_path")
        kz_dict = self.get_kz_dictionary(dict_path)

        # Build in-game target corpus of lowercased words for affix mining (Layer 1)
        corpus_words: Set[str] = set()
        for entry in target.entries.values():
            if isinstance(entry.value, str) and not entry.key.startswith("@"):
                for w in re.findall(r"[а-яәғқңөұүһіА-ЯӘҒҚҢӨҰҮҺІ]+", entry.value.lower()):
                    corpus_words.add(w)

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
                # 1. Technical units and metric patterns ({minutes} мин. {seconds} сек., %s км)
                if self.is_metric_pattern(tgt_val):
                    continue

                # 2. Brands, numbers, pure Latin codes
                if self.is_legitimate_match(tgt_val, key, active_whitelist):
                    continue

                # 3. In-game corpus affix mining (adapted loanwords like 'Гараж', 'Бизнес', 'Арена')
                if self.is_short_adapted_term(tgt_val, corpus_words, active_whitelist):
                    continue

                # 4. Official Kazakh dictionary (internationalisms like 'Алхимия', 'Металл', 'Маска', 'Картон')
                if self.is_in_kz_dictionary(tgt_val, kz_dict, active_whitelist):
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
