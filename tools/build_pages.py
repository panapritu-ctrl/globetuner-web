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
import hashlib
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


# Cyrillic and Greek romanisation. Without these the whole name is dropped:
# the genre "\u041f\u043e\u043f-\u041c\u0443\u0437\u044b\u043a\u0430" (60 stations) came out as the literal
# fallback "station", and every Russian station name collapsed the same way.
_CYR = {
    "\u0430": "a", "\u0431": "b", "\u0432": "v", "\u0433": "g", "\u0434": "d", "\u0435": "e", "\u0451": "e",
    "\u0436": "zh", "\u0437": "z", "\u0438": "i", "\u0439": "y", "\u043a": "k", "\u043b": "l", "\u043c": "m",
    "\u043d": "n", "\u043e": "o", "\u043f": "p", "\u0440": "r", "\u0441": "s", "\u0442": "t", "\u0443": "u",
    "\u0444": "f", "\u0445": "kh", "\u0446": "ts", "\u0447": "ch", "\u0448": "sh", "\u0449": "shch",
    "\u044a": "", "\u044b": "y", "\u044c": "", "\u044d": "e", "\u044e": "yu", "\u044f": "ya",
    "\u0454": "ye", "\u0456": "i", "\u0457": "yi", "\u0491": "g", "\u045e": "u", "\u0452": "dj",
    "\u0458": "j", "\u0459": "lj", "\u045a": "nj", "\u045b": "c", "\u045f": "dz",
}
_GRK = {
    "\u03b1": "a", "\u03b2": "v", "\u03b3": "g", "\u03b4": "d", "\u03b5": "e", "\u03b6": "z", "\u03b7": "i",
    "\u03b8": "th", "\u03b9": "i", "\u03ba": "k", "\u03bb": "l", "\u03bc": "m", "\u03bd": "n", "\u03be": "x",
    "\u03bf": "o", "\u03c0": "p", "\u03c1": "r", "\u03c3": "s", "\u03c2": "s", "\u03c4": "t", "\u03c5": "y",
    "\u03c6": "f", "\u03c7": "ch", "\u03c8": "ps", "\u03c9": "o",
}
_LATIN = {"\u00df": "ss", "\u00f8": "o", "\u0111": "d", "\u00e6": "ae", "\u0153": "oe",
          "\u0142": "l", "\u00fe": "th", "\u00f0": "d", "\u20ac": "eur", "&": " and "}


def slug(s):
    # Transliterate rather than drop: stripping non-ASCII turned "Turkiye"
    # into "t-rkiye" and "Cote d'Ivoire" into "c-te-d-ivoire", which are poor
    # URLs and poor search terms.
    out = []
    for ch in (s or ""):
        lo = ch.lower()
        out.append(_CYR.get(lo) or _GRK.get(lo) or _LATIN.get(lo) or ch)
    s = unicodedata.normalize("NFKD", "".join(out))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    if len(s) > 70:
        # Cut on a word boundary. A hard slice left "...silves" and
        # "...top-4", which read as typos in a search result.
        s = s[:70].rsplit("-", 1)[0] if "-" in s[:70] else s[:70]
    return s.strip("-")


def degenerate(sl):
    """True when a slug carries no usable words.

    CJK, Arabic, Hebrew and Thai have no single-character romanisation, so
    those names reduce to whatever ASCII they happened to contain -- often
    nothing, or bare digits. "80\u540e\u97f3\u60a6\u53f0" and "80\u540e\u97f3\u60a6\u53f0\u00b7\u6cb3\u5357\u7f51\u7edc\u7535\u53f0" both
    became "80", so two different stations claimed one URL and one page
    silently overwrote the other.
    """
    return not sl or len(sl) < 3 or sl.replace("-", "").isdigit()


