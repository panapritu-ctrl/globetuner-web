#!/usr/bin/env python3
"""
Link blog posts from the website's generated pages.

Google crawled this domain within minutes of verification; the blog goes
weeks between visits and sits near zero indexed. Links from pages a crawler
actually visits are the one lever left that doesn't depend on waiting --
the posts are genuinely related to the pages linking them, so this is
ordinary internal linking rather than anything manufactured.

Topic matches are explicit rather than guessed: a country page gets the
post about that country, genre pages get the post about that genre, and
everything else falls back to a small set of general guides. A wrong match
would be worse than none.

Run after tools/build_pages.py.

    python3 tools/link_blog.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOG = "https://globetuner.blogspot.com/2026"

# country slug -> (post url, anchor text)
BY_COUNTRY = {
    "india": (f"{BLOG}/07/how-to-listen-to-indian-fm-radio-online.html",
              "How to listen to Indian FM radio online for free"),
    "germany": (f"{BLOG}/08/wie-man-kostenlos-live-radio-online.html",
                "Kostenlos Live-Radio online hören (Anleitung 2026)"),
    "france": (f"{BLOG}/08/comment-ecouter-la-radio-en-direct.html",
               "Comment écouter la radio en direct gratuitement"),
    "brazil": (f"{BLOG}/08/como-ouvir-radio-ao-vivo-online-gratis.html",
               "Como ouvir rádio ao vivo online grátis"),
    "mexico": (f"{BLOG}/08/como-escuchar-radio-en-vivo-gratis.html",
               "Cómo escuchar radio en vivo gratis online"),
    "spain": (f"{BLOG}/08/como-escuchar-radio-en-vivo-gratis.html",
              "Cómo escuchar radio en vivo gratis online"),
    "indonesia": (f"{BLOG}/08/cara-mendengarkan-radio-online-gratis.html",
                  "Cara mendengarkan radio online gratis"),
    # slugs come from the catalog's own country names, which are
    # "Türkiye" and "The Russian Federation" rather than Turkey/Russia
    "turkiye": (f"{BLOG}/09/ucretsiz-canl-radyo-nasl-dinlenir-2026.html",
                "Ücretsiz canlı radyo nasıl dinlenir"),
    "the-russian-federation": (f"{BLOG}/09/2026.html",
                               "Как слушать прямой радиоэфир бесплатно онлайн"),
}

BY_GENRE = {
    "news": (f"{BLOG}/07/how-radio-apps-help-you-stay-updated.html",
             "How radio apps keep you updated with news and sports"),
    "sports": (f"{BLOG}/07/how-radio-apps-help-you-stay-updated.html",
               "How radio apps keep you updated with news and sports"),
    "public": (f"{BLOG}/07/npr-public-radio-apps-best-ways-to.html",
               "The best ways to stream public radio"),
}

GENERAL = [
    (f"{BLOG}/08/how-to-listen-to-free-live-radio-on-any.html",
     "How to listen to free live radio on any device"),
    (f"{BLOG}/07/the-history-of-radio-from-wireless.html",
     "The history of radio: from wireless waves to your pocket"),
    (f"{BLOG}/08/best-radio-app-for-android-in-2026-10.html",
     "Best radio app for Android in 2026: 10 apps compared"),
    (f"{BLOG}/08/how-to-save-battery-and-mobile-data.html",
     "How to save battery and mobile data while streaming radio"),
]

BLOCK = """
  <section class="panel">
    <div class="panel-head"><h2>Read more</h2></div>
    <ul>
{items}
    </ul>
  </section>
"""


def block_for(kind, slug, i):
    picks = []
    if kind == "country" and slug in BY_COUNTRY:
        picks.append(BY_COUNTRY[slug])
    if kind == "genre":
        for key, val in BY_GENRE.items():
            if key in slug:
                picks.append(val)
                break
    # top up with general guides, rotated so the same two posts aren't
    # linked from all 550 pages
    for j in range(2):
        picks.append(GENERAL[(i + j) % len(GENERAL)])

    seen, out = set(), []
    for url, text in picks:
        if url in seen:
            continue
        seen.add(url)
        out.append(f'      <li><a href="{url}" target="_blank" rel="noopener">{text}</a></li>')
    return BLOCK.format(items="\n".join(out[:3]))


def main():
    added = 0
    for kind in ("country", "genre"):
        d = ROOT / kind
        if not d.exists():
            continue
        for i, page in enumerate(sorted(d.glob("*/index.html"))):
            html = page.read_text(encoding="utf-8")
            if "Read more</h2>" in html:
                continue
            slug = page.parent.name
            marker = '<section class="applink">'
            blk = block_for(kind, slug, i)
            if marker in html:
                html = html.replace(marker, blk + "  " + marker, 1)
            else:
                html = html.replace("</main>", blk + "</main>", 1)
            page.write_text(html, encoding="utf-8")
            added += 1
    print(f"added blog links to {added} pages")


if __name__ == "__main__":
    main()
