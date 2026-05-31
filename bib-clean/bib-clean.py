#!/usr/bin/env python3
"""
bib-clean: A CLI tool to normalize and clean BibTeX .bib files.

Features:
- Merge duplicate DOIs
- Fix inconsistent fields
- Remove unused entries
- Flag missing required fields
- Output clean file or JSON
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set


REQUIRED_FIELDS = {
    "article": ["author", "title", "journal", "year"],
    "inproceedings": ["author", "title", "booktitle", "year"],
    "book": ["author", "title", "publisher", "year"],
    "incollection": ["author", "title", "booktitle", "year"],
    "phdthesis": ["author", "title", "school", "year"],
    "mastersthesis": ["author", "title", "school", "year"],
    "techreport": ["author", "title", "institution", "year"],
    "misc": ["title"],
}

NON_UTF8_PATTERN = re.compile(r'[^\x00-\x7F]')


def parse_bibtex(content: str) -> List[Dict]:
    """Parse BibTeX content into a list of entry dictionaries."""
    entries = []
    entry_pattern = re.compile(
        r'@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)\n\s*\}',
        re.DOTALL | re.IGNORECASE
    )

    for match in entry_pattern.finditer(content):
        entry_type = match.group(1).lower()
        citekey = match.group(2).strip()
        fields_str = match.group(3)

        fields = parse_fields(fields_str)
        entries.append({
            "type": entry_type,
            "citekey": citekey,
            "fields": fields,
            "raw": match.group(0)
        })

    return entries


def parse_fields(fields_str: str) -> Dict[str, str]:
    """Parse BibTeX field string into a dictionary."""
    fields = {}
    field_pattern = re.compile(
        r'(\w+)\s*=\s*("([^"]*)"|\{(.*?)\}|\S+)',
        re.DOTALL
    )

    for match in field_pattern.finditer(fields_str):
        key = match.group(1).lower()
        if match.group(3) is not None:
            value = match.group(3)
        elif match.group(4) is not None:
            value = match.group(4)
        else:
            value = match.group(2)

        fields[key] = value.strip()

    return fields


def find_duplicate_dois(entries: List[Dict]) -> Dict[str, List[str]]:
    """Find entries with duplicate DOIs."""
    doi_map: Dict[str, List[str]] = {}
    for entry in entries:
        doi = entry["fields"].get("doi", "").lower().strip()
        if doi:
            doi = normalize_doi(doi)
            if doi not in doi_map:
                doi_map[doi] = []
            doi_map[doi].append(entry["citekey"])
    return {k: v for k, v in doi_map.items() if len(v) > 1}


def find_duplicate_citekeys(entries: List[Dict]) -> List[str]:
    """Find entries with duplicate citekeys."""
    seen = {}
    duplicates = []
    for entry in entries:
        key = entry["citekey"]
        if key in seen:
            duplicates.append(key)
        else:
            seen[key] = True
    return duplicates


def check_missing_fields(entries: List[Dict]) -> List[Tuple[str, str, List[str]]]:
    """Check for missing required fields based on entry type."""
    missing = []
    for entry in entries:
        entry_type = entry["type"]
        required = REQUIRED_FIELDS.get(entry_type, [])
        fields = entry["fields"]
        missing_fields = [f for f in required if f not in fields]
        if missing_fields:
            missing.append((entry["citekey"], entry_type, missing_fields))
    return missing


def normalize_doi(doi: str) -> str:
    """Normalize DOI format."""
    doi = doi.strip()
    doi = re.sub(r'^https?://doi\.org/', '', doi)
    doi = re.sub(r'^doi:', '', doi)
    return doi


def fix_doi_fields(entries: List[Dict]) -> int:
    """Normalize DOI fields to just the DOI identifier."""
    fixed = 0
    for entry in entries:
        if "doi" in entry["fields"]:
            old = entry["fields"]["doi"]
            entry["fields"]["doi"] = normalize_doi(old)
            if old != entry["fields"]["doi"]:
                fixed += 1
    return fixed


def check_year_arxiv(entries: List[Dict]) -> List[Tuple[str, str, str]]:
    """Check year consistency with arXiv URLs."""
    issues = []
    for entry in entries:
        url = entry["fields"].get("url", "")
        year = entry["fields"].get("year", "")
        if "arxiv.org" in url.lower() and year:
            arxiv_match = re.search(r'arxiv\.org/abs/(\d{2})(\d{2})', url)
            if arxiv_match:
                arxiv_year = "20" + arxiv_match.group(1)
                if arxiv_year != year:
                    issues.append((entry["citekey"], year, arxiv_year))
    return issues


def check_encoding(entries: List[Dict]) -> List[str]:
    """Flag entries with non-UTF8 characters."""
    flagged = []
    for entry in entries:
        raw = entry["raw"]
        if NON_UTF8_PATTERN.search(raw):
            flagged.append(entry["citekey"])
    return flagged


def find_tex_files(directory: Path) -> List[Path]:
    """Find all .tex files in a directory."""
    return list(directory.glob("*.tex"))


def find_cited_keys(tex_files: List[Path]) -> Set[str]:
    """Extract all cited/referenced keys from .tex files."""
    keys = set()
    pattern = re.compile(r'\\(?:cite|ref|label|citep|citet|citeauthor|citeyear)\{([^}]+)\}')
    for tex_file in tex_files:
        try:
            content = tex_file.read_text(encoding="utf-8")
            for match in pattern.finditer(content):
                for key in match.group(1).split(","):
                    keys.add(key.strip())
        except Exception:
            continue
    return keys


def remove_unused_entries(entries: List[Dict], cited_keys: Set[str]) -> Tuple[List[Dict], int]:
    """Remove entries not cited in any .tex file."""
    cleaned = []
    removed = 0
    for entry in entries:
        if entry["citekey"] in cited_keys:
            cleaned.append(entry)
        else:
            removed += 1
    return cleaned, removed


def merge_duplicate_dois(entries: List[Dict], verbose: bool = False) -> Tuple[List[Dict], int]:
    """Merge entries with duplicate DOIs, keeping the one with more fields."""
    doi_map: Dict[str, List[Dict]] = {}
    for entry in entries:
        doi = entry["fields"].get("doi", "").lower().strip()
        if doi:
            doi = normalize_doi(doi)
            if doi not in doi_map:
                doi_map[doi] = []
            doi_map[doi].append(entry)

    merged_keys = set()
    merge_count = 0

    for doi, group in doi_map.items():
        if len(group) <= 1:
            continue

        best = max(group, key=lambda e: len(e["fields"]))
        for entry in group:
            if entry["citekey"] != best["citekey"]:
                merged_keys.add(entry["citekey"])
                for key, value in entry["fields"].items():
                    if key not in best["fields"] or not best["fields"][key]:
                        best["fields"][key] = value
                        if verbose:
                            print(f"  Merged field '{key}' from {entry['citekey']} into {best['citekey']}")
                merge_count += 1

    cleaned = [e for e in entries if e["citekey"] not in merged_keys]
    return cleaned, merge_count


def format_output_message(
    filename: str,
    parsed_count: int,
    merge_count: int,
    missing_fields: List,
    removed_count: int,
    final_count: int,
    duplicate_keys: List[str],
    arxiv_issues: List,
    encoding_issues: List[str]
) -> str:
    """Format the summary output message."""
    lines = [
        f"\U0001f9f9 bib-clean: {filename}",
        "\u2501" * 30,
        "",
        f"  \u2705 Parsed {parsed_count} entries from {filename}",
    ]

    if merge_count > 0:
        lines.append(f"  \U0001f504 Merged {merge_count} duplicate DOI entries")

    if duplicate_keys:
        lines.append(f"  \u26a0\ufe0f  Found {len(duplicate_keys)} entries with duplicate citekeys:")
        for key in duplicate_keys[:5]:
            lines.append(f"     {key}")
        if len(duplicate_keys) > 5:
            lines.append(f"     ... and {len(duplicate_keys) - 5} more")

    if missing_fields:
        lines.append(f"  \u26a0\ufe0f  Found {len(missing_fields)} entries with missing required fields:")
        for citekey, etype, fields in missing_fields[:5]:
            lines.append(f"     {citekey} \u2014 missing {', '.join(fields)} (@{etype})")
        if len(missing_fields) > 5:
            lines.append(f"     ... and {len(missing_fields) - 5} more")

    if arxiv_issues:
        lines.append(f"  \U0001f50d Found {len(arxiv_issues)} year/arXiv mismatches:")
        for citekey, year, arxiv_year in arxiv_issues[:3]:
            lines.append(f"     {citekey} \u2014 year={year}, arXiv year={arxiv_year}")

    if encoding_issues:
        lines.append(f"  \u26a0\ufe0f  Found {len(encoding_issues)} entries with encoding issues")
        for key in encoding_issues[:3]:
            lines.append(f"     {key}")

    if removed_count > 0:
        lines.append(f"  \U0001f5d1\ufe0f  Removed {removed_count} unused entries (not cited in any .tex file)")

    if merge_count > 0 or removed_count > 0:
        lines.append(f"  \U0001f4ca Summary: {parsed_count} \u2192 {final_count} entries after cleanup")

    lines.append("")
    return "\n".join(lines)


def format_bibtex_entry(entry: Dict) -> str:
    """Format an entry back to BibTeX string."""
    lines = [f"@{entry['type']}{{{entry['citekey']},"]
    for key, value in entry["fields"].items():
        if value:
            if key in ("title", "booktitle", "journal"):
                lines.append(f"  {key} = {{{value}}},")
            else:
                lines.append(f"  {key} = \"{value}\",")
    lines.append("}")
    return "\n".join(lines)


def write_bibtex(entries: List[Dict], filepath: Optional[str]) -> str:
    """Write entries to a .bib file or return as string."""
    content = "\n\n".join(format_bibtex_entry(e) for e in entries)
    if filepath:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content + "\n")
    return content


def main():
    parser = argparse.ArgumentParser(
        description="Clean and normalize BibTeX .bib files"
    )
    parser.add_argument(
        "-i", "--input",
        required=True,
        help="Input .bib file path"
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output file path (default: overwrite input)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed information"
    )
    parser.add_argument(
        "--remove-unused",
        action="store_true",
        help="Remove entries not cited in any .tex file"
    )
    parser.add_argument(
        "--fix-doi",
        action="store_true",
        help="Normalize DOI fields (strip https://doi.org/ prefix)"
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File '{args.input}' not found", file=sys.stderr)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        content = f.read()

    entries = parse_bibtex(content)
    parsed_count = len(entries)

    # Find duplicate citekeys
    duplicate_keys = find_duplicate_citekeys(entries)

    # Find duplicate DOIs and merge
    duplicate_dois = find_duplicate_dois(entries)
    entries, merge_count = merge_duplicate_dois(entries, verbose=args.verbose)

    # Fix DOI fields if requested
    doi_fixed = 0
    if args.fix_doi:
        doi_fixed = fix_doi_fields(entries)

    # Check missing fields
    missing_fields = check_missing_fields(entries)

    # Check year/arXiv consistency
    arxiv_issues = check_year_arxiv(entries)

    # Check encoding
    encoding_issues = check_encoding(entries)

    # Remove unused if requested
    removed_count = 0
    if args.remove_unused:
        tex_files = find_tex_files(input_path.parent)
        if tex_files:
            cited_keys = find_cited_keys(tex_files)
            entries, removed_count = remove_unused_entries(entries, cited_keys)
        elif args.verbose:
            print("  No .tex files found, skipping unused entry removal", file=sys.stderr)

    final_count = len(entries)

    # JSON output
    if args.json:
        result = {
            "filename": str(input_path),
            "parsed": parsed_count,
            "merged_dois": merge_count,
            "doi_fields_fixed": doi_fixed,
            "duplicate_citekeys": duplicate_keys,
            "duplicate_dois": duplicate_dois,
            "missing_fields": [
                {"citekey": k, "type": t, "fields": f}
                for k, t, f in missing_fields
            ],
            "arxiv_year_mismatches": [
                {"citekey": k, "bib_year": y, "arxiv_year": a}
                for k, y, a in arxiv_issues
            ],
            "encoding_issues": encoding_issues,
            "removed_unused": removed_count,
            "final_count": final_count,
            "entries": [
                {"citekey": e["citekey"], "type": e["type"], "fields": e["fields"]}
                for e in entries
            ]
        }
        print(json.dumps(result, indent=2))
    else:
        # Summary output
        print(format_output_message(
            str(input_path),
            parsed_count,
            merge_count,
            missing_fields,
            removed_count,
            final_count,
            duplicate_keys,
            arxiv_issues,
            encoding_issues
        ))

        # Write output
        output_path = args.output or str(input_path)
        write_bibtex(entries, output_path)
        if args.verbose:
            print(f"  \U0001f4be Written to {output_path}")


if __name__ == "__main__":
    main()