def uniq(path, taken):
    """Keep every generated path distinct, deterministically."""
    if path not in taken:
        taken.add(path)
        return path
    n = 2
    while f"{path}-{n}" in taken:
        n += 1
    taken.add(f"{path}-{n}")
    return f"{path}-{n}"


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
<meta name="theme-color" content="#121317">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canonical}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&family=Sora:wght@500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/css/style.css">
{extra_ld}
</head>
<body>
<header class="topbar">
  <a class="brand" href="/"><span class="brand-mark" aria-hidden="true">◉</span>
  <span class="brand-name">GlobeTuner</span></a>
  <span class="live-pill"><span class="dot" aria-hidden="true"></span> Live radio only</span>
  <nav class="nav" aria-label="Sections">
    <a class="nav-item" href="/">Tuner</a>
    <a class="nav-item" href="/countries/">Countries</a>
    <a class="nav-item" href="/genres/">Genres</a>
  </nav>
  <div class="search-wrap" style="flex:1"></div>
  <a class="topbar-cta" href="{PLAY}" target="_blank" rel="noopener">Get the app</a>
</header>
<main class="wrap">
{body}
</main>
<div class="wrap">
<footer class="footer">
  <p>Globe Tuner streams publicly available radio broadcasts. Station availability may vary.</p>
  <p class="footer-links">
    <a href="/">Home</a><span>·</span>
    <a href="/countries/">All countries</a><span>·</span>
    <a href="/genres/">All genres</a><span>·</span>
    <a href="{PLAY}" target="_blank" rel="noopener">Android app</a>
  </p>
