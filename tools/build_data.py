#!/usr/bin/env python3
"""
Turn the app's station catalog into something a browser can actually load.

The app pulls ~35k stations across 19 region files (several MB) at launch.
A web page can't do that, and it doesn't need to: two thirds of the work is
thrown away before anything is shown.

Two filters run here:

  * HTTP streams are dropped entirely. A page served over HTTPS cannot play
    an http:// stream -- browsers block it as mixed content, with no
    workaround short of proxying every stream. Those stations are counted
    and surfaced on the site as app-only, which is true and doubles as the
    honest reason to install.

  * Hosts that sign stream URLs with a short-lived token (zeno.fm and
    friends) are dropped, for the same reason the catalog tooling drops
    them: the URL is dead about a minute after it's issued.

Output is split per country so the homepage ships a few KB instead of
megabytes, with countries loaded on demand.

    python3 tools/build_data.py
"""
import json
import re
import shutil
import urllib.request
from collections import defaultdict
from pathlib import Path

CDN = "https://cdn.jsdelivr.net/gh/panapritu-ctrl/globe-tuner-content@main/"
OUT = Path(__file__).resolve().parent.parent / "data"

# Same expiring-signature families the catalog tooling refuses: the URL
# verifies fine and is dead by the time anyone presses play.
TOKEN_RE = re.compile(r"[?&](zt|zs|rj-tok|token|Policy|Signature|Key-Pair-Id)=", re.I)
BANNED_HOSTS = ("zeno.fm", "surfernetwork.com")

COUNTRY_NAMES = {}


def fetch(path):
    req = urllib.request.Request(CDN + path, headers={"User-Agent": "GlobeTunerWeb/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def web_playable(url):
    if not url.startswith("https://"):
        return False          # http:// is blocked as mixed content
    low = url.lower()
    if any(h in low for h in BANNED_HOSTS):
        return False
    if TOKEN_RE.search(url):
        return False
    return True


def main():
    print("fetching catalog...")
    index = fetch("radio_index.json")
    raw = []
    for f in index["files"]:
        raw += fetch(f)["stations"]
    print(f"  {len(raw)} stations in catalog")

    try:
        picks = fetch("zeno/zeno_stations.json")["stations"]
        print(f"  {len(picks)} editor's picks")
    except Exception:
        picks = []

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    by_country = defaultdict(list)
    seen = set()
    app_only = 0

    for s in raw:
        url = (s.get("streamUrl") or "").strip()
        title = (s.get("title") or "").strip()
        if not url or not title:
            continue
        if not web_playable(url):
            app_only += 1
            continue
        if url in seen:
            continue
        seen.add(url)
        cc = (s.get("countryCode") or "").upper() or "ZZ"
        by_country[cc].append({
            "i": s.get("id"),
            "t": title,
            "u": url,
            "g": (s.get("genre") or "Radio").strip()[:28],
            "l": (s.get("location") or "").strip()[:48],
            "c": cc,
        })

    total = sum(len(v) for v in by_country.values())
    print(f"  web-playable: {total}   app-only (http/token): {app_only}")

    # Per-country files, biggest first so the UI can rank sensibly.
    countries = []
    cdir = OUT / "c"
    cdir.mkdir()
    for cc, items in by_country.items():
        items.sort(key=lambda x: x["t"].lower())
        (cdir / f"{cc}.json").write_text(
            json.dumps(items, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        name = next((i["l"].split(",")[-1].strip() for i in items if i["l"]), cc)
        countries.append({"c": cc, "n": name or cc, "k": len(items)})
    countries.sort(key=lambda x: -x["k"])

    # A small homepage payload: editor's picks that are web-playable, else
    # a spread of the largest countries' first entries.
    featured = []
    fseen = set()
    for s in picks:
        url = (s.get("streamUrl") or "").strip()
        if web_playable(url) and url not in fseen:
            fseen.add(url)
            featured.append({
                "i": s.get("id"), "t": (s.get("title") or "").strip(), "u": url,
                "g": (s.get("genre") or "Radio").strip()[:28],
                "l": (s.get("location") or "").strip()[:48],
                "c": (s.get("countryCode") or "").upper(),
            })
        if len(featured) >= 60:
            break
    if len(featured) < 60:
        for entry in countries:
            for s in by_country[entry["c"]][:1]:
                if s["u"] not in fseen:
                    fseen.add(s["u"])
                    featured.append(s)
            if len(featured) >= 60:
                break

    (OUT / "countries.json").write_text(
        json.dumps(countries, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT / "featured.json").write_text(
        json.dumps(featured, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    genres = defaultdict(int)
    for items in by_country.values():
        for s in items:
            g = s["g"].title()
            if g and g.lower() not in ("radio", "music", "unknown", ""):
                genres[g] += 1
    top_genres = sorted(genres.items(), key=lambda x: -x[1])[:40]
    (OUT / "genres.json").write_text(
        json.dumps([{"g": g, "k": k} for g, k in top_genres],
                   ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    (OUT / "stats.json").write_text(json.dumps({
        "web": total, "appOnly": app_only, "countries": len(countries),
        "total": total + app_only,
    }), encoding="utf-8")

    kb = sum(p.stat().st_size for p in OUT.rglob("*.json")) // 1024
    print(f"\nwrote {len(countries)} country files, {len(featured)} featured, "
          f"{len(top_genres)} genres  ({kb} KB total)")
    print(f"homepage payload: "
          f"{(OUT/'featured.json').stat().st_size//1024}KB featured + "
          f"{(OUT/'countries.json').stat().st_size//1024}KB countries")


if __name__ == "__main__":
    main()
