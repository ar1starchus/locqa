from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from locqa.checkers.base import BaseChecker
from locqa.models import ArbFile, Finding, IssueType, Severity
from locqa.translator import Translator


class InconsistentTermChecker(BaseChecker):
    """Detects terminology inconsistencies where the same source term or short UI string
    is translated into conflicting or divergent target variants across different keys.
    
    Provides multiple candidate options for reviewer selection:
    - Verifies canonical translation using verified glossary / dictionary / anchor keys.
    - Collects all alternative variants present in the file as interactive options.
    """

    # Common anchor UI key stems that indicate definitive, canonical translations
    ANCHOR_KEYS: Set[str] = {
        "cancel", "ok", "select", "delete", "back", "next", "close", "save",
        "edit", "search", "confirm", "apply", "create", "refresh", "continue",
        "accept", "decline", "yes", "no", "exit", "help", "settings",
    }

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
        translator: Optional[Translator] = context.get("translator")
        glossary = context.get("glossary")

        # Map: clean_source -> dict of { clean_target: list of (key, raw_source, raw_target) }
        source_clusters: Dict[str, Dict[str, List[Tuple[str, str, str]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        anchor_translations: Dict[str, str] = {}

        for key, src_entry in source.entries.items():
            tgt_entry = target.entries.get(key)
            if tgt_entry is None:
                continue

            s_raw = src_entry.value.strip()
            t_raw = tgt_entry.value.strip()

            if not s_raw or not t_raw:
                continue

            # Must contain at least a 2-letter word
            if not re.search(r"[a-zA-Zа-яА-ЯәіңғүұқөһӘІҢҒҮҰҚӨҺ]{2,}", s_raw):
                continue

            # Check concise phrases or single/two-word UI elements
            if len(s_raw) <= max_term_len and len(s_raw.split()) <= 4:
                norm_s = s_raw.lower()
                norm_t = t_raw.lower()
                source_clusters[norm_s][norm_t].append((key, s_raw, t_raw))

                # Check if this key is a canonical/anchor key
                k_clean = key.lower().replace("_", "").replace("-", "")
                s_clean = re.sub(r"[\W_]+", "", norm_s)
                if k_clean in self.ANCHOR_KEYS or k_clean == s_clean:
                    anchor_translations[norm_s] = norm_t

        findings: List[Finding] = []

        for norm_s, variants in source_clusters.items():
            if len(variants) < 2:
                continue

            # Determine verified / canonical translation
            verified_target: Optional[str] = anchor_translations.get(norm_s)

            # Check glossary if available
            if not verified_target and glossary:
                entry = glossary.get_by_ru(norm_s)
                if entry and entry.term_kk.strip().lower() in variants:
                    verified_target = entry.term_kk.strip().lower()

            # Check translator API / cache if available
            if not verified_target and translator:
                t_res = translator.translate_term(norm_s, source=source, target=target)
                if t_res and t_res.lower() in variants:
                    verified_target = t_res.lower()

            # Sort variants: verified variant first (if any), then by occurrence frequency descending
            sorted_variants = sorted(
                variants.items(),
                key=lambda item: (item[0] == verified_target, len(item[1])),
                reverse=True,
            )

            canonical_norm = sorted_variants[0][0]

            for norm_t, occ in variants.items():
                if norm_t != canonical_norm:
                    for key, s_val, t_val in occ:
                        # Collect all alternative target variants present in the file
                        raw_options = [cand[0][2] for n_t, cand in sorted_variants if n_t != norm_t]

                        # Adapt casing of options to match the source key
                        options: List[str] = []
                        for ro in raw_options:
                            adapted = Translator.adapt_casing(ro, s_val)
                            if adapted not in options:
                                options.append(adapted)

                        suggestion = options[0] if options else None
                        options_formatted = ", ".join(repr(o) for o in options)
                        evidence = (
                            f"Термин '{s_val}' переведен как '{t_val}', тогда как в других местах файла "
                            f"используется: {options_formatted}"
                        )

                        findings.append(
                            Finding(
                                key=key,
                                issue_type=self.issue_type,
                                severity=Severity.MEDIUM,
                                source=s_val,
                                target=t_val,
                                evidence=evidence,
                                suggestion=suggestion,
                                options=options,
                                confidence=0.90 if verified_target else 0.85,
                                reviewed_by_human=False,
                            )
                        )

        return findings
