from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from locqa.checkers.base import BaseChecker
from locqa.models import ArbFile, Finding, IssueType, Severity


class SuffixHarmonyChecker(BaseChecker):
    """Detects hardcoded case suffixes/affixes attached directly to placeholders.
    
    In agglutinative languages like Kazakh (and Turkic languages), the choice of affix
    (e.g., -ға/-ге/-қа/-ке, -дан/-ден/-нан/-нен, -ды/-ді/-ты/-ті) depends strictly on
    vowel harmony and the final consonant of the dynamic runtime word (name, provider, amount).
    
    Hardcoding an affix after {var} breaks grammar whenever the runtime substitution
    does not match the hardcoded vowel harmony.
    """

    # Regex detecting {placeholder}-suffix (hyphenated) or {placeholder}suffix (directly attached without space)
    # Never matches separate words preceded by whitespace (e.g. '{days} күн' or '{place} орын')
    AFFIX_REGEX = re.compile(
        r"(\{[a-zA-Z0-9_]+\})(?:([-–—])\s*([а-яәғқңөұүһіА-ЯӘҒҚҢӨҰҮҺІ\w]+)|([а-яәғқңөұүһіА-ЯӘҒҚҢӨҰҮҺІ\w]+))",
        re.UNICODE,
    )

    # Common grammatical case endings in Kazakh
    KAZAKH_CASE_AFFIXES = {
        # Dative-directional (-ға, -ге, -қа, -ке)
        "ға", "ге", "қа", "ке",
        # Ablative (-дан, -ден, -тан, -тен, -нан, -нен)
        "дан", "ден", "тан", "тен", "нан", "нен",
        # Locative (-да, -де, -та, -те, -нда, -нде)
        "да", "де", "та", "те", "нда", "нде",
        # Accusative (-ны, -ні, -ты, -ті, -ды, -ді)
        "ны", "ні", "ты", "ті", "ды", "ді",
        # Genitive (-ның, -нің, -дың, -дің, -тың, -тің)
        "ның", "нің", "дың", "дің", "тың", "тің",
        # Instrumental (-мен, -бен, -пен)
        "мен", "бен", "пен",
    }

    @property
    def issue_type(self) -> IssueType:
        return IssueType.SUFFIX_HARMONY

    def check(
        self,
        source: ArbFile,
        target: ArbFile,
        context: Dict[str, Any] | None = None,
    ) -> List[Finding]:
        findings: List[Finding] = []

        # Only apply to languages that use vowel harmony affixes (e.g. Kazakh, Kyrgyz, Uzbek, etc.)
        locale = (target.locale or "").lower()
        if locale and locale not in ("kk", "kz", "uz", "ky", "tt", "ba"):
            return findings

        for key, tgt_entry in target.entries.items():
            tgt_val = tgt_entry.value
            src_entry = source.entries.get(key)
            src_val = src_entry.value if src_entry else ""

            matches = self.AFFIX_REGEX.findall(tgt_val)
            if not matches:
                continue

            detected_issues: List[Tuple[str, str]] = []
            for ph, dash, sfx_dash, sfx_direct in matches:
                sfx = sfx_dash if dash else sfx_direct
                clean_sfx = sfx.lower()
                # Check if suffix matches Kazakh grammatical case affix
                if clean_sfx in self.KAZAKH_CASE_AFFIXES:
                    detected_issues.append((ph, f"{dash}{sfx}" if dash else sfx))

            if not detected_issues:
                continue

            # Formulate evidence
            details = [f"'{ph}{affix}'" for ph, affix in detected_issues]
            evidence = (
                f"Жестко зашитый аффикс после плейсхолдера: {', '.join(details)}. "
                f"Нарушает закон сингармонизма при динамической подстановке"
            )

            findings.append(
                Finding(
                    key=key,
                    issue_type=self.issue_type,
                    severity=Severity.HIGH,
                    source=src_val,
                    target=tgt_val,
                    evidence=evidence,
                    suggestion=None,
                    confidence=0.90,
                    reviewed_by_human=False,
                )
            )

        return findings
