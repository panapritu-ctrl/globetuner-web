#!/usr/bin/env python3
"""
Generate the crawlable pages.

The homepage renders its stations with JavaScript, which leaves Google a
single URL with no real content to index -- URL inspection confirmed it as
"crawled, currently not indexed". These pages exist so there is something
to crawl: each one ships its station list as plain HTML in the response,
carries its own title/description/canonical, and links to siblings so a
crawler can walk the whole site without running any script.

Deliberately not generating a page per station for all 20k: a young domain
publishing thousands of near-identical pages is the pattern that got the
blog stuck at zero indexed. Countries and genres are substantial by
nature -- a real list of stations each -- and station pages are capped and
can be widened once the domain has some crawl history.

    python3 tools/build_pages.py
"""
import html
import json
import re
import unicodedata
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BASE = "https://globetuner-web.pages.dev"
PLAY = "https://play.google.com/store/apps/details?id=com.globetuner.radio"

STATION_PAGE_CAP = 300          # widen once the domain has crawl history
MAX_LISTED = 80                 # stations rendered per country/genre page


def esc(s):
    return html.escape(str(s or ""), quote=True)


def slug(s):
    # Transliterate accents rather than dropping them: stripping non-ASCII
    # turned "Turkiye" into "t-rkiye" and "Cote d'Ivoire" into
    # "c-te-d-ivoire", which are poor URLs and poor search terms.
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("\u00df", "ss").replace("\u00f8", "o").replace("\u0111", "d")
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)[:70] or "station"


def flag(cc):
    cc = (cc or "").upper()
    if not re.fullmatch(r"[A-Z]{2}", cc):
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in cc)


def shell(title, desc, canonical, body, extra_ld=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}">
<meta name="theme-color" content="#0b1020">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canonical}">
<link rel="stylesheet" href="/css/style.css">
{extra_ld}
</head>
<body>
<header class="topbar">
  <a class="brand" href="/"><span class="brand-mark" aria-hidden="true">◉</span>
  <span class="brand-name">Globe&nbsp;Tuner</span></a>
  <div class="search-wrap" style="flex:1"></div>
  <a class="topbar-cta" href="{PLAY}" target="_blank" rel="noopener">Get the app</a>
</header>
<main>
{body}
</main>
<footer class="footer">
  <p>Globe Tuner streams publicly available radio broadcasts. Station availability may vary.</p>
  <p class="footer-links">
    <a href="/">Home</a><span>·</span>
    <a href="/countries/">All countries</a><span>·</span>
    <a href="/genres/">All genres</a><span>·</span>
    <a href="{PLAY}" target="_blank" rel="noopener">Android app</a>
  </p>
