#!/usr/bin/env python3
"""
Generate clinical cards for all articles in ppu_archive.json using the Anthropic API.

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python3 generate_cards.py

Saves progress after each article to ppu_archive_with_cards.json so it's resumable.
If interrupted, just run again — it skips articles that already have cards.
"""
import json
import os
import sys
import time

import anthropic

INPUT_FILE = "ppu_archive.json"
OUTPUT_FILE = "ppu_archive_with_cards.json"

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
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    card = json.loads(text)

    # Validate tags
    card["subspecialty_tags"] = [t for t in card.get("subspecialty_tags", []) if t in SUBSPECIALTIES]
    card["evidence_quality_tags"] = [t for t in card.get("evidence_quality_tags", []) if t in EVIDENCE_TAGS]

    return card


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set.")
        print('Run: export ANTHROPIC_API_KEY="sk-ant-..."')
        sys.exit(1)

    client = anthropic.Anthropic()

    # Load input
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        editions = json.load(f)

    # Load existing output for resume support
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            output = json.load(f)
        # Build lookup of already-processed PMIDs
        done_pmids = set()
        for ed in output:
            for art in ed["articles"]:
                if art.get("clinical_card"):
                    done_pmids.add(art.get("pmid", ""))
        print(f"Resuming — {len(done_pmids)} articles already processed.")
    else:
        output = json.loads(json.dumps(editions))  # deep copy
        done_pmids = set()

    total = sum(len(ed["articles"]) for ed in output)
    processed = len(done_pmids)
    errors = 0

    print(f"Total articles: {total}")
    print(f"Remaining: {total - processed}")
    print()

    for ed_idx, ed in enumerate(output):
        for art_idx, article in enumerate(ed["articles"]):
            pmid = article.get("pmid", "")

            # Skip if already done
            if pmid and pmid in done_pmids:
                continue
            if article.get("clinical_card"):
                processed += 1
                continue

            processed += 1
            title_short = article["title"][:70]
            print(f"[{processed}/{total}] {title_short}...", end=" ", flush=True)

            try:
                card = generate_card(client, article)
                article["clinical_card"] = card
                # Also populate the tags field for compatibility
                article["tags"] = {
                    "subspecialty": card.get("subspecialty_tags", []),
                    "evidence_quality": card.get("evidence_quality_tags", []),
                }
                print("OK")
            except json.JSONDecodeError as exc:
                print(f"JSON error: {exc}")
                errors += 1
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
                except Exception as exc2:
                    print(f"Failed on retry: {exc2}")
                    errors += 1
            except Exception as exc:
                print(f"Error: {exc}")
                errors += 1

            # Save after each article
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDone! {processed} processed, {errors} errors.")
    print(f"Output saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
