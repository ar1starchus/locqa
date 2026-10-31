from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

from locqa.engine import QAEngine
from locqa.fixer import ArbFixer
from locqa.glossary import Glossary, GlossaryBuilder
from locqa.llm import GeminiClient
from locqa.models import ArbFile, Finding
from locqa.parser import ArbParser
from locqa.reporter import Reporter
from locqa.translator import Translator
from locqa.transliteration import KazakhLatinTransliteration


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="locqa",
        description="Qazaq Loc QA — Universal Quality Assurance CLI for ARB / Flutter Localization",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command: check
    check_parser = subparsers.add_parser("check", help="Run localization QA checks")
    check_parser.add_argument(
        "--source",
        "-s",
        required=True,
        help="Path to source ARB file (e.g. intl_ru.arb)",
    )
    check_parser.add_argument(
        "--target",
        "-t",
        required=True,
        help="Path to target ARB file (e.g. intl_kk.arb, intl_uz.arb)",
    )
    check_parser.add_argument(
        "--glossary",
        "-g",
        default="glossary.csv",
        help="Path to terminology glossary CSV (default: glossary.csv)",
    )
    check_parser.add_argument(
        "--out",
        "-o",
        default="report.json",
        help="Path to write JSON findings report (default: report.json)",
    )
    check_parser.add_argument(
        "--html",
        default="report.html",
        help="Path to write HTML report dashboard (default: report.html)",
    )
    check_parser.add_argument(
        "--fix",
        default=None,
        help="Optional path to write fixed ARB file (e.g. intl_kk_fixed.arb)",
    )
    check_parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite fixed ARB if it already exists",
    )
    check_parser.add_argument(
        "--mark-reviewed",
        action="store_true",
        help="Mark auto-fixed strings as reviewed_by_human: true",
    )
    check_parser.add_argument(
        "--aux",
        nargs="*",
        default=[],
        help="Auxiliary locale files in format locale=path (e.g. uz=intl_uz.arb en=intl_en.arb)",
    )
    check_parser.add_argument(
        "--auto-glossary",
        action="store_true",
        help="Automatically generate glossary.csv if missing from source/target/aux pairs",
    )
    check_parser.add_argument(
        "--transliterate-latin",
        default=None,
        help="Bonus: Export target to official Kazakh Latin ARB with length verification",
    )
    check_parser.add_argument(
        "--gemini-key",
        default=None,
        help="Optional Gemini API key for semantic calque detection (or set GEMINI_API_KEY env var)",
    )
    check_parser.add_argument(
        "--translate-api",
        default=None,
        help="Optional custom translation API URL (default: Google Translate gtx)",
    )
    check_parser.add_argument(
        "--no-online-translate",
        action="store_true",
        help="Disable online translation API calls and use offline lexicon/corpus only",
    )

    # Command: apply (applies fixes from report.json without re-running checks)
    apply_parser = subparsers.add_parser("apply", help="Apply reviewed fixes from report.json to target ARB")
    apply_parser.add_argument("--target", "-t", required=True, help="Path to target ARB file (e.g. intl_kk.arb)")
    apply_parser.add_argument("--report", "-r", default="report.json", help="Path to report.json (default: report.json)")
    apply_parser.add_argument("--out", "-o", default="intl_kk_fixed.arb", help="Output fixed ARB (default: intl_kk_fixed.arb)")
    apply_parser.add_argument("--only-reviewed", action="store_true", help="Only apply fixes marked as reviewed_by_human: true")
    apply_parser.add_argument("--force", action="store_true", help="Force overwrite existing output file")

    # Command: glossary
    gloss_parser = subparsers.add_parser("build-glossary", help="Build glossary.csv from ARB files")
    gloss_parser.add_argument("--source", "-s", required=True, help="Source ARB (intl_ru.arb)")
    gloss_parser.add_argument("--target", "-t", required=True, help="Target ARB (intl_kk.arb)")
    gloss_parser.add_argument("--en", default=None, help="English ARB (intl_en.arb)")
    gloss_parser.add_argument("--out", "-o", default="glossary.csv", help="Output glossary CSV")

    # Command: transliterate
    trans_parser = subparsers.add_parser("transliterate", help="Transliterate Kazakh Cyrillic ARB to Latin")
    trans_parser.add_argument("--input", "-i", required=True, help="Input Cyrillic ARB")
    trans_parser.add_argument("--out", "-o", required=True, help="Output Latin ARB")

    return parser.parse_args(argv)