</footer>
</body>
</html>
"""


def station_list_html(stations, link_pages):
    """Render stations as real anchors when they have their own page, plain
    items otherwise -- a link that goes nowhere is worse than no link."""
    out = ['<div class="grid">']
    for s in stations:
        title = esc(s["t"])
        meta = esc(" · ".join(x for x in (s.get("g"), s.get("l") or s.get("c")) if x))
        fl = flag(s.get("c"))
        page = link_pages.get(s["u"])
        inner = (f'<span class="card-ico" aria-hidden="true">{esc((s["t"] or "?")[:2].upper())}</span>'
                 f'<span class="card-txt"><span class="card-t">{title}</span>'
                 f'<span class="card-s">{fl} {meta}</span></span>')
        if page:
            out.append(f'<a class="card" href="{page}">{inner}</a>')
        else:
            out.append(f'<div class="card">{inner}</div>')
    out.append("</div>")
    return "\n".join(out)


def main():
    countries = json.loads((DATA / "countries.json").read_text(encoding="utf-8"))
    by_cc = {}
    for c in countries:
        p = DATA / "c" / f"{c['c']}.json"
        if p.exists():
            by_cc[c["c"]] = json.loads(p.read_text(encoding="utf-8"))

    # pick the station pages: spread across countries so the set isn't all
    # from whichever country happens to have the most entries
    featured = json.loads((DATA / "featured.json").read_text(encoding="utf-8"))
    chosen, per_cc = [], defaultdict(int)
    for s in featured:
        if len(chosen) >= STATION_PAGE_CAP:
            break
        chosen.append(s)
        per_cc[s.get("c", "")] += 1
    for c in countries:
        if len(chosen) >= STATION_PAGE_CAP:
            break
        for s in by_cc.get(c["c"], []):
            if per_cc[c["c"]] >= 4 or len(chosen) >= STATION_PAGE_CAP:
                break
            if any(x["u"] == s["u"] for x in chosen):
                continue
            chosen.append(s)
            per_cc[c["c"]] += 1

    station_url = {s["u"]: f"/station/{slug(s['t'])}-{slug(s.get('c','xx'))}/" for s in chosen}

    for d in ("country", "genre", "station", "countries", "genres"):
        p = ROOT / d
        if p.exists():
            shutil.rmtree(p)

    urls = [f"{BASE}/"]

    # ---------- country pages ----------
    cdir = ROOT / "country"
    cdir.mkdir()
    for c in countries:
        items = by_cc.get(c["c"], [])
        if not items:
            continue
        name, cc = c["n"] or c["c"], c["c"]
        sl = slug(name)
        title = f"Radio Stations in {name} — Listen Free Online | Globe Tuner"
        desc = (f"Listen to {len(items)} live radio stations from {name} free online. "
                f"Music, news, talk and sports streaming in your browser — no sign-up.")
        canon = f"{BASE}/country/{sl}/"
        body = f"""
  <section class="hero">
    <h1>{flag(cc)} Radio Stations in {esc(name)}</h1>
    <p class="hero-sub">Stream <strong>{len(items)}</strong> live radio stations from
    {esc(name)} free in your browser — music, news, talk and sport. No sign-up, no download.</p>
  </section>
  <section class="panel">
    <div class="panel-head"><h2>Stations you can play now</h2></div>
    {station_list_html(items[:MAX_LISTED], station_url)}
    <p class="empty"><a href="/?q={esc(name)}">Open {esc(name)} in the player →</a></p>
  </section>
  <section class="applink"><div class="applink-inner">
    <h2>Listen on Android</h2>
    <p>Globe Tuner plays thousands more stations, including ones browsers can't —
    plus background playback, sleep timer and car mode.</p>
    <a class="btn-primary" href="{PLAY}" target="_blank" rel="noopener">Get the free app</a>
  </div></section>
  <section class="panel">
    <div class="panel-head"><h2>Other countries</h2></div>
    <div class="chips">
      {"".join(f'<a class="chip" href="/country/{slug(o["n"] or o["c"])}/">{flag(o["c"])} {esc(o["n"] or o["c"])}</a>' for o in countries[:36] if o["c"] != cc)}
    </div>
  </section>
"""
        (cdir / sl).mkdir(parents=True, exist_ok=True)
        (cdir / sl / "index.html").write_text(shell(title, desc, canon, body), encoding="utf-8")
        urls.append(canon)

    # ---------- genre pages ----------
    genres = json.loads((DATA / "genres.json").read_text(encoding="utf-8"))
    gdir = ROOT / "genre"
    gdir.mkdir()
    all_st = [s for items in by_cc.values() for s in items]
    for g in genres:
        name = g["g"]
        needle = name.lower()
        items = [s for s in all_st if needle in (s.get("g") or "").lower()][:MAX_LISTED]
        if len(items) < 5:
            continue
        sl = slug(name)
        title = f"{name} Radio Stations — Listen Free Online | Globe Tuner"
        desc = (f"Stream {name.lower()} radio stations free online from around the world. "
                f"{len(items)} live stations playing in your browser — no sign-up needed.")
        canon = f"{BASE}/genre/{sl}/"
        body = f"""
  <section class="hero">
    <h1>{esc(name)} Radio Stations</h1>
    <p class="hero-sub">Live {esc(name.lower())} radio from around the world, streaming free
    in your browser. No sign-up, no download.</p>
  </section>
  <section class="panel">
    <div class="panel-head"><h2>Stations you can play now</h2></div>
    {station_list_html(items, station_url)}
    <p class="empty"><a href="/?q={esc(name)}">Open {esc(name)} in the player →</a></p>
  </section>
  <section class="panel">
    <div class="panel-head"><h2>Other genres</h2></div>
    <div class="chips">
      {"".join(f'<a class="chip" href="/genre/{slug(o["g"])}/">{esc(o["g"])}</a>' for o in genres[:30] if o["g"] != name)}
    </div>
  </section>
