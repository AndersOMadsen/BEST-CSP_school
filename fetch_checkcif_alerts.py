#!/usr/bin/env python3
"""
fetch_checkcif_alerts.py
========================

Download the IUCr checkCIF / PLATON data-validation alert documentation and
turn it into a machine-readable reference (JSON + Markdown) for tools like
Claude Code.

Background
----------
The page https://journals.iucr.org/services/cif/datavalidation.html is an index.
The full, detailed descriptions of every alert live on TWO master listing pages
that it links to:

  * platon.html   -> all PLATON geometry / symmetry tests (PLAT### codes)
  * autolist.html -> all CIF-consistency tests (PROC-NAME entries:
                     CELLZ01, CRYSR01, FORMU01, ...)

Each individual alert also has its own subpage (e.g. PLAT112.html, CELLZ_01.html)
but those subpages contain the SAME text as the two master pages, just split up.
So mirroring the two master pages captures essentially all the content, and is
far more robust than crawling ~600 little pages.

This script:
  1. Downloads the index + the two master pages (and optionally every subpage).
  2. Saves the raw HTML so you have an exact local copy.
  3. Parses the master pages into structured records, one per alert code.
  4. Writes  checkcif_alerts.json  and  checkcif_alerts.md.

Why a local script?
-------------------
The IUCr server blocks some automated fetchers and rate-limits others. Running
this from your own machine (where you control the User-Agent and aren't behind a
restrictive egress proxy) is the reliable way to get the content. Be polite:
the script sleeps between requests by default.

Usage
-----
    python3 fetch_checkcif_alerts.py                 # master pages only (fast, recommended)
    python3 fetch_checkcif_alerts.py --subpages      # also mirror every individual alert page
    python3 fetch_checkcif_alerts.py --out ./cif_ref # choose output directory
    python3 fetch_checkcif_alerts.py --delay 2.0     # seconds between requests (default 1.0)

Dependencies
------------
    pip install requests beautifulsoup4
(requests is optional - falls back to urllib; beautifulsoup4 is optional too -
 falls back to a regex parser, though bs4 gives cleaner results.)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from html import unescape

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

BASE = "https://journals.iucr.org/services/cif/checking/"
INDEX_URL = "https://journals.iucr.org/services/cif/datavalidation.html"

# The two master pages that contain the full text of every alert.
MASTER_PAGES = {
    "platon": BASE + "platon.html",      # PLAT### geometry / symmetry tests
    "autolist": BASE + "autolist.html",  # CIF-consistency PROC-NAME tests
}

# Full browser-like headers. IUCr checks Sec-Fetch-* and Accept-Encoding in
# addition to User-Agent; missing them triggers a 403.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}


# ----------------------------------------------------------------------------
# HTTP layer
# Strategy: requests.Session (keeps cookies, sends all headers) → curl fallback
# ----------------------------------------------------------------------------

try:
    import requests
    _SESSION = requests.Session()
    _SESSION.headers.update(HEADERS)

    def http_get(url: str, timeout: int = 30) -> str:
        resp = _SESSION.get(url, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

except ImportError:
    import urllib.request

    def http_get(url: str, timeout: int = 30) -> str:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
        for enc in ("utf-8", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")


def _curl_get(url: str, timeout: int = 30) -> str:
    """Fallback: use the system curl binary (different TLS fingerprint from Python)."""
    cmd = [
        "curl", "-sL",
        "--max-time", str(timeout),
        "-A", HEADERS["User-Agent"],
        "-H", f"Accept: {HEADERS['Accept']}",
        "-H", f"Accept-Language: {HEADERS['Accept-Language']}",
        "-H", "Accept-Encoding: gzip, deflate, br",
        "-H", "Sec-Fetch-Dest: document",
        "-H", "Sec-Fetch-Mode: navigate",
        "-H", "Sec-Fetch-Site: none",
        "-H", "Sec-Fetch-User: ?1",
        "--compressed",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=timeout + 5)
    if result.returncode != 0:
        raise RuntimeError(f"curl exited {result.returncode}: {result.stderr.decode()[:200]}")
    for enc in ("utf-8", "latin-1"):
        try:
            return result.stdout.decode(enc)
        except UnicodeDecodeError:
            continue
    return result.stdout.decode("utf-8", errors="replace")


def _wayback_url(url: str) -> str:
    """Return the Wayback Machine URL for the most recent 2024 snapshot."""
    return f"https://web.archive.org/web/2024/{url}"


def fetch(url: str, delay: float, attempts: int = 3) -> str | None:
    """Fetch a URL with retries. Falls back to curl, then Wayback Machine."""
    for attempt in range(1, attempts + 1):
        try:
            html = http_get(url)
            time.sleep(delay)
            return html
        except Exception as exc:
            wait = delay * attempt * 2
            print(f"  ! attempt {attempt}/{attempts} failed for {url}: {exc}",
                  file=sys.stderr)
            if attempt < attempts:
                print(f"    retrying in {wait:.1f}s ...", file=sys.stderr)
                time.sleep(wait)

    # curl fallback (different TLS fingerprint from Python requests)
    print(f"  ~ Python requests blocked; trying curl ...", file=sys.stderr)
    try:
        html = _curl_get(url)
        if html.strip():
            time.sleep(delay)
            return html
    except Exception as exc:
        print(f"  ! curl also failed: {exc}", file=sys.stderr)

    # Wayback Machine fallback — archive.org caches these pages and is always open
    wb_url = _wayback_url(url)
    print(f"  ~ trying Wayback Machine: {wb_url}", file=sys.stderr)
    try:
        html = _curl_get(wb_url)
        if html.strip():
            print(f"    (served from Wayback Machine archive)", file=sys.stderr)
            time.sleep(delay)
            return html
    except Exception as exc:
        print(f"  ! Wayback Machine also failed: {exc}", file=sys.stderr)

    print(f"  X giving up on {url}", file=sys.stderr)
    return None


# ----------------------------------------------------------------------------
# HTML -> text
# ----------------------------------------------------------------------------

def html_to_text(html: str) -> str:
    """Convert an HTML page to readable plain text."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text("\n")
    except ImportError:
        # crude fallback: strip tags
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
        text = re.sub(r"(?s)<[^>]+>", "\n", text)
        text = unescape(text)

    # normalise whitespace
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Parsers for the two master pages
# ----------------------------------------------------------------------------

