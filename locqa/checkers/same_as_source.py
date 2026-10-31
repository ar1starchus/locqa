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
        "1xbet",
        "silverstar",
    }

    # International metric & time unit abbreviations that are identical across Russian and Kazakh
    COMMON_UNITS: Set[str] = {
        "сек", "мин", "сағ", "с", "м", "см", "мм", "км", "кг", "г",
        "шт", "ур", "макс", "бонус", "лига", "секунд", "секунды", "минут",
        "х", "x", "lvl", "exp", "fps", "hp",
    }

    # Russian grammatical inflections and markers that do not exist in Kazakh morphology
    RU_ADJ = re.compile(
        r"\b\w{2,}("
        r"[ыи]е|[ое]е|[ая]я|[ыио]й|[ое]го|[ое]му|[ыи]х|[ыи]м|[ыи]ми|[уе]ю|[ое]й"
        r")\b",
        re.IGNORECASE,
    )

    RU_VERB = re.compile(
        r"\b\w{2,}("
        r"[аеиоуыэюя]ть|[аеиоуыэюя]ться|[аеиоуыэюя]тся|[аеиоуыэюя]ти|[аеиоуыэюя]тись"
        r")\b",
        re.IGNORECASE,
    )

    RU_PARTICIPLE = re.compile(
        r"\b\w{2,}("
        r"вш[аеиу]|енн[ыаое][йхм]?|анн[ыаое][йхм]?|ем[ыаое][йхм]?|им[ыаое][йхм]?"
        r")\b",
        re.IGNORECASE,
    )

    RU_FUNC_WORDS = re.compile(
        r"\b("
        r"для|в|во|на|из|изо|под|подо|над|надо|за|к|ко|по|о|об|обо|при|от|ото|до|без|безо|у|через|сквозь|"
        r"чтобы|если|или|как|чем|тем|только|уже|еще|ещё|тоже|также|потому|поэтому"
        r")\b",
        re.IGNORECASE,
    )

    RU_NOUN_SUFFIX = re.compile(
        r"\b\w{2,}("
        r"ость|ости|остью|остей|ение|ения|ению|ением|ении|ений|ание|ания|анию|анием|ании|аний|ии"
        r")\b",
        re.IGNORECASE,
    )

    @property
    def issue_type(self) -> IssueType:
        return IssueType.SAME_AS_SOURCE

    @classmethod
    def is_metric_unit_string(cls, text: str) -> bool:
        """Checks if text (with or without placeholders and numbers)
        consists entirely of recognized metric/time units or formatting symbols.
        E.g. '{seconds} сек.', '{minutes} мин. {seconds} сек.', '%s км', 'сек.'
        """
        clean = re.sub(r"\{[a-zA-Z0-9_]+\}|%[a-zA-Z0-9_]|<[^>]+>|[\d\s\W_]+", " ", text).strip().lower()
        if not clean:
            return True
        tokens = clean.split()
        return all(tok in cls.COMMON_UNITS for tok in tokens)

    @classmethod
    def find_russian_grammar_markers(cls, text: str) -> List[str]:
        """Detects Russian grammatical inflections and function words
        that do not exist in Kazakh morphology or syntax.
        """
        clean = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>", " ", text)
        markers: List[str] = []
        if cls.RU_ADJ.search(clean):
            markers.append("окончания прилагательных")
        if cls.RU_VERB.search(clean):
            markers.append("глагольные формы/инфинитивы")
        if cls.RU_PARTICIPLE.search(clean):
            markers.append("причастия")
        if cls.RU_FUNC_WORDS.search(clean):
            markers.append("русские предлоги/союзы")
        if cls.RU_NOUN_SUFFIX.search(clean):
            markers.append("русские суффиксы существительных")
        return markers

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

        # 5. International metric units and time abbreviation templates (e.g. '{seconds} сек.')
        if self.is_metric_unit_string(s):
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

                # Morphological and syntactic analysis of the untranslated string
                ru_markers = self.find_russian_grammar_markers(src_val)
                words = re.sub(r"\{[a-zA-Z0-9_]+\}|<[^>]+>", " ", src_val).split()
                word_count = len(words)
                char_count = len(src_val)

                # If the string contains explicit Russian grammatical markers (e.g. 'Уличные Гонки',
                # 'Неизвестная ошибка', 'До исключения за АФК', 'и получить предмет сразу')
                # OR is a multi-word sentence (>= 4 words)
                if ru_markers or word_count >= 4:
                    severity = Severity.HIGH if word_count >= 2 or char_count >= 15 else Severity.MEDIUM
                    confidence = 0.98
                    details = f" ({', '.join(ru_markers)})" if ru_markers else ""
                    evidence = (
                        f"Непереведённый русский текст{details}: '{src_val}'"
                    )
                else:
                    # Single words or short international loanwords without Russian grammar
                    # (e.g. 'Гараж', 'Профиль', 'Бразилия', 'Математика', 'Бизнес класс')
                    # are legitimate international borrowings in Kazakh Cyrillic: skip them.
                    continue

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
