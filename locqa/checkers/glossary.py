from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from locqa.checkers.base import BaseChecker
from locqa.glossary import Glossary
from locqa.models import ArbFile, Finding, IssueType, Severity


class GlossaryChecker(BaseChecker):
    """Detects terminology violations against an approved glossary.csv.
    
    Verifies that canonical game terms (e.g. 'фракция', 'семья', 'бизнес',
    'Grand Coins', 'варн', 'мут') are translated consistently in accordance
    with the agreed gaming terminology rather than improvised or mistranslated.
    """

    @property
    def issue_type(self) -> IssueType:
        return IssueType.GLOSSARY_VIOLATION

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

            # Word boundary regex for source
            pattern_ru = re.compile(rf"\b{re.escape(term_ru)}\b", re.IGNORECASE)
            # Stem or substring match for target (to accommodate Turkic agglutinative suffixes)
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

                # If source contains the glossary term
                if pattern_ru.search(src_val):
                    # Check if target contains the approved term or stem
                    if not pattern_kk.search(tgt_val):
                        # Extra check: if source string is just the term itself, higher severity
                        is_exact_match = src_val.strip().lower() == term_ru.lower()
                        severity = Severity.HIGH if is_exact_match else Severity.MEDIUM

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
                                suggestion=term_kk if is_exact_match else None,
                                confidence=0.90,
                                reviewed_by_human=False,
                            )
                        )

        return findings
