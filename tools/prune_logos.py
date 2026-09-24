#!/usr/bin/env python3
"""
Drop logo URLs that don't actually resolve to an image.

About a third of the favicons Radio Browser lists are stale. A dead one
isn't visually broken -- the card falls back to its lettered tile -- but
the browser still pays for the failed request, once per station on screen.
Checking them once at build time is cheaper than every visitor discovering
it for themselves.

    python3 tools/prune_logos.py
"""
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
UA = "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/120 Safari/537.36"


def loads(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
            return r.status == 200 and "image" in ctype
    except Exception:
        return False


def main():
    paths = list((DATA / "c").glob("*.json")) + [DATA / "featured.json"]

    urls = set()
    for p in paths:
        for s in json.loads(p.read_text(encoding="utf-8")):
            if s.get("f"):
                urls.add(s["f"])
    urls = sorted(urls)
    print(f"checking {len(urls)} distinct logo urls...")

    with ThreadPoolExecutor(max_workers=64) as ex:
        results = list(ex.map(loads, urls))
    good = {u for u, ok in zip(urls, results) if ok}
    print(f"  {len(good)} resolve, {len(urls) - len(good)} dead")

    kept = dropped = 0
    for p in paths:
        items = json.loads(p.read_text(encoding="utf-8"))
        changed = False
        for s in items:
            f = s.get("f")
            if not f:
                continue
            if f in good:
                kept += 1
            else:
                del s["f"]
                dropped += 1
                changed = True
        if changed:
            p.write_text(json.dumps(items, ensure_ascii=False, separators=(",", ":")),
                         encoding="utf-8")

    print(f"\nkept {kept} logo references, removed {dropped} dead ones")


if __name__ == "__main__":
    main()