"""
        (gdir / sl).mkdir(parents=True, exist_ok=True)
        (gdir / sl / "index.html").write_text(shell(title, desc, canon, body), encoding="utf-8")
        urls.append(canon)

    # ---------- station pages ----------
    sdir = ROOT / "station"
    sdir.mkdir()
    cc_name = {c["c"]: (c["n"] or c["c"]) for c in countries}
    for s in chosen:
        rel = station_url[s["u"]]
        name, cc = s["t"], s.get("c", "")
        country = cc_name.get(cc, cc)
        genre = s.get("g") or "Radio"
        title = f"{name} — Listen Live Online Free | Globe Tuner"
        desc = (f"Listen to {name} live online for free. {genre} radio"
                + (f" from {country}" if country else "")
                + ". Streams in your browser, no sign-up required.")
        canon = BASE + rel
        siblings = [x for x in by_cc.get(cc, []) if x["u"] != s["u"]][:12]
        ld = f"""<script type="application/ld+json">
{json.dumps({
  "@context":"https://schema.org","@type":"RadioStation","name":name,
  "url":canon,"genre":genre,
  **({"areaServed":country} if country else {}),
}, ensure_ascii=False)}
</script>"""
        body = f"""
  <section class="hero">
    <h1>{esc(name)}</h1>
    <p class="hero-sub">{flag(cc)} {esc(genre)}{(" · " + esc(country)) if country else ""}
    — listen live, free, in your browser.</p>
    <p><a class="btn-primary" href="/?q={esc(name)}">▶ Play {esc(name)}</a></p>
  </section>
  <section class="panel">
    <div class="panel-head"><h2>About this station</h2></div>
    <p class="empty">{esc(name)} is a {esc(genre.lower())} radio station
    {("broadcasting from " + esc(country)) if country else "streaming online"}. You can listen
    live for free in your browser — no account, no download. For background playback,
    a sleep timer and thousands more stations, use the Android app.</p>
  </section>
  <section class="applink"><div class="applink-inner">
    <h2>Listen on Android</h2>
    <p>Keep {esc(name)} playing in the background, set a sleep timer, or save it to favourites.</p>
    <a class="btn-primary" href="{PLAY}" target="_blank" rel="noopener">Get the free app</a>
  </div></section>
  {"" if not siblings else f'''
  <section class="panel">
    <div class="panel-head"><h2>More stations from {esc(country)}</h2></div>
    {station_list_html(siblings, station_url)}
    <p class="empty"><a href="/country/{slug(country)}/">All {esc(country)} stations →</a></p>
  </section>'''}
"""
        (sdir / rel.strip("/").split("/", 1)[1]).mkdir(parents=True, exist_ok=True)
        (ROOT / rel.strip("/") / "index.html").write_text(
            shell(title, desc, canon, body, ld), encoding="utf-8")
        urls.append(canon)

    # ---------- index pages ----------
    for folder, heading, links in (
        ("countries", "Radio by country",
         [(f"/country/{slug(c['n'] or c['c'])}/", f"{flag(c['c'])} {c['n'] or c['c']}", c["k"])
          for c in countries if by_cc.get(c["c"])]),
        ("genres", "Radio by genre",
         [(f"/genre/{slug(g['g'])}/", g["g"], g["k"]) for g in genres]),
    ):
        d = ROOT / folder
        d.mkdir(exist_ok=True)
        canon = f"{BASE}/{folder}/"
        chips = "".join(
            f'<a class="chip" href="{u}">{esc(label)}<span class="n">{n}</span></a>'
            for u, label, n in links)
        body = f"""
  <section class="hero"><h1>{heading}</h1>
  <p class="hero-sub">Browse {len(links)} collections of free live radio.</p></section>
  <section class="panel"><div class="chips">{chips}</div></section>
"""
        d.joinpath("index.html").write_text(
            shell(f"{heading} — Globe Tuner", f"Browse free live radio by {folder[:-1]}.",
                  canon, body), encoding="utf-8")
        urls.append(canon)

    # ---------- sitemap ----------
    entries = "\n".join(
        f"  <url><loc>{u}</loc><changefreq>weekly</changefreq>"
        f"<priority>{'1.0' if u == BASE + '/' else '0.7'}</priority></url>" for u in urls)
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n</urlset>\n", encoding="utf-8")

    print(f"countries: {sum(1 for c in countries if by_cc.get(c['c']))}")
    print(f"genres:    {len(list((ROOT/'genre').iterdir()))}")
    print(f"stations:  {len(chosen)}")
    print(f"sitemap:   {len(urls)} urls")


if __name__ == "__main__":
    main()
