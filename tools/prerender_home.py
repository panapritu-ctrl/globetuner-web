#!/usr/bin/env python3
"""
Bake the homepage's content into index.html.

The homepage fills its station grid, country pills, gateways and genre chips
from data/*.json after load. URL inspection reported the page as "crawled,
currently not indexed", and the reason is visible in the raw response: a
crawler that does not run scripts sees about 1,300 characters, most of it
chrome, with the words "Loading catalogue..." where the stations should be.
Google does render JavaScript, but it does so on a second pass that a new
domain with no history waits a long time for -- and the first pass is what
decides whether the page looks worth coming back to.

This writes real HTML into those four containers at build time. The page's
JavaScript still replaces them on load, so behaviour is unchanged for
people; the difference is only in what arrives before any script runs.

Idempotent: HTML comment markers fence each injected block, so re-running
replaces rather than stacks. Run after tools/build_pages.py.

    python3 tools/prerender_home.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pages import slug, degenerate, uniq, esc, flag   # same slugs as the pages


def short(n):
    return re.sub(r"\s+Federation$", "",
           re.sub(r"\s+Of\s+America$", "", re.sub(r"^The\s+", "", str(n))))


def _container_span(html, container_id):
    """Byte span of a container's inner HTML, found by matching tag depth.

    Counting depth rather than searching for the next closing tag matters
    because #cards ships skeleton divs and the injected blocks nest several
    levels; a non-greedy match stops at the first </a> it meets.
    """
    m = re.search(rf'<([a-z]+)[^>]*\bid="{container_id}"[^>]*>', html)
    if not m:
        raise SystemExit(f"container #{container_id} not found in index.html")
    tag, i, depth = m.group(1), m.end(), 1
    for t in re.finditer(rf'<(/?){tag}\b[^>]*>', html[i:]):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return i, i + t.start()
    raise SystemExit(f"container #{container_id} is never closed")


def inject(html, container_id, inner):
    """Replace a container's contents, idempotently.

    The block is fenced by comment markers. Without them a rerun cannot tell
    generated content from the container's original contents, and appends
    instead of replacing -- which silently doubled the homepage on every
    rebuild until it was caught.
    """
    begin, end = f"<!--pr:{container_id}-->", f"<!--/pr:{container_id}-->"
    block = f"{begin}\n{inner}\n    {end}"
    if begin in html:
        return re.sub(re.escape(begin) + r".*?" + re.escape(end), lambda _: block,
                      html, count=1, flags=re.S)
    a, b = _container_span(html, container_id)
    return html[:a] + "\n" + block + "\n    " + html[b:]


def main():
    countries = json.loads((DATA / "countries.json").read_text(encoding="utf-8"))
    countries = [c for c in countries if (c["n"] or "").strip().lower() != "unknown"]
    genres    = json.loads((DATA / "genres.json").read_text(encoding="utf-8"))
    featured  = json.loads((DATA / "featured.json").read_text(encoding="utf-8"))
    stats     = json.loads((DATA / "stats.json").read_text(encoding="utf-8"))

    # Same path resolution build_pages.py uses, so every link here points at a
    # page that exists rather than at a 404.
    taken_c, curl = set(), {}
    for c in countries:
        curl[c["c"]] = f"/country/{uniq(slug(c['n'] or c['c']) or slug(c['c']) or 'radio', taken_c)}/"
    taken_g, gurl = set(), {}
    for g in genres:
        base = slug(g["g"])
        if degenerate(base):
            base = f"{base + '-' if base else ''}radio"
        gurl[g["g"]] = f"/genre/{uniq(base, taken_g)}/"

    html = (ROOT / "index.html").read_text(encoding="utf-8")

    # ── country pills ──────────────────────────────────────────────────────
    pills = ['      <a class="pill is-on" href="/countries/">'
             '<span class="pdot" style="background:#ff535b"></span>Popular</a>']
    for c in countries[:9]:
        pills.append(
            f'      <a class="pill" href="{curl[c["c"]]}">'
            f'<span class="pdot" style="background:#5b9dff"></span>'
            f'{esc(short(c["n"]))}<span class="pk">{c["k"]:,}</span></a>')
    html = inject(html, "country-pills", "\n".join(pills))

    # ── station cards ──────────────────────────────────────────────────────
    cards = []
    for s in featured[:24]:
        cards.append(
            '      <article class="card">\n'
            '        <div class="card-top">\n'
            f'          <span class="card-logo">{esc((s["t"] or "?")[:2].upper())}</span>\n'
            '          <span class="card-id">\n'
            f'            <span class="card-name"><span class="nm">{esc(s["t"])}</span>'
            '<span class="tag-live">Live</span></span>\n'
            f'            <span class="card-loc">{esc(s.get("l") or "")}</span>\n'
            '          </span>\n'
            '        </div>\n'
            '        <div class="card-mid"><div class="card-genre">'
            f'<span class="g">{esc(s.get("g") or "Radio")}</span>'
            f'<span class="card-cc">{esc(s.get("c") or "")}</span></div></div>\n'
            '      </article>')
    html = inject(html, "cards", "\n".join(cards))

    # ── country gateways ───────────────────────────────────────────────────
    gw = []
    for c in countries[:8]:
        gw.append(
            f'      <a class="gw" href="{curl[c["c"]]}">\n'
            f'        <span class="gw-ico">{flag(c["c"]) or "◉"}</span>\n'
            f'        <span class="gw-k">{c["k"]:,} stations</span>\n'
            f'        <span class="gw-n">{esc(short(c["n"]))}</span>\n'
            f'        <span class="gw-s">Live radio from {esc(short(c["n"]))}, '
            'streaming free in your browser.</span>\n'
            '        <span class="gw-f"><span>Browse</span><span>&rarr;</span></span>\n'
            '      </a>')
    html = inject(html, "gateways", "\n".join(gw))

    # ── genre chips ────────────────────────────────────────────────────────
    chips = [f'      <a class="chip" href="{gurl[g["g"]]}">{esc(g["g"])} '
             f'<b>{g["k"]:,}</b></a>' for g in genres[:18]]
    html = inject(html, "genres", "\n".join(chips))

    # ── headline numbers, so they are not "—" before scripts run ───────────
    for cid, val in (("hero-count", f'{stats["web"]:,}'),
                     ("stat-web", f'{stats["web"]:,}'),
                     ("stat-countries", f'{stats["countries"]:,}'),
                     ("strip-web", f'{stats["web"]:,}'),
                     ("strip-countries", f'{stats["countries"]:,}'),
                     ("strip-app", f'{stats["appOnly"]:,}'),
                     ("stat-apponly", f'{stats["appOnly"]:,}')):
        html = re.sub(rf'(<[a-z]+[^>]*\bid="{cid}"[^>]*>).*?(</[a-z]+>)',
                      rf'\g<1>{val}\g<2>', html, count=1, flags=re.S)
    html = html.replace('>Loading catalogue…<',
                        f'>Worldwide • {stats["web"]:,} stations • {stats["countries"]} countries<')

    (ROOT / "index.html").write_text(html, encoding="utf-8")

    text = re.sub(r"<[^>]+>", " ", html.split("<body>")[1])
    print(f"prerendered homepage: {len(re.sub(r'\\s+', ' ', text))} chars of text, "
          f"{html.count('href=\"/country/')} country links, "
          f"{html.count('href=\"/genre/')} genre links")


if __name__ == "__main__":
    main()