# A PLAT line looks like:  "PLAT112 Type_2 Test for additional symmetry [0, 1] (ADDSYM) ..."
PLAT_RE = re.compile(
    r"\b(PLAT\d{3})\b"          # code
    r"\s+(Type_\d+)?"           # optional Type_N
    r"\s*(.*)",                 # rest of the description
    re.IGNORECASE,
)

# An autolist entry looks like:
#   "PROC-NAME: CELLZ01 Type_1 PURPOSE: ... PROCEDURE: ..."
PROC_RE = re.compile(
    r"PROC-NAME:\s*(\S+)\s+(Type_\S+)?\s*",
    re.IGNORECASE,
)


def parse_platon(text: str) -> list[dict]:
    """
    Parse the platon.html master page into one record per PLAT code.

    The page is essentially a flat list; each alert starts with its PLATxxx
    code. We split on the code boundaries and keep the text that follows until
    the next code.
    """
    # Find all code positions
    matches = list(re.finditer(r"\bPLAT\d{3}\b", text))
    records: list[dict] = []
    seen: set[str] = set()

    for i, m in enumerate(matches):
        code = m.group(0).upper()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()

        # First occurrence of a code is usually the real definition; later ones
        # in the page tend to be cross-references. Keep the longest chunk.
        body = chunk[len(code):].strip()
        type_match = re.match(r"\s*(Type_\d+)", body)
        alert_type = type_match.group(1) if type_match else None
        if type_match:
            body = body[type_match.end():].strip()

        body = re.sub(r"\s+", " ", body)

        rec = {
            "code": code,
            "category": "PLATON_geometry_symmetry",
            "type": alert_type,
            "description": body,
            "source_page": MASTER_PAGES["platon"],
            "subpage": BASE + code + ".html",
        }

        if code in seen:
            # keep whichever description is longer / more informative
            for existing in records:
                if existing["code"] == code and len(body) > len(existing["description"]):
                    existing.update(rec)
                    break
        else:
            seen.add(code)
            records.append(rec)

    return records


