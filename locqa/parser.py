from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from locqa.models import ArbEntry, ArbFile


class ArbParser:
    """Robust parser for Flutter ARB localization files.
    
    Supports:
    - Multiple duplicate '@@comment' section markers
    - String keys and complex '@key' metadata objects
    - Accurate line numbering
    - Proper JSON escape sequences (\\n, \\t, \\uXXXX, \\\")
    """

    @classmethod
    def parse_file(cls, path: str) -> ArbFile:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return cls.parse_content(content, path=path)

    @classmethod
    def parse_content(cls, content: str, path: str = "") -> ArbFile:
        # Step 1: Index line numbers for each key in the raw file
        lines = content.splitlines()
        key_line_map: Dict[str, List[int]] = {}
        for line_idx, line in enumerate(lines, 1):
            for match in re.finditer(r'"([^"\\]*(?:\\.[^"\\]*)*)"\s*:', line):
                key_name = match.group(1)
                key_line_map.setdefault(key_name, []).append(line_idx)

        # Step 2: Use json.loads with object_pairs_hook to preserve duplicate keys like @@comment
        # in exact document order
        raw_pairs = json.loads(content, object_pairs_hook=lambda pairs: pairs)

        # Detect locale
        locale = ""
        # Check filename first as fallback (e.g. intl_kk.arb -> kk)
        base = os.path.basename(path)
        m_file = re.search(r"intl_([a-zA-Z0-9_-]+)\.arb$", base)
        if m_file:
            locale = m_file.group(1)

        entries: Dict[str, ArbEntry] = {}
        metadata: Dict[str, ArbEntry] = {}
        sections: List[str] = []
        current_section = "GENERAL"

        # Track usage count of each key to match with line numbers
        key_occurrence_count: Dict[str, int] = {}

        for item in raw_pairs:
            if not isinstance(item, tuple) or len(item) != 2:
                continue
            key, val = item

            # Determine line number for this occurrence
            occ = key_occurrence_count.get(key, 0)
            line_list = key_line_map.get(key, [])
            line_no = line_list[occ] if occ < len(line_list) else 0
            key_occurrence_count[key] = occ + 1

            if key == "@@locale":
                if isinstance(val, str) and val.strip():
                    locale = val.strip()
                continue

            if key == "@@comment":
                sec_name = str(val).strip()
                current_section = sec_name
                sections.append(sec_name)
                continue

            if key.startswith("@"):
                # Metadata block for key
                meta_target = key[1:]
                if isinstance(val, dict):
                    meta_dict = val
                elif isinstance(val, list):
                    meta_dict = dict(val)
                else:
                    meta_dict = {"description": str(val)}

                entry = ArbEntry(
                    key=key,
                    value=json.dumps(meta_dict, ensure_ascii=False),
                    raw_line=lines[line_no - 1] if 0 < line_no <= len(lines) else "",
                    line_number=line_no,
                    section=current_section,
                    is_meta=True,
                    meta_for_key=meta_target,
                    meta_attributes=meta_dict,
                )
                metadata[meta_target] = entry
                continue

            # Regular translation entry
            str_val = str(val) if val is not None else ""
            entry = ArbEntry(
                key=key,
                value=str_val,
                raw_line=lines[line_no - 1] if 0 < line_no <= len(lines) else "",
                line_number=line_no,
                section=current_section,
                is_meta=False,
            )
            entries[key] = entry

        # Attach metadata to entries
        for target_key, meta_entry in metadata.items():
            if target_key in entries:
                entries[target_key].meta_attributes = meta_entry.meta_attributes

        return ArbFile(
            path=path,
            locale=locale,
            entries=entries,
            metadata=metadata,
            sections=sections,
            raw_lines=lines,
        )

    @classmethod
    def write_file(
        cls,
        original_arb: ArbFile,
        output_path: str,
        replacements: Optional[Dict[str, str]] = None,
        additions: Optional[Dict[str, str]] = None,
        reviewed_keys: Optional[Dict[str, bool]] = None,
    ) -> None:
        """Write back ARB file preserving sections, comments, formatting, and inserting updates.
        
        Args:
            original_arb: Original parsed ArbFile
            output_path: Destination path
            replacements: Mapping of key -> new_value
            additions: Mapping of new_key -> value to append
            reviewed_keys: Mapping of key -> bool indicating if human reviewed
        """
        replacements = replacements or {}
        additions = additions or {}
        reviewed_keys = reviewed_keys or {}

        # Re-parse original pairs to preserve original order and duplicate @@comments
        if original_arb.path and os.path.exists(original_arb.path):
            with open(original_arb.path, "r", encoding="utf-8") as f:
                raw_content = f.read()
        elif original_arb.raw_lines:
            raw_content = "\n".join(original_arb.raw_lines)
        else:
            raw_content = "{}"

        raw_pairs = json.loads(raw_content, object_pairs_hook=lambda pairs: pairs)

        # Build output structure
        output_lines: List[str] = ["{"]
        total_items = len(raw_pairs) + len(additions)
        current_item_idx = 0

        # We will track which keys were written
        written_keys = set()

        for idx, (k, v) in enumerate(raw_pairs):
            written_keys.add(k)
            # If replacement exists for this key
            val_to_write = replacements.get(k, v)

            # Format JSON key and value
            if k == "@@locale":
                formatted_val = json.dumps(val_to_write, ensure_ascii=False)
                output_lines.append(f'  "@@locale": {formatted_val},')
            elif k == "@@comment":
                formatted_val = json.dumps(val_to_write, ensure_ascii=False)
                output_lines.append("")
                output_lines.append(f'  "@@comment": {formatted_val},')
            elif k.startswith("@"):
                # Metadata block
                formatted_val = json.dumps(val_to_write, ensure_ascii=False, indent=2)
                # Indent metadata object
                indented = "\n".join("  " + line if i > 0 else line for i, line in enumerate(formatted_val.splitlines()))
                output_lines.append(f'  "{k}": {indented},')
            else:
                formatted_val = json.dumps(str(val_to_write), ensure_ascii=False)
                output_lines.append(f'  "{k}": {formatted_val},')

                # If there is newly added metadata for this key, write it right after
                meta_key = f"@{k}"
                if meta_key in replacements and meta_key not in [rk for rk, _ in raw_pairs]:
                    meta_val = replacements[meta_key]
                    formatted_meta = json.dumps(meta_val, ensure_ascii=False, indent=2)
                    indented_meta = "\n".join("  " + line if i > 0 else line for i, line in enumerate(formatted_meta.splitlines()))
                    output_lines.append(f'  "{meta_key}": {indented_meta},')
                    written_keys.add(meta_key)

        # Add any additions (e.g. missing untranslated keys)
        for k, v in additions.items():
            if k not in written_keys:
                if isinstance(v, dict):
                    formatted_val = json.dumps(v, ensure_ascii=False, indent=2)
                    indented = "\n".join("  " + line if i > 0 else line for i, line in enumerate(formatted_val.splitlines()))
                    output_lines.append(f'  "{k}": {indented},')
                else:
                    formatted_val = json.dumps(str(v), ensure_ascii=False)
                    output_lines.append(f'  "{k}": {formatted_val},')

        # Fix trailing comma on last non-empty line
        for i in range(len(output_lines) - 1, -1, -1):
            if output_lines[i].endswith(","):
                output_lines[i] = output_lines[i][:-1]
                break

        output_lines.append("}\n")
        result_text = "\n".join(output_lines)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result_text)
