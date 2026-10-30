from __future__ import annotations

from typing import Any, Dict, List, Optional

from locqa.checkers.base import BaseChecker
from locqa.checkers.glossary import GlossaryChecker
from locqa.checkers.inconsistent_term import InconsistentTermChecker
from locqa.checkers.length import LengthOverflowChecker
from locqa.checkers.machine_translation import MachineTranslationChecker
from locqa.checkers.orthography import OrthographyChecker
from locqa.checkers.placeholder import PlaceholderChecker
from locqa.checkers.plural import PluralChecker
from locqa.checkers.same_as_source import SameAsSourceChecker
from locqa.checkers.suffix_harmony import SuffixHarmonyChecker
from locqa.checkers.untranslated import UntranslatedChecker
from locqa.checkers.wrong_language import WrongLanguageChecker
from locqa.models import ArbFile, Finding, IssueType, Severity


class QAEngine:
    """Core localization QA execution engine.
    
    Coordinates the execution of deterministic and semantic checkers,
    aggregates results, applies deduplication, and ranks findings.
    """

    def __init__(self, checkers: Optional[List[BaseChecker]] = None):
        if checkers is not None:
            self.checkers = checkers
        else:
            self.checkers = [
                UntranslatedChecker(),
                SameAsSourceChecker(),
                PlaceholderChecker(),
                PluralChecker(),
                LengthOverflowChecker(),
                SuffixHarmonyChecker(),
                OrthographyChecker(),
                WrongLanguageChecker(),
                InconsistentTermChecker(),
                GlossaryChecker(),
                MachineTranslationChecker(),
            ]

    def run(
        self,
        source: ArbFile,
        target: ArbFile,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Finding]:
        context = context or {}
        raw_findings: List[Finding] = []

        for checker in self.checkers:
            findings = checker.check(source, target, context=context)
            raw_findings.extend(findings)

        # Deduplicate and prioritize findings
        deduped = self._deduplicate_and_rank(raw_findings)
        return deduped

    def _deduplicate_and_rank(self, findings: List[Finding]) -> List[Finding]:
        """Group findings by (key, issue_type) to avoid duplicate alerts.
        Also resolve conflicts where a key triggers both a generic issue
        and a more specific issue (e.g. wrong_language vs same_as_source).
        """
        # Map: (key, issue_type) -> Finding
        seen: Dict[tuple[str, str], Finding] = {}
        for f in findings:
            it = f.issue_type.value if isinstance(f.issue_type, IssueType) else str(f.issue_type)
            k = (f.key, it)
            if k not in seen:
                seen[k] = f
            else:
                # Keep the one with higher confidence
                if f.confidence > seen[k].confidence:
                    seen[k] = f

        # If a key is flagged as wrong_language, drop same_as_source for that key
        wrong_lang_keys = {f.key for f in seen.values() if f.issue_type == IssueType.WRONG_LANGUAGE}
        # If a key is flagged as glossary_violation, drop inconsistent_term for that key
        glossary_keys = {f.key for f in seen.values() if f.issue_type == IssueType.GLOSSARY_VIOLATION}
        final_list: List[Finding] = []

        for (key, it), finding in seen.items():
            if it == IssueType.SAME_AS_SOURCE.value and key in wrong_lang_keys:
                continue
            if it == IssueType.INCONSISTENT_TERM.value and key in glossary_keys:
                continue
            final_list.append(finding)

        # Rank by severity (HIGH > MEDIUM > LOW) and then confidence
        severity_order = {Severity.HIGH.value: 3, Severity.MEDIUM.value: 2, Severity.LOW.value: 1}

        def sort_key(f: Finding):
            sev_val = f.severity.value if isinstance(f.severity, Severity) else str(f.severity)
            return (severity_order.get(sev_val, 0), f.confidence)

        final_list.sort(key=sort_key, reverse=True)
        return final_list