def _normalise_autolist(text: str) -> str:
    """
    The rendered HTML puts section headers and their colons on separate lines:
        PROC-NAME\n:\nFORMU01  →  PROC-NAME: FORMU01
    Collapse these so the regex parsers can match them.
    """
    for kw in ("PROC-NAME", "PURPOSE", "PROCEDURE", "TEST", "CALCULATE"):
        # keyword on its own line, followed by bare ":" on the next line
        text = re.sub(rf"(?m)^({kw})\s*\n\s*:\s*\n?", rf"\1: ", text)
        text = re.sub(rf"(?m)^({kw})\s*\n\s*:", rf"\1:", text)
    return text


def parse_autolist(text: str) -> list[dict]:
    """
    Parse the autolist.html master page into one record per PROC-NAME entry.
    Each entry: PROC-NAME, Type, PURPOSE, PROCEDURE (+ embedded ALERT lines).
    """
    text = _normalise_autolist(text)
    parts = re.split(r"(?=PROC-NAME:)", text)
    records: list[dict] = []

    for part in parts:
        m = PROC_RE.match(part)
        if not m:
            continue
        name = m.group(1)
        alert_type = m.group(2)
        body = part[m.end():].strip()
        body = re.sub(r"\s+", " ", body)

        purpose = ""
        procedure = ""
        pm = re.search(r"PURPOSE:\s*(.*?)(?:PROCEDURE:|$)", body, re.IGNORECASE)
        if pm:
            purpose = pm.group(1).strip()
        prm = re.search(r"PROCEDURE:\s*(.*)", body, re.IGNORECASE)
        if prm:
            procedure = prm.group(1).strip()

        # collect the alert messages embedded in the procedure.
        # A real level is a single A/B/C/G token immediately after "ALERT",
        # followed by a space and then a quote or a capitalised word (the
        # message). "General ALERT" / "ALERT WARNING" are not lettered levels.
        alerts = re.findall(r"\bALERT\s+([ABCG])\b", body)
        levels = sorted(set(alerts))

        records.append({
            "code": name,
            "category": "CIF_consistency",
            "type": alert_type,
            "purpose": purpose,
            "procedure": procedure,
            "alert_levels": levels,
            "description": body,
            "source_page": MASTER_PAGES["autolist"],
        })

    return records


# ----------------------------------------------------------------------------
# Output writers
# ----------------------------------------------------------------------------