</footer>
</div>
</body>
</html>
"""


def station_list_html(stations, link_pages):
    """Render stations as real anchors when they have their own page, plain
    items otherwise -- a link that goes nowhere is worse than no link."""
    out = ['<div class="slist">']
    for s in stations:
        title = esc(s["t"])
        meta = esc(" · ".join(x for x in (s.get("g"), s.get("l") or s.get("c")) if x))
        fl = flag(s.get("c"))
        page = link_pages.get(s["u"])
        inner = (f'<span class="srow-ico" aria-hidden="true">{esc((s["t"] or "?")[:2].upper())}</span>'
                 f'<span class="srow-txt"><span class="srow-t">{title}</span>'
                 f'<span class="srow-s">{fl} {meta}</span></span>')
        if page:
            out.append(f'<a class="srow" href="{page}">{inner}<span class="srow-go">▶</span></a>')
        else:
            out.append(f'<div class="srow">{inner}</div>')
    out.append("</div>")
    return "\n".join(out)


def main():
    countries = json.loads((DATA / "countries.json").read_text(encoding="utf-8"))
    # "Unknown" is Radio Browser's placeholder for a missing country, and it
    # arrives under two codes (ZZ and XX). Both slugged to /country/unknown/,
    # so they overwrote each other -- and a page titled "Radio Stations in
    # Unknown" is not worth crawling either way.
    countries = [c for c in countries if (c["n"] or "").strip().lower() != "unknown"]
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

    # One URL per station, guaranteed. Names in scripts we cannot romanise
    # fall back to genre + country, and a digest of the stream URL breaks any
    # remaining tie, so no page can overwrite another.
    taken_st = set()
    station_url = {}
    for s in chosen:
        base = slug(s["t"])
        if degenerate(base):
            parts = [base, slug(s.get("g") or "") or "radio",
                     hashlib.sha1(s["u"].encode("utf-8")).hexdigest()[:6]]
            base = "-".join(x for x in parts if x)
        cc = slug(s.get("c") or "") or "xx"
        station_url[s["u"]] = f"/station/{uniq(f'{base}-{cc}', taken_st)}/"

    # Country and genre paths are resolved once and then looked up, so the
    # links on every page match the directories that actually get written.
    taken_c, country_url = set(), {}
    for c in countries:
        base = slug(c["n"] or c["c"]) or slug(c["c"]) or "radio"
        country_url[c["c"]] = f"/country/{uniq(base, taken_c)}/"

    genres = json.loads((DATA / "genres.json").read_text(encoding="utf-8"))
    taken_g, genre_url = set(), {}
    for g in genres:
        base = slug(g["g"])
        if degenerate(base):
            base = f"{base + '-' if base else ''}radio-{slug(g['g']) or hashlib.sha1(g['g'].encode('utf-8')).hexdigest()[:6]}"
        genre_url[g["g"]] = f"/genre/{uniq(base, taken_g)}/"

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
        sl = country_url[cc].strip("/").split("/", 1)[1]
        title = f"Radio Stations in {name} — Listen Free Online | Globe Tuner"
        desc = (f"Listen to {len(items)} live radio stations from {name} free online. "
                f"Music, news, talk and sports streaming in your browser — no sign-up.")
        canon = BASE + country_url[cc]
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
      {"".join(f'<a class="chip" href="{country_url[o["c"]]}">{flag(o["c"])} {esc(o["n"] or o["c"])}</a>' for o in countries[:36] if o["c"] != cc)}
    </div>
  </section>
"""
        (cdir / sl).mkdir(parents=True, exist_ok=True)
        (cdir / sl / "index.html").write_text(shell(title, desc, canon, body), encoding="utf-8")
        urls.append(canon)

    # ---------- genre pages ----------
    gdir = ROOT / "genre"
    gdir.mkdir()
    all_st = [s for items in by_cc.values() for s in items]
    for g in genres:
        name = g["g"]
        needle = name.lower()
        items = [s for s in all_st if needle in (s.get("g") or "").lower()][:MAX_LISTED]
        if len(items) < 5:
            continue
        sl = genre_url[name].strip("/").split("/", 1)[1]
        title = f"{name} Radio Stations — Listen Free Online | Globe Tuner"
        desc = (f"Stream {name.lower()} radio stations free online from around the world. "
                f"{len(items)} live stations playing in your browser — no sign-up needed.")
        canon = BASE + genre_url[name]
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
      {"".join(f'<a class="chip" href="{genre_url[o["g"]]}">{esc(o["g"])}</a>' for o in genres[:30] if o["g"] != name)}
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
    <p class="empty"><a href="{country_url.get(cc, "/countries/")}">All {esc(country)} stations →</a></p>
  </section>'''}
"""
        (sdir / rel.strip("/").split("/", 1)[1]).mkdir(parents=True, exist_ok=True)
        (ROOT / rel.strip("/") / "index.html").write_text(
            shell(title, desc, canon, body, ld), encoding="utf-8")
        urls.append(canon)

    # ---------- 404 ----------
    # Without a 404.html, Pages answers every unknown path with index.html
    # at status 200. Google read that as a real page, so any typo or stale
    # link became another duplicate of the homepage. A file here makes Pages
    # return an actual 404. Deliberately absent from the sitemap.
    (ROOT / "404.html").write_text(shell(
        "Page not found — Globe Tuner",
        "That page doesn't exist. Browse live radio by country or genre instead.",
        f"{BASE}/404",
        """
  <section class="hero">
    <h1>That page doesn't exist</h1>
    <p class="hero-sub">The link may be out of date. Everything we have is reachable
    from the lists below, or start playing straight away from the home page.</p>
    <p><a class="btn-primary" href="/">\u25b6 Open the player</a></p>
  </section>
  <section class="panel">
    <div class="panel-head"><h2>Go somewhere real</h2></div>
    <div class="chips">
      <a class="chip" href="/countries/">Radio by country</a>
      <a class="chip" href="/genres/">Radio by genre</a>
      <a class="chip" href="/">All stations</a>
    </div>
  </section>
"""), encoding="utf-8")

    # ---------- index pages ----------
    for folder, heading, links in (
        ("countries", "Radio by country",
         [(country_url[c["c"]], f"{flag(c['c'])} {c['n'] or c['c']}", c["k"])
          for c in countries if by_cc.get(c["c"])]),
        ("genres", "Radio by genre",
         [(genre_url[g["g"]], g["g"], g["k"]) for g in genres]),
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
