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
    genres: [],
    loaded: new Map(),   // countryCode -> stations[]
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

  /* ---------------- rendering ---------------- */

  const initials = (name) =>
    (name || "?")
      .replace(/[^\p{L}\p{N} ]/gu, "")
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((w) => w[0])
      .join("")
      .toUpperCase() || "?";

  // ISO country code -> flag emoji, via regional indicator symbols. Costs
  // nothing to ship and makes the country lists read at a glance.
  const flag = (cc) =>
    /^[A-Z]{2}$/.test(cc || "")
      ? String.fromCodePoint(...[...cc].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65))
      : "";

  function artwork(s, cls) {
    const box = document.createElement("span");
    box.className = cls;
    box.textContent = initials(s.t);
    if (s.f) {
      // Logo sits on top of the lettered tile; if it 404s or is too slow we
      // just drop it and the initials stay visible.
      const img = document.createElement("img");
      img.loading = "lazy";
      img.decoding = "async";
      img.alt = "";
      img.src = s.f;
      img.addEventListener("load", () => { box.textContent = ""; box.append(img); });
      img.addEventListener("error", () => img.remove());
    }
    return box;
  }

  function stationCard(s) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "card";
    el.dataset.url = s.u;

    const txt = document.createElement("span");
    txt.className = "card-txt";
    const t = document.createElement("span");
    t.className = "card-t";
    t.textContent = s.t;

    const sub = document.createElement("span");
    sub.className = "card-s";
    const fl = flag(s.c);
    if (fl) {
      const f = document.createElement("span");
      f.className = "flag";
      f.textContent = fl;
      sub.append(f);
    }
    const meta = document.createElement("span");
    meta.textContent = [s.g, s.l || s.c].filter(Boolean).join(" · ");
    sub.append(meta);
    txt.append(t, sub);

    const eq = document.createElement("span");
    eq.className = "eq";
    eq.setAttribute("aria-hidden", "true");
    eq.innerHTML = "<i></i><i></i><i></i>";

    el.append(artwork(s, "card-ico"), txt, eq);
    el.addEventListener("click", () => play(s, el));
    return el;
  }

  function renderInto(node, stations, limit = 120) {
    node.replaceChildren();
    const frag = document.createDocumentFragment();
    stations.slice(0, limit).forEach((s) => frag.append(stationCard(s)));
    node.append(frag);
    markActive();
  }

  function markActive() {
    const url = state.current?.u;
    document.querySelectorAll(".card").forEach((c) =>
      c.classList.toggle("active", !!url && c.dataset.url === url)
    );
  }

  /* ---------------- playback ---------------- */

  function setState(msg) {
    $("np-state").textContent = msg;
  }

  function play(station, cardEl) {
    // Tapping the station that's already playing acts as pause/resume
    // rather than restarting the stream.
    if (state.current && state.current.u === station.u && !audio.paused) {
      audio.pause();
      return;
    }

    state.current = station;
    $("player").hidden = false;
    const art = artwork(station, "np-art");
    art.id = "np-art";
    $("np-art").replaceWith(art);
    $("np-title").textContent = station.t;
    $("np-sub").textContent = [station.g, station.l || station.c]
      .filter(Boolean)
      .join(" · ");
    setState("Connecting…");

    audio.src = station.u;
    audio.play().catch(() => {
      // Autoplay refusal or a stream that won't open. Either way the user
      // gets told rather than staring at a silent bar.
      setState("Can't play");
    });

    markActive();
    if (cardEl) cardEl.classList.add("active");
    remember(station);
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

  $("close-player").addEventListener("click", () => {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    state.current = null;
    $("player").hidden = true;
    markActive();
  });

  $("vol").addEventListener("input", (e) => {
    audio.volume = Number(e.target.value);
  });

  function remember(s) {
    try {
      const key = "gt_recent";
      const prev = JSON.parse(localStorage.getItem(key) || "[]").filter(
        (x) => x.u !== s.u
      );
      prev.unshift(s);
      localStorage.setItem(key, JSON.stringify(prev.slice(0, 20)));
    } catch {
      /* private mode / storage disabled -- not worth interrupting playback */
    }
  }

  /* ---------------- search ---------------- */

  let searchTimer;
  const resultsPanel = $("results-panel");

  async function runSearch(qRaw) {
    const q = qRaw.trim().toLowerCase();
    if (q.length < 2) {
      resultsPanel.hidden = true;
      $("featured-panel").hidden = false;
      return;
    }

    // Match a country by name or code first: "kenya" or "ke" should load
    // that country rather than scan only what's already in memory.
    const hit = state.countries.find(
      (c) => c.n.toLowerCase() === q || c.c.toLowerCase() === q
    );
    if (hit) {
      await showCountry(hit);
      return;
    }

    const pool = [];
    for (const items of state.loaded.values()) pool.push(...items);
    // Nothing loaded yet: search the biggest countries so results aren't empty.
    if (pool.length < 4000) {
      const top = state.countries.slice(0, 12).map((c) => loadCountry(c.c));
      for (const items of await Promise.all(top)) pool.push(...items);
    }

    const seen = new Set();
    const out = [];
    for (const s of pool) {
      if (seen.has(s.u)) continue;
      const hay = `${s.t} ${s.g} ${s.l} ${s.c}`.toLowerCase();
      if (hay.includes(q)) {
        seen.add(s.u);
        out.push(s);
      }
      if (out.length >= 120) break;
    }

    $("results-title").textContent = `Results for “${qRaw.trim()}”`;
    renderInto($("results"), out);
    $("results-empty").hidden = out.length > 0;
    resultsPanel.hidden = false;
    $("featured-panel").hidden = true;
    resultsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  $("search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    const v = e.target.value;
    searchTimer = setTimeout(() => runSearch(v), 220);
  });

  $("clear-search").addEventListener("click", () => {
    $("search").value = "";
    resultsPanel.hidden = true;
    $("featured-panel").hidden = false;
  });

  async function showCountry(c) {
    const items = await loadCountry(c.c);
    $("results-title").textContent = `${c.n} · ${items.length} stations`;
    renderInto($("results"), items);
    $("results-empty").hidden = true;
    resultsPanel.hidden = false;
    $("featured-panel").hidden = true;
    resultsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function showGenre(g) {
    const top = state.countries.slice(0, 24).map((c) => loadCountry(c.c));
    const pool = (await Promise.all(top)).flat();
    const needle = g.toLowerCase();
    const out = pool.filter((s) => (s.g || "").toLowerCase().includes(needle));
    $("results-title").textContent = `${g} · ${out.length} stations`;
    renderInto($("results"), out);
    $("results-empty").hidden = out.length > 0;
    resultsPanel.hidden = false;
    $("featured-panel").hidden = true;
    resultsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

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

      state.countries = countries;
      state.genres = genres;

      renderInto($("featured"), featured, 60);

      const cnode = $("countries");
      countries.slice(0, 80).forEach((c) => {
        const fl = flag(c.c);
        cnode.append(chip(`${fl ? fl + " " : ""}${c.n || c.c}`, c.k, () => showCountry(c)));
      });

      const gnode = $("genres");
      genres.slice(0, 32).forEach((g) =>
        gnode.append(chip(g.g, g.k, () => showGenre(g.g)))
      );

      if (stats) {
        $("stat-web").textContent = stats.web.toLocaleString();
        $("stat-countries").textContent = stats.countries.toLocaleString();
        $("stat-apponly").textContent = stats.appOnly.toLocaleString();
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