def run_check(args: argparse.Namespace) -> int:
    print(f"[*] Loading source ARB: {args.source}")
    src_arb = ArbParser.parse_file(args.source)

    print(f"[*] Loading target ARB: {args.target}")
    tgt_arb = ArbParser.parse_file(args.target)

    # Load auxiliary files if provided
    aux_files: Dict[str, ArbFile] = {}
    for item in args.aux:
        if "=" in item:
            loc, path = item.split("=", 1)
            if os.path.exists(path):
                print(f"[*] Loading auxiliary ARB ({loc}): {path}")
                aux_files[loc] = ArbParser.parse_file(path)

    # Auto-detect sibling aux files in target/source directory if not explicitly passed
    for base_path in (args.target, args.source):
        base_dir = os.path.dirname(os.path.abspath(base_path))
        for auto_loc in ("uz", "en"):
            if auto_loc not in aux_files:
                candidate = os.path.join(base_dir, f"intl_{auto_loc}.arb")
                if os.path.exists(candidate):
                    print(f"[*] Auto-detected auxiliary ARB ({auto_loc}): {candidate}")
                    aux_files[auto_loc] = ArbParser.parse_file(candidate)

    # Load or build glossary
    glossary: Optional[Glossary] = None
    if os.path.exists(args.glossary):
        print(f"[*] Loading glossary: {args.glossary}")
        glossary = Glossary.load_csv(args.glossary)
    elif args.auto_glossary or not os.path.exists(args.glossary):
        print(f"[*] Generating glossary automatically: {args.glossary}")
        en_arb = aux_files.get("en")
        glossary = GlossaryBuilder.build_from_arb(src_arb, tgt_arb, en_arb=en_arb)
        glossary.save_csv(args.glossary)
        print(f"[✓] Saved glossary with {len(glossary.entries)} terms to {args.glossary}")

    # Setup context
    context = {
        "glossary": glossary,
        "auxiliary_arb_files": aux_files,
        "gemini_client": GeminiClient(api_key=args.gemini_key),
        "translator": Translator(
            api_url=args.translate_api,
            enable_online=not args.no_online_translate,
        ),
    }

    # Run QA Engine
    print("[*] Running localization checks...")
    engine = QAEngine()
    findings = engine.run(src_arb, tgt_arb, context=context)

    print(f"[✓] Completed QA checks: {len(findings)} findings detected.")

    # Save reports
    if args.out:
        Reporter.save_json(findings, args.out)
        print(f"[✓] Saved JSON report: {args.out}")

    if args.html:
        with open(args.target, "r", encoding="utf-8") as f:
            target_raw = f.read()
        Reporter.save_html(
            findings,
            args.html,
            source_name=os.path.basename(args.source),
            target_name=os.path.basename(args.target),
            target_raw_content=target_raw,
        )
        print(f"[✓] Saved HTML dashboard: {args.html}")

    # Generate fixed ARB if requested
    if args.fix:
        if os.path.exists(args.fix) and not args.force:
            print(
                f"[i] Файл {args.fix} уже существует и НЕ был перезаписан "
                f"(защита от случайной потери ручных правок). Используйте --force для перезаписи."
            )
        else:
            applied_cnt, _ = ArbFixer.apply_fixes(
                target_arb=tgt_arb,
                findings=findings,
                output_path=args.fix,
                mark_all_reviewed=args.mark_reviewed,
            )
            print(f"[✓] Applied {applied_cnt} automatic fixes to {args.fix}")

    # Bonus: Latin transliteration
    if args.transliterate_latin:
        print(f"[*] Transliterating target to official Latin script: {args.transliterate_latin}")
        latin_entries = {}
        for k, e in tgt_arb.entries.items():
            latin_entries[k] = KazakhLatinTransliteration.transliterate_text(e.value)

        ArbParser.write_file(tgt_arb, args.transliterate_latin, replacements=latin_entries)
        overflows = KazakhLatinTransliteration.verify_lengths(
            {k: e.value for k, e in tgt_arb.entries.items()}
        )
        print(f"[✓] Generated Latin ARB: {args.transliterate_latin} (noted {len(overflows)} length shifts)")

    return 0


def run_apply(args: argparse.Namespace) -> int:
    if os.path.exists(args.out) and not args.force:
        print(f"[!] Файл {args.out} уже существует. Используйте --force для перезаписи.")
        return 1

    tgt_arb = ArbParser.parse_file(args.target)
    with open(args.report, "r", encoding="utf-8") as f:
        data = json.load(f)

    findings: List[Finding] = []
    for item in data:
        if args.only_reviewed and not item.get("reviewed_by_human"):
            continue
        if item.get("suggestion"):
            findings.append(
                Finding(
                    key=item["key"],
                    issue_type=item["issue_type"],
                    severity=item["severity"],
                    source=item.get("source", ""),
                    target=item.get("target", ""),
                    evidence=item.get("evidence", ""),
                    suggestion=item["suggestion"],
                    confidence=item.get("confidence", 1.0),
                    reviewed_by_human=item.get("reviewed_by_human", False),
                )
            )

    applied_cnt, _ = ArbFixer.apply_fixes(
        target_arb=tgt_arb,
        findings=findings,
        output_path=args.out,
        mark_all_reviewed=False,
    )
    print(f"[✓] Применено {applied_cnt} правок из {args.report} в {args.out}")
    return 0


def run_build_glossary(args: argparse.Namespace) -> int:
    src_arb = ArbParser.parse_file(args.source)
    tgt_arb = ArbParser.parse_file(args.target)
    en_arb = ArbParser.parse_file(args.en) if args.en and os.path.exists(args.en) else None

    print(f"[*] Building glossary from {args.source} and {args.target}...")
    glossary = GlossaryBuilder.build_from_arb(src_arb, tgt_arb, en_arb=en_arb)
    glossary.save_csv(args.out)
    print(f"[✓] Saved glossary ({len(glossary.entries)} terms) to {args.out}")
    return 0


def run_transliterate(args: argparse.Namespace) -> int:
    arb = ArbParser.parse_file(args.input)
    latin_entries = {k: KazakhLatinTransliteration.transliterate_text(e.value) for k, e in arb.entries.items()}
    ArbParser.write_file(arb, args.out, replacements=latin_entries)
    print(f"[✓] Transliterated {len(latin_entries)} keys to {args.out}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if args.command == "check":
        return run_check(args)
    elif args.command == "apply":
        return run_apply(args)
    elif args.command == "build-glossary":
        return run_build_glossary(args)
    elif args.command == "transliterate":
        return run_transliterate(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
