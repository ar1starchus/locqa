from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

from locqa.checkers.base import BaseChecker
from locqa.models import ArbFile, Finding, IssueType, Severity


class InconsistentTermChecker(BaseChecker):
    """Detects terminology inconsistencies where the same source term or short UI string
    is translated into conflicting or divergent target variants across different keys.
    
    Uses reverse clustering:
    Maps source term -> {variant_1: [keys], variant_2: [keys]}.
    When an overwhelming majority of keys uses Variant A, keys using isolated
    Variant B are flagged with high confidence.
    """

    @property
    def issue_type(self) -> IssueType:
        return IssueType.INCONSISTENT_TERM

    def check(
        self,
        source: ArbFile,
        target: ArbFile,
        context: Dict[str, Any] | None = None,
    ) -> List[Finding]:
        context = context or {}
        max_term_len = context.get("inconsistent_max_term_len", 30)

        # Map: clean_source -> dict of { clean_target: list of (key, raw_source, raw_target) }
        source_clusters: Dict[str, Dict[str, List[Tuple[str, str, str]]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for key, src_entry in source.entries.items():
            tgt_entry = target.entries.get(key)
            if tgt_entry is None:
                continue

            s_raw = src_entry.value.strip()
            t_raw = tgt_entry.value.strip()

            if not s_raw or not t_raw:
                continue

            # Check concise phrases or single/two-word UI elements
            if len(s_raw) <= max_term_len and len(s_raw.split()) <= 4:
                # Normalize case for clustering check (while preserving raw strings)
                norm_s = s_raw.lower()
                norm_t = t_raw.lower()
                source_clusters[norm_s][norm_t].append((key, s_raw, t_raw))

        findings: List[Finding] = []

        for norm_src, target_variants in source_clusters.items():
            # If there are 2 or more distinct translations for this source term
            if len(target_variants) < 2:
                continue

            # Sort variants by popularity (number of keys)
            sorted_variants = sorted(
                target_variants.items(),
                key=lambda item: len(item[1]),
                reverse=True,
            )

            dominant_norm, dominant_occurrences = sorted_variants[0]
            dominant_count = len(dominant_occurrences)
            canonical_suggestion = dominant_occurrences[0][2]  # raw target from dominant

            # If dominant appears at least twice as often and has at least 2 occurrences
            if dominant_count < 2:
                continue

            for minor_norm, minor_occurrences in sorted_variants[1:]:
                minor_count = len(minor_occurrences)

                # Skip if it's just a 50/50 split on 2 keys total
                if dominant_count >= 2 and minor_count <= dominant_count // 2:
                    for key, s_val, t_val in minor_occurrences:
                        evidence = (
                            f"Термин '{s_val}' переведен как '{t_val}', тогда как в большинстве других мест "
                            f"({dominant_count} ключей) используется '{canonical_suggestion}'"
                        )

                        findings.append(
                            Finding(
                                key=key,
                                issue_type=self.issue_type,
                                severity=Severity.MEDIUM,
                                source=s_val,
                                target=t_val,
                                evidence=evidence,
                                suggestion=None,
                                confidence=0.88,
                                reviewed_by_human=False,
                            )
                        )

        return findings