def write_json(records: list[dict], path: str) -> None:
    payload = {
        "source": "IUCr checkCIF / PLATON data-validation tests",
        "index_url": INDEX_URL,
        "master_pages": MASTER_PAGES,
        "generated_by": "fetch_checkcif_alerts.py",
        "alert_count": len(records),
        "alerts": records,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def write_markdown(records: list[dict], path: str) -> None:
    by_cat: dict[str, list[dict]] = {}
    for r in records:
        by_cat.setdefault(r["category"], []).append(r)

    lines = [
        "# checkCIF / PLATON data-validation alerts",
        "",
        f"Source: <{INDEX_URL}>",
        "",
        f"Total alerts captured: **{len(records)}**",
        "",
        "> Generated by `fetch_checkcif_alerts.py`. Each alert below corresponds",
        "> to a checkCIF validation test. Codes match those in checkCIF reports",
        "> (e.g. `PLAT112_ALERT_2_C`). Severity (A/B/C/G) is assigned at runtime",
        "> by checkCIF, not fixed per test; `type` is the test type number.",
        "",
    ]

    for cat in sorted(by_cat):
        recs = sorted(by_cat[cat], key=lambda r: r["code"])
        lines.append(f"## {cat} ({len(recs)} tests)")
        lines.append("")
        for r in recs:
            header = f"### {r['code']}"
            if r.get("type"):
                header += f"  ({r['type']})"
            lines.append(header)
            lines.append("")
            if r.get("purpose"):
                lines.append(f"**Purpose:** {r['purpose']}")
                lines.append("")
            if r.get("procedure"):
                lines.append(f"**Procedure:** {r['procedure']}")
                lines.append("")
            if r.get("alert_levels"):
                lines.append(f"**Alert levels:** {', '.join(r['alert_levels'])}")
                lines.append("")
            if r.get("description") and not r.get("purpose"):
                lines.append(r["description"])
                lines.append("")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ----------------------------------------------------------------------------
# Optional: discover & mirror every individual subpage
# ----------------------------------------------------------------------------

def discover_subpages(htmls: dict[str, str]) -> list[str]:
    """Find links to individual alert pages (PLAT112.html, CELLZ_01.html, ...)."""
    urls: set[str] = set()
    pat = re.compile(r'href="([^"]*?(?:PLAT\d{3}|[A-Z]{3,6}_?\d{2})\.html)"',
                     re.IGNORECASE)
    for html in htmls.values():
        for href in pat.findall(html):
            if href.startswith("http"):
                urls.add(href)
            else:
                urls.add(BASE + os.path.basename(href))
    return sorted(urls)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="checkcif_reference",
                    help="output directory (default: ./checkcif_reference)")
    ap.add_argument("--subpages", action="store_true",
                    help="also mirror every individual alert subpage (slow, ~600 requests)")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="seconds to wait between requests (default 1.0; be polite)")
    args = ap.parse_args()

    out = args.out
    raw_dir = os.path.join(out, "raw_html")
    os.makedirs(raw_dir, exist_ok=True)

    print("checkCIF alert downloader")
    print("=" * 60)

    # 1. index page (for reference / link discovery)
    htmls: dict[str, str] = {}
    print(f"\n[1] index: {INDEX_URL}")
    idx = fetch(INDEX_URL, args.delay)
    if idx:
        htmls["index"] = idx
        with open(os.path.join(raw_dir, "datavalidation.html"), "w",
                  encoding="utf-8") as f:
            f.write(idx)
        print("    saved.")

    # 2. master pages
    print("\n[2] master pages")
    for name, url in MASTER_PAGES.items():
        print(f"    {name}: {url}")
        html = fetch(url, args.delay)
        if html:
            htmls[name] = html
            with open(os.path.join(raw_dir, f"{name}.html"), "w",
                      encoding="utf-8") as f:
                f.write(html)
            print("      saved.")
        else:
            print("      FAILED - see errors above.")

    if "platon" not in htmls and "autolist" not in htmls:
        print("\nERROR: could not download either master page. "
              "Check your network / try increasing --delay.", file=sys.stderr)
        return 1

    # 3. optional subpages
    if args.subpages:
        print("\n[3] mirroring individual subpages")
        subs = discover_subpages(htmls)
        print(f"    discovered {len(subs)} subpage links")
        sub_dir = os.path.join(raw_dir, "subpages")
        os.makedirs(sub_dir, exist_ok=True)
        for i, url in enumerate(subs, 1):
            fname = os.path.basename(url)
            print(f"    ({i}/{len(subs)}) {fname}")
            html = fetch(url, args.delay)
            if html:
                with open(os.path.join(sub_dir, fname), "w",
                          encoding="utf-8") as f:
                    f.write(html)

    # 4. parse
    print("\n[4] parsing")
    records: list[dict] = []
    if "platon" in htmls:
        plat = parse_platon(html_to_text(htmls["platon"]))
        print(f"    PLATON tests parsed: {len(plat)}")
        records.extend(plat)
    if "autolist" in htmls:
        auto = parse_autolist(html_to_text(htmls["autolist"]))
        print(f"    consistency tests parsed: {len(auto)}")
        records.extend(auto)

    # 5. write outputs
    print("\n[5] writing outputs")
    json_path = os.path.join(out, "checkcif_alerts.json")
    md_path = os.path.join(out, "checkcif_alerts.md")
    write_json(records, json_path)
    write_markdown(records, md_path)
    print(f"    {json_path}")
    print(f"    {md_path}")
    print(f"    raw HTML in {raw_dir}/")

    print("\nDone. {} alerts captured.".format(len(records)))
    print("\nTip for Claude Code: point it at checkcif_alerts.json for lookups,")
    print("or checkcif_alerts.md for human-readable context.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
