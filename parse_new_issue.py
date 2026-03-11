#!/usr/bin/env python3
"""
Parse a PPU Word doc into JSON and generate AI clinical cards.

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python3 parse_new_issue.py "docs/PPU February 2026.docx" "February 2026"

Outputs: new_issue.json (ready for add-issue.js)
"""
import json
import os
import re
import sys
import time

import docx
import anthropic

SUBSPECIALTIES = [
    "Mood Disorders", "Psychotic Disorders", "Anxiety & Trauma", "Addiction",
    "Sleep", "Neurocognitive", "Child & Adolescent", "Geriatric Psychiatry",
    "Psychopharmacology", "Neuromodulation", "Women's Mental Health",
    "Medical Psychiatry", "Psychotherapy", "Public Health & Policy", "Neuroscience",
]

EVIDENCE_TAGS = [
    "Large RCT / Meta-analysis",
    "Small RCT / Open-label",
    "Observational / Case series",
    "Review / Viewpoint",
    "Industry-funded",
    "Generalizability concern",
]

SYSTEM_PROMPT = """You are a psychiatry journal editor creating clinical summary cards for practicing psychiatrists.

Given an article's title, citation, and abstract, generate a clinical card with these fields:

1. bottom_line: One concise sentence on what this means for clinical practice. Write for a busy clinician — be direct and specific.

2. why_it_matters: 1-2 sentences on why a psychiatrist should care about this finding. Connect it to real clinical decisions or knowledge gaps.

3. caveats: Key methodological limitations in one sentence, or null if the study is robust with no notable concerns.

4. subspecialty_tags: 1-3 tags from this exact list (use exact spelling):
   """ + json.dumps(SUBSPECIALTIES) + """

5. evidence_quality_tags: All that apply from this exact list (use exact spelling):
   """ + json.dumps(EVIDENCE_TAGS) + """
   Apply "Industry-funded" if the study was funded by a pharmaceutical company.
   Apply "Generalizability concern" if the sample is narrow or results may not generalize.

Respond with ONLY valid JSON matching this schema:
{
  "bottom_line": "string",
  "why_it_matters": "string",
  "caveats": "string or null",
  "subspecialty_tags": ["string"],
  "evidence_quality_tags": ["string"]
}"""


def parse_docx(filepath, edition_name):
    """Parse a PPU Word doc into a list of article dicts."""
    doc = docx.Document(filepath)
    articles = []
    current = None

    for p in doc.paragraphs:
        style = p.style.name if p.style else ""
        text = p.text.strip()
        if not text:
            continue

        if style == "Heading 1":
            if current:
                current["abstract"] = current["abstract"].strip()
                articles.append(current)
            current = {
                "title": text,
                "citation": "",
                "authors": "",
                "pmid": "",
                "doi": "",
                "abstract": "",
                "edition": edition_name,
            }
        elif current is not None:
            if style == "Normal" and not current["citation"]:
                # First Normal paragraph after heading = citation
                current["citation"] = text
                # Extract PMID
                m = re.search(r'PMID:\s*(\d+)', text)
                if not m:
                    m = re.search(r'PMID\D*(\d+)', text)
                if m:
                    current["pmid"] = m.group(1)
                # Extract DOI
                m = re.search(r'doi:\s*(10\.[^\s,;]+)', text, re.I)
                if m:
                    doi = m.group(1).rstrip(".")
                    current["doi"] = doi
            elif "Normal" in style:
                # Abstract paragraphs
                if current["abstract"]:
                    current["abstract"] += "\n"
                current["abstract"] += text

    # Don't forget the last article
    if current:
        current["abstract"] = current["abstract"].strip()
        articles.append(current)

    return articles


def generate_card(client, article):
    """Call the Anthropic API to generate a clinical card for one article."""
    user_msg = f"""Title: {article['title']}

Citation: {article.get('citation', 'N/A')}

Abstract: {article.get('abstract', 'N/A')}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    card = json.loads(text)
    card["subspecialty_tags"] = [t for t in card.get("subspecialty_tags", []) if t in SUBSPECIALTIES]
    card["evidence_quality_tags"] = [t for t in card.get("evidence_quality_tags", []) if t in EVIDENCE_TAGS]
    return card


def main():
    if len(sys.argv) < 3:
        print('Usage: python3 parse_new_issue.py "docs/PPU February 2026.docx" "February 2026"')
        sys.exit(1)

    filepath = sys.argv[1]
    edition_name = sys.argv[2]

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    print(f"Parsing {filepath}...")
    articles = parse_docx(filepath, edition_name)
    print(f"Found {len(articles)} articles.\n")

    client = anthropic.Anthropic()
    errors = 0

    for i, article in enumerate(articles):
        title_short = article["title"][:70]
        print(f"[{i+1}/{len(articles)}] {title_short}...", end=" ", flush=True)
        try:
            card = generate_card(client, article)
            article["clinical_card"] = card
            article["tags"] = {
                "subspecialty": card.get("subspecialty_tags", []),
                "evidence_quality": card.get("evidence_quality_tags", []),
            }
            print("OK")
        except anthropic.RateLimitError:
            print("Rate limited — waiting 60s...")
            time.sleep(60)
            try:
                card = generate_card(client, article)
                article["clinical_card"] = card
                article["tags"] = {
                    "subspecialty": card.get("subspecialty_tags", []),
                    "evidence_quality": card.get("evidence_quality_tags", []),
                }
                print("OK (retry)")
            except Exception as exc:
                print(f"Failed on retry: {exc}")
                errors += 1
        except Exception as exc:
            print(f"Error: {exc}")
            errors += 1

    output = {
        "edition": edition_name,
        "filename": os.path.basename(filepath),
        "article_count": len(articles),
        "articles": articles,
    }

    out_path = "new_issue.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDone! {len(articles)} articles, {errors} errors.")
    print(f"Output saved to {out_path}")
    print(f'Run: node add-issue.js {out_path}')


if __name__ == "__main__":
    main()
