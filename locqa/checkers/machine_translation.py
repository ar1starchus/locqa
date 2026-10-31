from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from locqa.checkers.base import BaseChecker
from locqa.llm import GeminiClient
from locqa.models import ArbFile, Finding, IssueType, Severity


class MachineTranslationChecker(BaseChecker):
    """Detects suspicious machine translation calques, unnatural word order,
    and Russian grammar patterns projected onto Kazakh/Uzbek strings.
    
    Combines:
    1. Offline syntactic pattern heuristics for Turkic SOV vs Russian SVO inversion
       (e.g., postpositions placed before nouns like 'үшін сіз' instead of 'сіз үшін',
       unnatural Russian conjunctions/constructions directly transliterated).
    2. Semantic LLM analysis via Gemini when API key is provided.
    """

    # Kazakh postpositions used as prepositions at the start of a clause (Russian preposition calques)
    # E.g. 'сіз үшін' is correct postposition; '*үшін сіз...' at clause start is a direct Russian 'для ...' calque.
    INVERTED_POSTPOSITION_PATTERNS = [
        (r"(?:^|[.,!?;]|\n)\s*\bүшін\s+(сіз|сен|ол|біз|олар|оны|мұны|бұны)\b", "Калька русской структуры 'для ...' (в казахском 'үшін' должно следовать после местоимения)"),
        (r"(?:^|[.,!?;]|\n)\s*\bбойынша\s+(сіз|ереже|заң|нұсқаулық)\b", "Калька предлога 'по ...' перед существительным"),
        (r"(?:^|[.,!?;]|\n)\s*\bарқылы\s+(сіз|қосымша|ойын)\b", "Калька предлога 'через ...' перед существительным"),
        (r"\b(және\s+растайсыз,\s+дегенді)\b", "Буквальная калька русской канцелярской формулировки"),
    ]

    @property
    def issue_type(self) -> IssueType:
        return IssueType.MACHINE_TRANSLATION_SUSPECT

    def check(
        self,
        source: ArbFile,
        target: ArbFile,
        context: Dict[str, Any] | None = None,
    ) -> List[Finding]:
        context = context or {}
        findings: List[Finding] = []
        target_locale = (target.locale or "").lower()

        # Step 1: Syntactic Heuristics (offline)
        if target_locale in ("kk", "kz"):
            for key, tgt_entry in target.entries.items():
                tgt_val = tgt_entry.value
                src_entry = source.entries.get(key)
                src_val = src_entry.value if src_entry else ""

                if not tgt_val or len(tgt_val.split()) < 3:
                    continue

                for pattern, desc in self.INVERTED_POSTPOSITION_PATTERNS:
                    match = re.search(pattern, tgt_val, re.IGNORECASE)
                    if match:
                        findings.append(
                            Finding(
                                key=key,
                                issue_type=self.issue_type,
                                severity=Severity.MEDIUM,
                                source=src_val,
                                target=tgt_val,
                                evidence=f"Подозрение на машинный перевод: {desc} (фрагмент: '{match.group(0)}')",
                                suggestion=None,
                                confidence=0.85,
                                reviewed_by_human=False,
                            )
                        )
                        break

        # Step 2: Semantic LLM Evaluation if Gemini is available
        gemini: Optional[GeminiClient] = context.get("gemini_client")
        if gemini and gemini.is_available:
            # Collect long complex sentences (length >= 40 chars) not already flagged
            already_flagged = {f.key for f in findings}
            candidates = []
            for k, tgt_entry in target.entries.items():
                if k in already_flagged:
                    continue
                src_entry = source.entries.get(k)
                if not src_entry:
                    continue
                s_val = src_entry.value.strip()
                t_val = tgt_entry.value.strip()
                if len(s_val) >= 40 and len(t_val) >= 40:
                    candidates.append({"key": k, "source": s_val, "target": t_val})

            # Process in small batches of 15
            for i in range(0, min(len(candidates), 60), 15):
                batch = candidates[i : i + 15]
                llm_results = gemini.analyze_translations(batch, source_lang="ru", target_lang=target_locale)
                for res in llm_results:
                    k = res.get("key")
                    if not k or k not in target.entries:
                        continue
                    src_e = source.entries.get(k)
                    findings.append(
                        Finding(
                            key=k,
                            issue_type=self.issue_type,
                            severity=Severity.HIGH,
                            source=src_e.value if src_e else "",
                            target=target.entries[k].value,
                            evidence=res.get("evidence", "Семантический анализ LLM: неестественный синтаксис/калька"),
                            suggestion=res.get("suggestion"),
                            confidence=float(res.get("confidence", 0.90)),
                            reviewed_by_human=False,
                        )
                    )

        return findings
