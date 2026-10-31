from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from locqa.checkers.base import BaseChecker
from locqa.glossary import Glossary
from locqa.models import ArbFile, Finding, IssueType, Severity
from locqa.morphology import KazakhMorphology


class GlossaryChecker(BaseChecker):
    """Detects terminology violations against an approved glossary.csv.
    
    Verifies that canonical game terms (e.g. 'фракция', 'семья', 'бизнес',
    'Grand Coins', 'варн', 'мут', 'аккаунт', 'ранг', 'награда', 'донат')
    are translated consistently in accordance with approved gaming terminology.
    
    Provides direct suggestions for exact single-term keys, and flags
    contextual violations in sentences for human review without hardcoding.
    """

    @property
    def issue_type(self) -> IssueType:
        return IssueType.GLOSSARY_VIOLATION

    @staticmethod
    def adapt_casing(term: str, sample_source: str, sample_target: Optional[str] = None) -> str:
        """Adapt grammatical casing (UPPERCASE, Title Case, lowercase)
        to match the surrounding target context and source original.
        """
        if not term:
            return term

        # Proper nouns or terms with Latin characters (e.g. 'Grand Coins') or short acronyms (e.g. 'ГК')
        if any("a" <= c <= "z" or "A" <= c <= "Z" for c in term) or (len(term) <= 3 and term.isupper()):
            if (sample_target and sample_target.isupper()) or sample_source.isupper():
                return term.upper()
            return term

        # If target word is ALL CAPS (e.g. СІЗДІҢ СЫЙЛЫҒЫҢЫЗ) or source is ALL CAPS (АККАУНТ)
        if (sample_target and sample_target.isupper()) or sample_source.isupper():
            return term.upper()

        # If target word context is provided, target position casing takes precedence
        # over source (e.g. Russian first-word 'Награда за ...' is capitalized,
        # but Kazakh 'жазылым сыйлығы' is lowercase mid-sentence).
        if sample_target:
            if sample_target.islower():
                return term.lower()
            if sample_target[0].isupper():
                return term[0].upper() + term[1:].lower() if term.isupper() else term[0].upper() + term[1:]

        # If no target sample or target case undetermined, fall back to source casing
        if sample_source.istitle():
            return term[0].upper() + term[1:]
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

                        # Provide suggestion for exact single-term keys directly from glossary
                        suggestion = None
                        if is_exact_match:
                            target_caps = tgt_val if tgt_val.isupper() else None
                            suggestion = self.adapt_casing(term_kk, matched_src_text, target_caps)

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
