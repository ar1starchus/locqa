from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple

from locqa.models import ArbFile, Finding
from locqa.parser import ArbParser


class ArbFixer:
    """Applies QA corrections and outputs compliant ARB files.
    
    Generates intl_fixed.arb with:
    - High-confidence deterministic fixes (placeholder typos, homoglyphs, orthography, suffix harmony)
    - Metadata flags (@key) marking reviewed_by_human status compliant with Flutter gen-l10n
    """

    @classmethod
    def apply_fixes(
        cls,
        target_arb: ArbFile,
        findings: List[Finding],
        output_path: str,
        mark_all_reviewed: bool = False,
        min_confidence: float = 0.85,
    ) -> Tuple[int, ArbFile]:
        """Apply findings that have suggestions and produce fixed ARB file.
        
        Args:
            target_arb: Original target ArbFile
            findings: List of detected findings
            output_path: Path to write intl_fixed.arb
            mark_all_reviewed: Flag to set reviewed_by_human=True
            min_confidence: Confidence threshold to auto-apply fix
            
        Returns:
            Tuple of (count_of_applied_fixes, updated_ArbFile)
        """
        replacements: Dict[str, str] = {}
        metadata_additions: Dict[str, dict] = {}
        reviewed_status: Dict[str, bool] = {}

        for f in findings:
            if not f.suggestion or f.confidence < min_confidence:
                continue

            current_val = target_arb.get_value(f.key)
            # Only apply if value actually changes
            if f.suggestion != current_val:
                replacements[f.key] = f.suggestion
                is_reviewed = mark_all_reviewed or f.reviewed_by_human
                f.reviewed_by_human = is_reviewed

                # Attach metadata flag for Flutter gen-l10n
                it_val = f.issue_type.value if hasattr(f.issue_type, "value") else str(f.issue_type)
                meta_key = f"@{f.key}"
                metadata_additions[meta_key] = {
                    "reviewed_by_human": is_reviewed,
                    "issue_type": it_val,
                    "previous_value": current_val or "",
                }

        # Merge metadata additions into replacements
        full_replacements = dict(replacements)
        for meta_k, meta_dict in metadata_additions.items():
            full_replacements[meta_k] = meta_dict

        ArbParser.write_file(
            original_arb=target_arb,
            output_path=output_path,
            replacements=full_replacements,
        )

        updated_arb = ArbParser.parse_file(output_path)
        return len(replacements), updated_arb
