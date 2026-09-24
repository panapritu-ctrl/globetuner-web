#!/usr/bin/env python3
"""
Attach station logos to the web dataset.

The app's catalog carries no artwork, so the site was drawing lettered
placeholders for everything. Radio Browser publishes a favicon URL for a
good share of its stations, and the catalog was built from Radio Browser
in the first place, so the two can be matched on stream URL.

Only https logos are kept: an http image on an https page is blocked as
mixed content exactly like an http stream, so storing one would just draw
a broken image.

    python3 tools/add_logos.py
"""
import json
import urllib.parse
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
RB = "https://all.api.radio-browser.info/json/stations/search"
UA = "GlobeTunerWeb/1.0 (+https://globetuner-web.pages.dev)"
PAGE = 10000


def fetch_page(offset):
    q = urllib.parse.urlencode({
        "hidebroken": "true", "order": "clickcount", "reverse": "true",
        "limit": str(PAGE), "offset": str(offset),
    })
    req = urllib.request.Request(f"{RB}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def main():
    logos = {}
    offset = 0
    while True:
        batch = fetch_page(offset)
        if not batch:
            break
        for s in batch:
            fav = (s.get("favicon") or "").strip()
            if not fav.startswith("https://"):
                continue                     # http logo = blocked on https
            for key in (s.get("url_resolved"), s.get("url")):
                if key:
                    logos[key.strip()] = fav
        print(f"  offset {offset}: {len(batch)} rows, {len(logos)} logos mapped")
        offset += PAGE
        if len(batch) < PAGE or offset >= 60000:
            break

    matched = total = 0
    for path in list((DATA / "c").glob("*.json")) + [DATA / "featured.json"]:
        items = json.loads(path.read_text(encoding="utf-8"))
        for s in items:
            total += 1
            fav = logos.get(s["u"])
            if fav:
                s["f"] = fav
                matched += 1
        path.write_text(json.dumps(items, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")

    pct = 100 * matched // max(1, total)
    print(f"\nlogos attached to {matched}/{total} station records ({pct}%)")


if __name__ == "__main__":
    main()
