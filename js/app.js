/* Globe Tuner web player.
 *
 * Data is pre-split per country by tools/build_data.py, so the homepage
 * pulls ~21KB and a country loads only when someone asks for it. Stations
 * whose streams are plain HTTP never reach this file at all -- the browser
 * would refuse to play them on an HTTPS page, so they're filtered at build
 * time and surfaced on the page as app-only instead.
 */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const audio = $("audio");

  const state = {
    countries: [],
    featured: [],
    loaded: new Map(),  // countryCode -> stations[]
    queue: [],          // the list the current station was played from
    index: -1,
    current: null,
  };

  /* ---------------- data ---------------- */

  const getJSON = (path) =>
    fetch(path, { cache: "force-cache" }).then((r) => {
      if (!r.ok) throw new Error(`${path}: ${r.status}`);
      return r.json();
    });

  async function loadCountry(cc) {
    if (state.loaded.has(cc)) return state.loaded.get(cc);
    const items = await getJSON(`/data/c/${cc}.json`);
    state.loaded.set(cc, items);
    return items;
  }

  /* ---------------- helpers ---------------- */

  const initials = (name) =>
    (name || "?")
      .replace(/[^\p{L}\p{N} ]/gu, "")
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((w) => w[0])
      .join("")
      .toUpperCase() || "?";

  // ISO country code -> flag emoji via regional indicator symbols. Ships no
  // assets and makes long country lists scannable.
  const flag = (cc) =>
    /^[A-Z]{2}$/.test(cc || "")
      ? String.fromCodePoint(...[...cc].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65))
      : "";

  /** Artwork that shows a logo when one loads and falls back to initials
   *  when it doesn't -- roughly a third of upstream favicons are stale, and
   *  a broken image looks worse than a clean monogram. */
  function artwork(s, cls, phCls) {
    const box = document.createElement("span");
    box.className = cls;
    const ph = document.createElement("span");
    if (phCls) ph.className = phCls;
    ph.textContent = initials(s.t);
    box.append(ph);
    if (s.f) {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.decoding = "async";
      img.alt = "";
      img.src = s.f;
      img.addEventListener("load", () => ph.replaceWith(img));
      img.addEventListener("error", () => img.remove());
    }
    return box;
  }

  /* ---------------- tiles ---------------- */

  function tile(s, list, i) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "tile";
    el.dataset.url = s.u;

    const art = artwork(s, "tile-art", "tile-ph");
    const playBtn = document.createElement("span");
    playBtn.className = "tile-play";
    playBtn.setAttribute("aria-hidden", "true");
    playBtn.textContent = "▶";
    art.append(playBtn);

    const t = document.createElement("span");
    t.className = "tile-t";
    t.textContent = s.t;

    const sub = document.createElement("span");
    sub.className = "tile-s";
    const fl = flag(s.c);
    if (fl) {
      const f = document.createElement("span");
      f.className = "flag";
      f.textContent = fl;
      sub.append(f);
    }
    const meta = document.createElement("span");
    meta.textContent = s.g || s.l || s.c || "Radio";
    sub.append(meta);

    el.append(art, t, sub);
    el.addEventListener("click", () => play(s, list, i));
    return el;
  }

  function renderTiles(node, stations, limit = 120) {
    node.replaceChildren();
    const shown = stations.slice(0, limit);
    const frag = document.createDocumentFragment();
    shown.forEach((s, i) => frag.append(tile(s, shown, i)));
    node.append(frag);
    markActive();
  }

  function markActive() {
    const url = state.current?.u;
    document.querySelectorAll(".tile").forEach((c) =>
      c.classList.toggle("active", !!url && c.dataset.url === url)
    );
  }

  /* ---------------- playback ---------------- */

  const setState = (msg) => ($("np-state").textContent = msg);

  function play(station, list, i) {
    // Tapping whatever is already playing pauses instead of restarting.
    if (state.current && state.current.u === station.u && !audio.paused) {
      audio.pause();
      return;
    }
    if (Array.isArray(list)) {
      state.queue = list;
      state.index = typeof i === "number" ? i : list.findIndex((x) => x.u === station.u);
    }
    state.current = station;

    $("player").hidden = false;
    const art = artwork(station, "now-art");
    art.id = "np-art";
    $("np-art").replaceWith(art);

    $("np-title").textContent = station.t;
    $("np-sub").textContent = [flag(station.c), station.g, station.l || station.c]
      .filter(Boolean)
      .join(" · ");
    setState("Connecting…");

    audio.src = station.u;
    audio.play().catch(() => setState("Can't play"));

    markActive();
    remember(station);
  }

  /** Skip within whatever list the current station came from -- that's what
   *  "next" means to a listener browsing a country or a search result. */
  function step(delta) {
    if (!state.queue.length) return;
    const n = (state.index + delta + state.queue.length) % state.queue.length;
    play(state.queue[n], state.queue, n);
  }

  audio.addEventListener("playing", () => {
    setState("● Live");
    $("np-state").classList.add("live");
    document.body.classList.remove("paused");
    $("toggle-icon").textContent = "⏸";
  });
  audio.addEventListener("pause", () => {
    setState("Paused");
    $("np-state").classList.remove("live");
    document.body.classList.add("paused");
    $("toggle-icon").textContent = "▶";
  });
  audio.addEventListener("waiting", () => setState("Buffering…"));
  audio.addEventListener("error", () => {
    $("np-state").classList.remove("live");
    setState("Stream offline");
    $("toggle-icon").textContent = "▶";
  });

  $("toggle").addEventListener("click", () => {
    if (!state.current) return;
    if (audio.paused) audio.play().catch(() => setState("Can't play"));
    else audio.pause();
  });
  $("next").addEventListener("click", () => step(1));
  $("prev").addEventListener("click", () => step(-1));
  $("vol").addEventListener("input", (e) => (audio.volume = Number(e.target.value)));

  $("close-player").addEventListener("click", () => {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    state.current = null;
    $("player").hidden = true;
    markActive();
  });

  /* ---------------- recently played ---------------- */

  const RECENT_KEY = "gt_recent";

  function readRecent() {
    try {
      return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    } catch {
      return [];   // private mode / storage blocked
    }
  }

  function remember(s) {
    try {
      const prev = readRecent().filter((x) => x.u !== s.u);
      prev.unshift(s);
      localStorage.setItem(RECENT_KEY, JSON.stringify(prev.slice(0, 24)));
    } catch {
      /* not worth interrupting playback over */
    }
  }

  /* ---------------- views ---------------- */

  const panels = {
    featured: $("featured-panel"),
    results: $("results-panel"),
    recent: $("recent-panel"),
  };

  function show(which) {
    panels.featured.hidden = which !== "featured";
    panels.results.hidden = which !== "results";
    panels.recent.hidden = which !== "recent";
  }

  function showRecent() {
    const items = readRecent();
    renderTiles($("recent"), items);
    $("recent-empty").hidden = items.length > 0;
    show("recent");
  }

  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("is-on"));
      btn.classList.add("is-on");
      if (btn.dataset.view === "recent") {
        showRecent();
      } else {
        renderTiles($("featured"), state.featured, 60);
        show("featured");
      }
      closeSidebar();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  async function showCountry(c) {
    const items = await loadCountry(c.c);
    $("results-title").textContent = `${flag(c.c)} ${c.n} · ${items.length} stations`.trim();
    renderTiles($("results"), items);
    $("results-empty").hidden = true;
    show("results");
    closeSidebar();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function showGenre(g) {
    const top = state.countries.slice(0, 24).map((c) => loadCountry(c.c));
    const pool = (await Promise.all(top)).flat();
    const needle = g.toLowerCase();
    const out = pool.filter((s) => (s.g || "").toLowerCase().includes(needle));
    $("results-title").textContent = `${g} · ${out.length} stations`;
    renderTiles($("results"), out);
    $("results-empty").hidden = out.length > 0;
    show("results");
  }

  /* ---------------- search ---------------- */

  let timer;
  async function runSearch(raw) {
    const q = raw.trim().toLowerCase();
    if (q.length < 2) {
      renderTiles($("featured"), state.featured, 60);
      show("featured");
      return;
    }

    // "kenya" or "ke" should open that country rather than scan only what
    // happens to be in memory.
    const hit = state.countries.find(
      (c) => c.n.toLowerCase() === q || c.c.toLowerCase() === q
    );
    if (hit) return showCountry(hit);

    const pool = [];
    for (const items of state.loaded.values()) pool.push(...items);
    if (pool.length < 4000) {
      const top = state.countries.slice(0, 12).map((c) => loadCountry(c.c));
      for (const items of await Promise.all(top)) pool.push(...items);
    }

    const seen = new Set();
    const out = [];
    for (const s of pool) {
      if (seen.has(s.u)) continue;
      if (`${s.t} ${s.g} ${s.l} ${s.c}`.toLowerCase().includes(q)) {
        seen.add(s.u);
        out.push(s);
      }
      if (out.length >= 120) break;
    }

    $("results-title").textContent = `Results for “${raw.trim()}”`;
    renderTiles($("results"), out);
    $("results-empty").hidden = out.length > 0;
    show("results");
  }

  $("search").addEventListener("input", (e) => {
    clearTimeout(timer);
    const v = e.target.value;
    timer = setTimeout(() => runSearch(v), 220);
  });
  $("clear-search").addEventListener("click", () => {
    $("search").value = "";
    renderTiles($("featured"), state.featured, 60);
    show("featured");
  });

  /* ---------------- mobile sidebar ---------------- */

  const sidebar = $("sidebar");
  const scrim = $("scrim");
  const closeSidebar = () => {
    sidebar.classList.remove("open");
    scrim.hidden = true;
  };
  $("menu").addEventListener("click", () => {
    sidebar.classList.toggle("open");
    scrim.hidden = !sidebar.classList.contains("open");
  });
  scrim.addEventListener("click", closeSidebar);

  /* ---------------- boot ---------------- */

  function chip(label, count, onClick) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.textContent = label;
    if (count != null) {
      const n = document.createElement("span");
      n.className = "n";
      n.textContent = count;
      b.append(n);
    }
    b.addEventListener("click", onClick);
    return b;
  }

  async function boot() {
    try {
      const [featured, countries, genres, stats] = await Promise.all([
        getJSON("/data/featured.json"),
        getJSON("/data/countries.json"),
        getJSON("/data/genres.json"),
        getJSON("/data/stats.json").catch(() => null),
      ]);

      state.featured = featured;
      state.countries = countries;

      renderTiles($("featured"), featured, 60);

      const side = $("side-countries");
      countries.slice(0, 120).forEach((c) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "side-c";
        const f = document.createElement("span");
        f.className = "flag";
        f.textContent = flag(c.c);
        const nm = document.createElement("span");
        nm.textContent = c.n || c.c;
        const n = document.createElement("span");
        n.className = "n";
        n.textContent = c.k;
        b.append(f, nm, n);
        b.addEventListener("click", () => showCountry(c));
        side.append(b);
      });

      const gnode = $("genres");
      genres.slice(0, 32).forEach((g) => gnode.append(chip(g.g, g.k, () => showGenre(g.g))));

      if (stats) {
        $("stat-web").textContent = stats.web.toLocaleString();
        $("stat-countries").textContent = stats.countries.toLocaleString();
        const ao = stats.appOnly.toLocaleString();
        $("stat-apponly").textContent = ao;
        $("side-apponly").textContent = `${ao} more stations`;
      }

      // Deep link: /?q=jazz
      const q = new URLSearchParams(location.search).get("q");
      if (q) {
        $("search").value = q;
        runSearch(q);
      }
    } catch (err) {
      console.error(err);
      $("featured").innerHTML =
        '<p class="empty">Couldn\'t load stations. Please refresh.</p>';
    }
  }

  boot();
})();
