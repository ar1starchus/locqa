from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from locqa.checkers.base import BaseChecker
from locqa.glossary import Glossary
from locqa.models import ArbFile, Finding, IssueType, Severity
from locqa.morphology import KazakhMorphology


class GlossaryChecker(BaseChecker):
    """Detects terminology violations against an approved glossary.csv
    and generates case-adapted, grammatically inflected suggestions.
    
    Verifies that canonical game terms (e.g. 'фракция', 'семья', 'бизнес',
    'Grand Coins', 'варн', 'мут', 'аккаунт', 'ранг', 'награда', 'донат')
    are translated consistently in accordance with approved gaming terminology.
    
    Uses KazakhMorphology to transfer grammatical affixes (possessive, plural, case)
    from the mistranslated word to the approved term with full vowel harmony.
    """

    # Mapping of canonical Russian terms to tuples of (regex_pattern, base_stem)
    MISTRANSLATION_PATTERNS: Dict[str, List[Tuple[str, str]]] = {
        "аккаунт": [
            (r"тіркелгі[а-яәғқңөұүһі]*", "тіркелгі"),
            (r"есептік жазба[а-яәғқңөұүһі]*", "есептік жазба"),
            (r"есепті[а-яәғқңөұүһі]*", "есеп"),
            (r"есеп[а-яәғқңөұүһі]*", "есеп"),
        ],
        "ранг": [
            (r"дәреже[а-яәғқңөұүһі]*", "дәреже"),
            (r"рейтинг[а-яәғқңөұүһі]*", "рейтинг"),
        ],
        "награда": [
            (r"сыйақы[а-яәғқңөұүһі]*", "сыйақы"),
            (r"сыйлы[қғ][а-яәғқңөұүһі]*", "сыйлық"),
            (r"марапат[а-яәғқңөұүһі]*", "марапат"),
            (r"сый[а-яәғқңөұүһі]*", "сый"),
        ],
        "донат": [
            (r"сыйлық[а-яәғқңөұүһі]*", "сыйлық"),
            (r"қайырымдылық[а-яәғқңөұүһі]*", "қайырымдылық"),
        ],
        "пропуск": [
            (r"жауынгерлік билет[а-яәғқңөұүһі]*", "жауынгерлік билет"),
            (r"билет[а-яәғқңөұүһі]*", "билет"),
            (r"пасс?[а-яәғқңөұүһі]*", "пасс"),
        ],
        "боевой пропуск": [
            (r"жауынгерлік билет[а-яәғқңөұүһі]*", "жауынгерлік билет"),
            (r"билет[а-яәғқңөұүһі]*", "билет"),
            (r"пасс?[а-яәғқңөұүһі]*", "пасс"),
        ],
        "фракция": [
            (r"ұйым[а-яәғқңөұүһі]*", "ұйым"),
        ],
        "семья": [
            (r"клан[а-яәғқңөұүһі]*", "клан"),
            (r"әулет[а-яәғқңөұүһі]*", "әулет"),
        ],
        "бизнес": [
            (r"кәсіп[а-яәғқңөұүһі]*", "кәсіп"),
        ],
        "Grand Coins": [
            (r"гранд коинс[а-яәғқңөұүһі]*", "гранд коинс"),
            (r"монета[а-яәғқңөұүһі]*", "монета"),
        ],
    }

    @property
    def issue_type(self) -> IssueType:
        return IssueType.GLOSSARY_VIOLATION

    @staticmethod
    def adapt_casing(term: str, sample_source: str, sample_target: Optional[str] = None) -> str:
        """Adapt grammatical casing (UPPERCASE, Title Case, lowercase)
        to match the source original and surrounding target context.
        """
        # If target word is ALL CAPS (e.g. СІЗДІҢ СЫЙЛЫҒЫҢЫЗ) or source is ALL CAPS (АККАУНТ)
        if (sample_target and sample_target.isupper()) or sample_source.isupper():
            return term.upper()
        # If source is Title Case (e.g. Аккаунт, Донат)
        if sample_source.istitle():
            return term.capitalize()
        # If source is lowercase (e.g. аккаунт, донат)
        if sample_source.islower():
            return term.lower()
        return term

    def check(
        self,
        source: ArbFile,
        target: ArbFile,
        context: Dict[str, Any] | None = None,
    ) -> List[Finding]:
        context = context or {}
        glossary: Optional[Glossary] = context.get("glossary")
        if not glossary or not glossary.entries:
            return []

        findings: List[Finding] = []

        for entry in glossary.entries:
            term_ru = entry.term_ru
            term_kk = entry.term_kk
            if not term_ru or not term_kk:
                continue

            pattern_ru = re.compile(rf"\b{re.escape(term_ru)}\b", re.IGNORECASE)
            term_stem = term_kk[: max(3, len(term_kk) - 2)]
            pattern_kk = re.compile(rf"\b{re.escape(term_stem)}", re.IGNORECASE)

            for key, src_entry in source.entries.items():
                tgt_entry = target.entries.get(key)
                if tgt_entry is None:
                    continue

                src_val = src_entry.value
                tgt_val = tgt_entry.value

                if not src_val or not tgt_val:
                    continue

                # Check if source contains the glossary term
                match_src = pattern_ru.search(src_val)
                if match_src:
                    # Check if target contains the approved term or its stem
                    if not pattern_kk.search(tgt_val):
                        matched_src_text = match_src.group(0)
                        is_exact_match = src_val.strip().lower() == term_ru.lower()
                        severity = Severity.HIGH if is_exact_match else Severity.MEDIUM

                        # Generate case-adapted and grammatically inflected suggestion
                        suggestion = None
                        if is_exact_match:
                            # Exact string replacement: match source case
                            suggestion = self.adapt_casing(term_kk, matched_src_text, tgt_val)
                        else:
                            # Sentence replacement: find mistranslated token in target
                            lookup_key = term_ru.lower()
                            candidate_patterns = self.MISTRANSLATION_PATTERNS.get(lookup_key, [])

                            for wrong_pat, wrong_stem in candidate_patterns:
                                m_tgt = re.search(rf"\b{wrong_pat}\b", tgt_val, re.IGNORECASE)
                                if m_tgt:
                                    matched_target_text = m_tgt.group(0)

                                    # Morphological suffix transfer:
                                    # Extracts plural, possessive, case tags from the mistranslated word
                                    # and applies them to the approved term obeying Kazakh vowel harmony
                                    inflected_term = KazakhMorphology.transfer_affixes(
                                        wrong_word=matched_target_text,
                                        wrong_stem=wrong_stem,
                                        approved_term=term_kk,
                                    )

                                    # Adapt casing to match either source or target caps
                                    adapted_term = self.adapt_casing(
                                        inflected_term,
                                        matched_src_text,
                                        matched_target_text,
                                    )

                                    # Replace the incorrect word with inflected approved term
                                    suggestion = re.sub(
                                        rf"\b{wrong_pat}\b",
                                        adapted_term,
                                        tgt_val,
                                        count=1,
                                        flags=re.IGNORECASE,
                                    )
                                    break

                        # Fallback for short UI strings if no regex pattern hit
                        if not suggestion and len(src_val.split()) <= 2:
                            suggestion = self.adapt_casing(term_kk, matched_src_text, tgt_val)

                        evidence = (
                            f"Термин '{term_ru}' должен переводиться как '{term_kk}' "
                            f"(согласно глоссарию), но в целевом тексте отсутствует '{term_kk}'"
                        )
                        if entry.comment:
                            evidence += f" [Контекст: {entry.comment}]"

                        findings.append(
                            Finding(
                                key=key,
                                issue_type=self.issue_type,
                                severity=severity,
                                source=src_val,
                                target=tgt_val,
                                evidence=evidence,
                                suggestion=suggestion,
                                confidence=0.90,
                                reviewed_by_human=False,
                            )
                        )

        return findings
