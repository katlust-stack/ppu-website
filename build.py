#!/usr/bin/env python3
"""
Static site generator for Psychiatric Practice Updates.

Usage:
    python3 build.py                    # Build from ppu_archive.json
    python3 build.py data/my_file.json  # Build from a specific JSON file

Output goes to dist/
"""
import json
import os
import re
import shutil
import sys
from html import escape

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SRC_JSON = sys.argv[1] if len(sys.argv) > 1 else "ppu_archive.json"
DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")

SUBSPECIALTIES = [
    "Mood Disorders", "Psychotic Disorders", "Anxiety & Trauma", "Addiction",
    "Sleep", "Neurocognitive", "Child & Adolescent", "Geriatric Psychiatry",
    "Psychopharmacology", "Neuromodulation", "Women's Mental Health",
    "Medical Psychiatry", "Psychotherapy", "Public Health & Policy", "Neuroscience",
]

EVIDENCE_TAGS = [
    "\U0001f7e2 Large RCT / Meta-analysis",
    "\U0001f7e1 Small RCT / Open-label",
    "\U0001f534 Observational / Case series",
    "\U0001f4cb Review / Viewpoint",
    "\u26a0\ufe0f Industry-funded",
    "\U0001f30d Generalizability concern",
]

SITE_TITLE = "Psychiatric Practice Updates"
SITE_SUBTITLE = "Curated journal article summaries for clinicians"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def slugify(text):
    s = text.lower().strip()
    s = s.replace("/", "-").replace("&", "and")
    s = re.sub(r"[^a-z0-9\-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


MONTH_ABBREVS = {
    "jan": "january", "feb": "february", "mar": "march", "apr": "april",
    "jun": "june", "jul": "july", "aug": "august", "sep": "september",
    "sept": "september", "oct": "october", "nov": "november", "dec": "december",
}
MONTH_FULL = set(MONTH_ABBREVS.values()) | {"may"}

STOP_WORDS = {"practice", "updates", "psychiatric", "docx", "pdf", "draft", "ppu"}


def tokenize_normalized(text):
    """Tokenize and expand month abbreviations to full names."""
    tokens = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip().split()
    return {MONTH_ABBREVS.get(t, t) for t in tokens} - STOP_WORDS


def find_doc_for_edition(edition_name, doc_files):
    """Find the best matching doc file for an edition name.
    Scores month-name matches higher than year matches."""
    ed_tokens = tokenize_normalized(edition_name)
    best = None
    best_score = (0, 0)  # (month_matches, total_matches)
    for fname in doc_files:
        f_tokens = tokenize_normalized(os.path.splitext(fname)[0])
        overlap = ed_tokens & f_tokens
        month_hits = len(overlap & MONTH_FULL)
        score = (month_hits, len(overlap))
        if score > best_score:
            best = fname
            best_score = score
        elif score == best_score and best is not None:
            if len(fname) < len(best):
                best = fname
    return best if best_score > (0, 0) else None


def pubmed_url(pmid):
    return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None


def doi_url(doi):
    return f"https://doi.org/{doi}" if doi else None


def e(text):
    """HTML-escape."""
    return escape(str(text)) if text else ""


def edition_sort_key(edition_name):
    """Sort editions chronologically. Returns (year, month_number)."""
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    name = edition_name.lower()
    # Extract year(s) — take the last 4-digit number as the primary year
    years = re.findall(r"\d{4}", name)
    year = int(years[-1]) if years else 0
    # Extract month names — take the first one for ordering
    found_months = [m for m in months if m in name]
    month = months.get(found_months[0], 0) if found_months else 0
    # For "December/January 2024-2025", use December of the first year
    if month == 12 and len(years) > 1:
        year = int(years[0])
    return (year, month)


# ---------------------------------------------------------------------------
# HTML fragments
# ---------------------------------------------------------------------------
def html_head(title, extra_path=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{e(title)} — {SITE_TITLE}</title>
<link rel="stylesheet" href="{extra_path}style.css">
</head>
<body>
"""


def html_header(active="home", extra_path=""):
    def cls(name):
        return ' class="active"' if active == name else ""
    return f"""<header class="site-header">
<div class="container">
  <div class="site-title"><a href="{extra_path}index.html">{SITE_TITLE}</a>
    <span class="site-subtitle">{SITE_SUBTITLE}</span>
  </div>
  <nav class="site-nav">
    <a href="{extra_path}index.html"{cls("home")}>Home</a>
    <a href="{extra_path}archive.html"{cls("archive")}>Browse All</a>
  </nav>
</div>
</header>
"""


def html_footer():
    return """<footer class="site-footer">
<div class="container">
  <p>&copy; Psychiatric Practice Updates. For educational purposes only. Not a substitute for clinical judgment.</p>
</div>
</footer>
</body>
</html>
"""


def render_tags_html(article):
    """Render subspecialty + evidence tags as pill spans."""
    card = article.get("clinical_card") or {}
    sub_tags = card.get("subspecialty_tags") or article.get("tags", {}).get("subspecialty", [])
    ev_tags = card.get("evidence_quality_tags") or article.get("tags", {}).get("evidence_quality", [])
    parts = []
    for t in sub_tags:
        parts.append(f'<span class="tag tag-subspecialty">{e(t)}</span>')
    for t in ev_tags:
        parts.append(f'<span class="tag tag-evidence">{e(t)}</span>')
    return "".join(parts)


def render_article_card(article, show_edition=True):
    """Render a single article as an expandable card."""
    card = article.get("clinical_card") or {}
    bottom_line = card.get("bottom_line", "")
    caveats = card.get("caveats", "")
    why = card.get("why_it_matters", "")
    sub_tags = card.get("subspecialty_tags") or article.get("tags", {}).get("subspecialty", [])
    ev_tags = card.get("evidence_quality_tags") or article.get("tags", {}).get("evidence_quality", [])

    tags_str = "|".join(sub_tags).lower()
    evidence_str = "|".join(ev_tags).lower()

    edition_html = f'<div class="article-edition">{e(article.get("edition", ""))}</div>' if show_edition else ""

    bottom_line_html = ""
    if bottom_line:
        bottom_line_html = f'<div class="article-bottom-line"><strong>Bottom line:</strong> {e(bottom_line)}</div>'

    caveat_html = ""
    if caveats:
        caveat_html = f'<div class="article-caveat">\u26a0 {e(caveats)}</div>'

    tags_html = render_tags_html(article)
    tags_div = f'<div class="article-tags">{tags_html}</div>' if tags_html else ""

    pmid = article.get("pmid", "")
    doi = article.get("doi", "")
    link_html = ""
    if pmid:
        link_html = f'<a class="pubmed-link" href="https://pubmed.ncbi.nlm.nih.gov/{e(pmid)}/" target="_blank" rel="noopener">\u2197 PubMed {e(pmid)}</a>'
    elif doi:
        link_html = f'<a class="pubmed-link" href="https://doi.org/{e(doi)}" target="_blank" rel="noopener">\u2197 DOI</a>'

    abstract_text = article.get("abstract", "")
    citation_text = article.get("citation", "")

    # Why it matters section
    why_html = ""
    if why:
        why_html = f'<div class="article-bottom-line" style="margin-top:0.75rem"><strong>Why it matters:</strong> {e(why)}</div>'

    return f"""<div class="article-card" data-title="{e(article.get('title',''))}" data-bottomline="{e(bottom_line)}" data-tags="{e(tags_str)}" data-evidence="{e(evidence_str)}">
  <div class="article-card-header">
    <div class="article-card-body">
      <div class="article-card-title">{e(article.get("title",""))}</div>
      {edition_html}
      {bottom_line_html}
      {caveat_html}
      {tags_div}
    </div>
    <div class="expand-icon">\u25BC</div>
  </div>
  <div class="article-card-detail">
    {why_html}
    <div class="article-abstract">{e(abstract_text)}</div>
    <div class="article-citation">{e(citation_text)}</div>
    {link_html}
  </div>
</div>
"""


def render_article_open(article):
    """Render an article card for issue pages with all content always visible."""
    card = article.get("clinical_card") or {}
    bottom_line = card.get("bottom_line", "")
    caveats = card.get("caveats", "")
    why = card.get("why_it_matters", "")

    bottom_line_html = ""
    if bottom_line:
        bottom_line_html = f'<div class="article-bottom-line"><strong>Bottom line:</strong> {e(bottom_line)}</div>'

    caveat_html = ""
    if caveats:
        caveat_html = f'<div class="article-caveat">\u26a0 {e(caveats)}</div>'

    tags_html = render_tags_html(article)
    tags_div = f'<div class="article-tags">{tags_html}</div>' if tags_html else ""

    why_html = ""
    if why:
        why_html = f'<div class="article-bottom-line"><strong>Why it matters:</strong> {e(why)}</div>'

    pmid = article.get("pmid", "")
    doi = article.get("doi", "")
    link_html = ""
    if pmid:
        link_html = f'<a class="pubmed-link" href="https://pubmed.ncbi.nlm.nih.gov/{e(pmid)}/" target="_blank" rel="noopener">View on PubMed \u2197</a>'
    elif doi:
        link_html = f'<a class="pubmed-link" href="https://doi.org/{e(doi)}" target="_blank" rel="noopener">View on DOI \u2197</a>'

    abstract_text = article.get("abstract", "")
    citation_text = article.get("citation", "")

    return f"""<div class="article-card article-card-open">
  <div class="article-card-body" style="padding:1.25rem">
    <div class="article-card-title">{e(article.get("title",""))}</div>
    <div class="article-citation">{e(citation_text)}</div>
    {link_html}
    <div class="article-abstract">{e(abstract_text)}</div>
    {bottom_line_html}
    {why_html}
    {caveat_html}
    {tags_div}
  </div>
</div>
"""


# ---------------------------------------------------------------------------
# Page generators
# ---------------------------------------------------------------------------
def build_index(editions):
    """Generate the homepage."""
    latest = editions[0]
    latest_slug = slugify(latest["edition"])

    issue_cards = []
    for ed in editions:
        slug = slugify(ed["edition"])
        issue_cards.append(f"""<div class="issue-card">
  <a href="issues/{slug}.html">
    <h3>{e(ed["edition"])}</h3>
    <div class="count">{ed["article_count"]} articles</div>
  </a>
</div>""")

    journals = [
        "Frontiers of Psychiatry", "Neuropsychopharmacology",
        "PLOS Mental Health and Psychiatry", "Depression and Anxiety",
        "Journal of the American Academy of Child and Adolescent Psychiatry",
        "American Journal of Geriatric Psychiatry",
        "Journal of the Academy of Consult-Liaison Psychiatry",
        "Journal of Child Psychology and Psychiatry and Allied Disciplines",
        "Psychotherapy and Psychosomatics",
        "Journal of Neurology Neurosurgery and Psychiatry",
        "British Journal of Psychiatry", "Molecular Psychiatry",
        "JAMA Psychiatry", "JAMA", "Translational Psychiatry",
        "American Journal of Psychiatry", "Journal of Clinical Psychiatry",
        "Journal of Clinical Psychopharmacology", "World Psychiatry",
        "Psychological Medicine", "Acta Psychiatrica Scandinavica",
        "Biological Psychiatry", "Schizophrenia Bulletin",
        "The Lancet Psychiatry", "Bipolar Disorders",
        "International Journal of Bipolar Disorders",
    ]
    journals_html = "".join(f"<li>{e(j)}</li>" for j in sorted(journals))

    return (
        html_head("Home")
        + html_header("home")
        + f"""
<main class="container">
  <section class="hero">
    <h1>{SITE_TITLE}</h1>
  </section>

  <section class="about-section">
    <h2>About</h2>
    <p>Psychiatric Practice Updates is a free monthly digest of curated psychiatry journal articles.
       Our team conducts reviews of over 20 peer-reviewed journals each month with the goal of
       selecting articles that are interesting, impactful, and clinically relevant. Through our
       reviews, we may also highlight articles that advance our scientific understanding of mental
       illness or service delivery.</p>
    <p>This digest was founded by <a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC11837292/" target="_blank" rel="noopener">Dr.&nbsp;Joel&nbsp;Yager</a>
       who, for years, compiled and distributed monthly issues of articles that &ldquo;caught his
       eye&rdquo; to psychiatrists across the world and the lifelong learning continuum. With his
       retirement, he passed the project to the Psychiatric Practice Updates Committee. We are deeply
       grateful for Dr.&nbsp;Yager&rsquo;s generosity, his love of learning, and his enduring influence on
       psychiatric education. He is greatly missed.</p>
  </section>

  <section class="about-section">
    <h2>Committee</h2>
    <p><strong>Chairs:</strong> Katrina DeBonis, MD and Jane Eisen, MD</p>
    <p><strong>Members:</strong> Michael Fiori, MD, David Fogelson, MD, Michael Gitlin, MD,
       Raphaela Gold, MD MSc, Kevin Kennedy, MD, Stephen Marder, MD, Collin Price, MD</p>
  </section>

  <section class="latest-issue">
    <h2>Latest Issue: {e(latest["edition"])}</h2>
    <div class="meta">{latest["article_count"]} article summaries</div>
    <a class="btn" href="issues/{latest_slug}.html">Read the latest issue &rarr;</a>
  </section>

  <section class="issue-list-section">
    <h2>All Issues</h2>
    <div class="issue-grid">
      {"".join(issue_cards)}
    </div>
  </section>

  <section class="about-section journals-section">
    <h2>Journals Reviewed Each Month</h2>
    <ul class="journal-list">
      {journals_html}
    </ul>
  </section>
</main>
"""
        + html_footer()
    )


def build_archive(editions):
    """Generate the archive/browse page with filters."""
    # Collect all articles
    all_articles = []
    for ed in editions:
        for art in ed["articles"]:
            all_articles.append(art)

    # Subspecialty options
    sub_options = ['<option value="">All subspecialties</option>']
    for s in SUBSPECIALTIES:
        sub_options.append(f'<option value="{e(s.lower())}">{e(s)}</option>')

    ev_options = ['<option value="">All evidence types</option>']
    for ev in EVIDENCE_TAGS:
        # Strip emoji prefix for the value to match data-evidence attributes
        ev_plain = ev.split(" ", 1)[1] if " " in ev else ev
        ev_options.append(f'<option value="{e(ev_plain.lower())}">{e(ev)}</option>')

    cards_html = "\n".join(render_article_card(a, show_edition=True) for a in all_articles)

    return (
        html_head("Browse All Articles")
        + html_header("archive")
        + f"""
<main class="container">
  <div class="page-header">
    <h1>Browse All Articles</h1>
    <p>{len(all_articles)} articles across {len(editions)} issues</p>
  </div>

  <div class="filter-bar">
    <div class="filter-row">
      <div class="filter-group">
        <label for="search-input">Search</label>
        <input type="text" id="search-input" placeholder="Search titles and bottom lines\u2026">
      </div>
      <div class="filter-group">
        <label for="subspecialty-filter">Subspecialty</label>
        <select id="subspecialty-filter">
          {"".join(sub_options)}
        </select>
      </div>
      <div class="filter-group">
        <label for="evidence-filter">Evidence Quality</label>
        <select id="evidence-filter">
          {"".join(ev_options)}
        </select>
      </div>
    </div>
  </div>

  <div class="filter-results" id="results-count">{len(all_articles)} of {len(all_articles)} articles</div>

  <div class="article-list" id="article-list">
    {cards_html}
    <div class="no-results" id="no-results" style="display:none">No articles match your filters.</div>
  </div>
</main>
<script src="app.js"></script>
"""
        + html_footer()
    )


PODCAST_LINKS = {
    "December/January 2025-2026": "https://notebooklm.google.com/notebook/be4ea3af-b4f1-42a4-8fcc-278941f0e267?artifactId=9449899e-5ec4-478d-a376-ca8ff776dc0f",
    "November 2025": "https://notebooklm.google.com/notebook/4c01cd47-e6a6-48dd-bfbe-57f88e19a510?artifactId=3a7ef740-5c05-4f9c-9f58-2e560abc6c5d",
    "October 2025": "https://notebooklm.google.com/notebook/2b5cd164-f44d-414e-bec6-a900ed32c111?artifactId=6c336fba-80c6-40be-b496-79c0a61cf258",
    "September 2025": "https://notebooklm.google.com/notebook/d8a6ec3f-5cef-4b23-9c2c-4a6993f12f23?artifactId=1e9737a8-22ea-4910-9648-f5bcca706584",
    "July/August 2025": "https://notebooklm.google.com/notebook/24df422b-7200-4f5b-9f6e-eea24eced4d5?artifactId=23030539-9299-4770-848e-5d9a2f6973e6",
    "June 2025": "https://notebooklm.google.com/notebook/ec3eda99-578e-481d-a999-594630877c0b?artifactId=57d20454-33d0-432d-9be5-5c577e3fbb99",
    "May 2025": "https://notebooklm.google.com/notebook/d1ff65e2-daba-4189-8e65-27cf64072dad?artifactId=c6c1a3ba-d391-408f-b56d-94004b75021b",
    "April 2025": "https://notebooklm.google.com/notebook/7719f25b-49d4-491a-a91d-12c964cec058?artifactId=3efedb21-3ba2-4e75-a8b8-c9994f3138ca",
    "March 2025": "https://notebooklm.google.com/notebook/3821bf4c-e37b-4621-9e4f-151d22815c85?artifactId=df8b45ec-fdad-40a7-96ac-4fbbb405967b",
    "February 2025": "https://notebooklm.google.com/notebook/6bbfc904-bfaf-4de7-a919-7fc8ce0ef944?artifactId=e31be70b-ab1c-47b9-b595-5a953b1a5186",
    "December/January 2024-2025": "https://notebooklm.google.com/notebook/560f7f82-02d3-4983-93ac-0cf46ec396d6?artifactId=3d7d29c9-9326-41ec-9462-274c055db565",
}


def build_issue_page(edition, editions, index):
    """Generate a single issue page."""
    prev_link = ""
    next_link = ""
    if index < len(editions) - 1:
        prev_ed = editions[index + 1]
        prev_slug = slugify(prev_ed["edition"])
        prev_link = f'<a href="{prev_slug}.html">&larr; {e(prev_ed["edition"])}</a>'
    else:
        prev_link = '<span class="disabled">&larr; Older</span>'

    if index > 0:
        next_ed = editions[index - 1]
        next_slug = slugify(next_ed["edition"])
        next_link = f'<a href="{next_slug}.html">{e(next_ed["edition"])} &rarr;</a>'
    else:
        next_link = '<span class="disabled">Newer &rarr;</span>'

    # Download button for original Word doc
    download_html = ""
    # Prefer explicit doc_file field, fall back to filename field, then fuzzy match
    doc_name = edition.get("doc_file", "")
    if not doc_name:
        fn = edition.get("filename", "")
        if fn and os.path.isfile(os.path.join(DOCS, fn)):
            doc_name = fn
    if not doc_name:
        doc_files = os.listdir(DOCS) if os.path.isdir(DOCS) else []
        doc_name = find_doc_for_edition(edition["edition"], doc_files) or ""
    if doc_name and os.path.isfile(os.path.join(DOCS, doc_name)):
        download_html = f'<a class="btn btn-download" href="../docs/{e(doc_name)}" download>&#8681; Download original document</a>'

    # Podcast section
    podcast_html = ""
    podcast_url = PODCAST_LINKS.get(edition["edition"], "")
    if podcast_url:
        podcast_html = f"""<section class="podcast-section">
    <h2>\U0001f399\ufe0f AI Podcast &mdash; Listen to this issue</h2>
    <p>AI-generated audio overview of this issue&rsquo;s key findings, powered by NotebookLM.</p>
    <a class="btn btn-podcast" href="{e(podcast_url)}" target="_blank" rel="noopener">\u25b6\ufe0f Listen on NotebookLM</a>
  </section>"""

    cards_html = "\n".join(render_article_open(a) for a in edition["articles"])

    return (
        html_head(edition["edition"], extra_path="../")
        + html_header("issues", extra_path="../")
        + f"""
<main class="container">
  <div class="page-header">
    <h1>{e(edition["edition"])}</h1>
    <p>{edition["article_count"]} articles</p>
    {download_html}
  </div>

  {podcast_html}

  <nav class="issue-nav">
    {prev_link}
    {next_link}
  </nav>

  <div class="article-list">
    {cards_html}
  </div>

  <nav class="issue-nav">
    {prev_link}
    {next_link}
  </nav>
</main>
"""
        + html_footer()
    )


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------
def main():
    print(f"Reading {SRC_JSON}...")
    with open(SRC_JSON, "r", encoding="utf-8") as f:
        editions = json.load(f)

    # Sort editions newest-first
    editions.sort(key=lambda ed: edition_sort_key(ed["edition"]), reverse=True)

    total_articles = sum(ed["article_count"] for ed in editions)
    print(f"Found {len(editions)} issues, {total_articles} articles total.")

    # Clean and create dist
    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(os.path.join(DIST, "issues"), exist_ok=True)

    # Copy static assets
    for fname in os.listdir(STATIC):
        src = os.path.join(STATIC, fname)
        dst = os.path.join(DIST, fname)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            print(f"  Copied {fname}")

    # Copy Word docs if the docs/ directory exists
    if os.path.isdir(DOCS):
        docs_dist = os.path.join(DIST, "docs")
        os.makedirs(docs_dist, exist_ok=True)
        for fname in os.listdir(DOCS):
            if fname.lower().endswith((".docx", ".doc", ".pdf")):
                shutil.copy2(os.path.join(DOCS, fname), os.path.join(docs_dist, fname))
                print(f"  Copied docs/{fname}")

    # Build pages
    with open(os.path.join(DIST, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_index(editions))
    print("  Built index.html")

    with open(os.path.join(DIST, "archive.html"), "w", encoding="utf-8") as f:
        f.write(build_archive(editions))
    print("  Built archive.html")

    for i, ed in enumerate(editions):
        slug = slugify(ed["edition"])
        path = os.path.join(DIST, "issues", f"{slug}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(build_issue_page(ed, editions, i))
        print(f"  Built issues/{slug}.html")

    print(f"\nDone! Site generated in {DIST}/")
    print(f"Open {DIST}/index.html in your browser to preview.")


if __name__ == "__main__":
    main()
