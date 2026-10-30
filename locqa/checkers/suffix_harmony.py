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

    # Regex detecting {placeholder}-suffix or {placeholder}suffix
    # Matches Cyrillic affixes with or without hyphen
    AFFIX_REGEX = re.compile(
        r"(\{[a-zA-Z0-9_]+\})\s*([-–—]?)\s*([а-яәғқңөұүһіА-ЯӘҒҚҢӨҰҮҺІ\w]+)",
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
        # Common compounding suffixes e.g. -орында, -күн, -орын
        "орында", "күн", "орын",
    }

    @property
    def issue_type(self) -> IssueType:
        return IssueType.SUFFIX_HARMONY

    def propose_reformulation(self, text: str, placeholder: str, affix: str) -> Optional[str]:
        """Generate automated generic reformulation that avoids dynamic vowel harmony violation."""
        raw_affix = affix.lstrip("-–—").lower()
        ph_inner = placeholder.strip("{}").lower()

        # Dative cases with financial/cost variables ({price}, {bet}, {cost}, {amount})
        if any(w in ph_inner for w in ("price", "bet", "cost", "amount", "coin")):
            if raw_affix in ("ге", "ға", "қа", "ке"):
                # e.g. "{price}-ге сатып алу" -> "{price} бағасына сатып алу"
                pattern = re.escape(placeholder) + r"\s*[-–—]?\s*" + re.escape(affix.lstrip("-–—"))
                return re.sub(pattern, f"{placeholder} сомасына", text, count=1)

        # Service / provider variables ({provider}, {service})
        if "provider" in ph_inner or "service" in ph_inner:
            if raw_affix in ("ға", "ге", "қа", "ке"):
                pattern = re.escape(placeholder) + r"\s*[-–—]?\s*" + re.escape(affix.lstrip("-–—"))
                return re.sub(pattern, f"{placeholder} арқылы", text, count=1)

        # Numerical comparison ({max}, {min}, {limit})
        if any(w in ph_inner for w in ("max", "min", "limit", "count")):
            if raw_affix in ("нан", "нен", "дан", "ден", "тан", "тен"):
                pattern = re.escape(placeholder) + r"\s*[-–—]?\s*" + re.escape(affix.lstrip("-–—"))
                return re.sub(pattern, f"{placeholder} санынан", text, count=1)

        # Rank / Place ({place}, {playerplace})
        if "place" in ph_inner:
            # e.g. "{playerPlace}-орында" -> "{playerPlace} орында"
            pattern = re.escape(placeholder) + r"\s*[-–—]?\s*" + re.escape(affix.lstrip("-–—"))
            return re.sub(pattern, f"{placeholder} орында", text, count=1)

        # Level / ID ({id}, {level})
        if "id" in ph_inner or "level" in ph_inner:
            if raw_affix in ("ға", "ге", "қа", "ке"):
                pattern = re.escape(placeholder) + r"\s*[-–—]?\s*" + re.escape(affix.lstrip("-–—"))
                return re.sub(pattern, f"{placeholder} деңгейіне", text, count=1)

        # User / Player relations ({fromuser}, {touser}, {name}, {player})
        if any(w in ph_inner for w in ("from", "to", "user", "name", "player")):
            pattern = re.escape(placeholder) + r"\s*[-–—]?\s*" + re.escape(affix.lstrip("-–—"))
            if raw_affix in ("дан", "ден", "нан", "нен", "тан", "тен"):
                return re.sub(pattern, f"{placeholder} ойыншысынан", text, count=1)
            elif raw_affix in ("ға", "ге", "қа", "ке"):
                return re.sub(pattern, f"{placeholder} ойыншысына", text, count=1)

        # Universal fallback: separate hyphen or isolate with postposition
        pattern = re.escape(placeholder) + r"\s*[-–—]?\s*" + re.escape(affix.lstrip("-–—"))
        return re.sub(pattern, f"{placeholder} ({affix.lstrip('-–—')})", text, count=1)

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
            for ph, dash, sfx in matches:
                clean_sfx = sfx.lower()
                # Check if suffix matches Kazakh grammatical case affix or is hyphenated
                if dash or clean_sfx in self.KAZAKH_CASE_AFFIXES:
                    detected_issues.append((ph, f"{dash}{sfx}"))

            if not detected_issues:
                continue

            # Formulate evidence and suggestion
            details = [f"'{ph}{affix}'" for ph, affix in detected_issues]
            evidence = (
                f"Жестко зашитый аффикс после плейсхолдера: {', '.join(details)}. "
                f"Нарушает закон сингармонизма при динамической подстановке"
            )

            # Apply suggestions sequentially
            suggestion = tgt_val
            for ph, affix in detected_issues:
                reformulated = self.propose_reformulation(suggestion, ph, affix)
                if reformulated:
                    suggestion = reformulated

            findings.append(
                Finding(
                    key=key,
                    issue_type=self.issue_type,
                    severity=Severity.HIGH,
                    source=src_val,
                    target=tgt_val,
                    evidence=evidence,
                    suggestion=suggestion if suggestion != tgt_val else None,
                    confidence=0.96,
                    reviewed_by_human=False,
                )
            )

        return findings
