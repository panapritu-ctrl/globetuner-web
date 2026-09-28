/* Globe Tuner — homepage.
   Everything rendered here comes from data/ (built by tools/build_data.py).
   The bar visualiser is decorative: cross-origin streams don't allow
   Web Audio analysis, so it animates rather than reading the signal. */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var audio = $('audio');

  var state = {
    stats: null,
    countries: [],     // [{c,n,k}]
    genres: [],        // [{g,k}]
    featured: [],      // [{i,t,u,g,l,c,f}]
    list: [],          // what the grid currently shows
    cc: null,          // selected country code, null = featured
    idx: -1,           // index of the playing station in state.list
    cache: {}
  };

  /* IANA zone for the countries we surface. Only used to print a real
     local time; a country without an entry simply doesn't show one. */
  var TZ = {
    US:'America/New_York', CA:'America/Toronto', MX:'America/Mexico_City',
    BR:'America/Sao_Paulo', AR:'America/Argentina/Buenos_Aires', CL:'America/Santiago',
    CO:'America/Bogota', PE:'America/Lima', VE:'America/Caracas',
    GB:'Europe/London', IE:'Europe/Dublin', FR:'Europe/Paris', DE:'Europe/Berlin',
    ES:'Europe/Madrid', IT:'Europe/Rome', PT:'Europe/Lisbon', NL:'Europe/Amsterdam',
    BE:'Europe/Brussels', CH:'Europe/Zurich', AT:'Europe/Vienna', SE:'Europe/Stockholm',
    NO:'Europe/Oslo', DK:'Europe/Copenhagen', FI:'Europe/Helsinki', IS:'Atlantic/Reykjavik',
    PL:'Europe/Warsaw', CZ:'Europe/Prague', SK:'Europe/Bratislava', HU:'Europe/Budapest',
    RO:'Europe/Bucharest', BG:'Europe/Sofia', GR:'Europe/Athens', HR:'Europe/Zagreb',
    RS:'Europe/Belgrade', UA:'Europe/Kyiv', RU:'Europe/Moscow', TR:'Europe/Istanbul',
    IN:'Asia/Kolkata', PK:'Asia/Karachi', BD:'Asia/Dhaka', LK:'Asia/Colombo',
    NP:'Asia/Kathmandu', CN:'Asia/Shanghai', JP:'Asia/Tokyo', KR:'Asia/Seoul',
    TW:'Asia/Taipei', HK:'Asia/Hong_Kong', SG:'Asia/Singapore', MY:'Asia/Kuala_Lumpur',
    TH:'Asia/Bangkok', VN:'Asia/Ho_Chi_Minh', ID:'Asia/Jakarta', PH:'Asia/Manila',
    AU:'Australia/Sydney', NZ:'Pacific/Auckland',
    AE:'Asia/Dubai', SA:'Asia/Riyadh', IL:'Asia/Jerusalem', QA:'Asia/Qatar',
    EG:'Africa/Cairo', MA:'Africa/Casablanca', DZ:'Africa/Algiers', TN:'Africa/Tunis',
    NG:'Africa/Lagos', GH:'Africa/Accra', KE:'Africa/Nairobi', ZA:'Africa/Johannesburg',
    ET:'Africa/Addis_Ababa', UG:'Africa/Kampala', TZ:'Africa/Dar_es_Salaam'
  };

  var DOTS = ['#ff535b','#5b9dff','#a77bff','#ffc44d','#4ade80','#3ecfcf','#ff8f6b','#f472b6'];

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }
  function num(n) { return Number(n || 0).toLocaleString('en-US'); }
  function dotFor(cc) {
    var h = 0, i;
    for (i = 0; i < cc.length; i++) h = (h * 31 + cc.charCodeAt(i)) >>> 0;
    return DOTS[h % DOTS.length];
  }
  function localTime(cc) {
    var z = TZ[cc];
    if (!z) return '';
    try {
      return new Intl.DateTimeFormat('en-GB', {
        hour: '2-digit', minute: '2-digit', hour12: false, timeZone: z
      }).format(new Date());
    } catch (e) { return ''; }
  }
  function tzAbbr(cc) {
    var z = TZ[cc];
    if (!z) return '';
    try {
      var parts = new Intl.DateTimeFormat('en-US', {
        timeZone: z, timeZoneName: 'short'
      }).formatToParts(new Date());
      for (var i = 0; i < parts.length; i++) {
        if (parts[i].type === 'timeZoneName') return parts[i].value;
      }
    } catch (e) {}
    return '';
  }
  function initials(t) {
    var w = String(t || '').replace(/[^\p{L}\p{N} ]/gu, ' ').trim().split(/\s+/);
    if (!w[0]) return '?';
    return (w[0][0] + (w[1] ? w[1][0] : '')).toUpperCase();
  }
  function json(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    });
  }

  /* ── ribbon ── */
  function setRibbon(name, count, cc) {
    var t = localTime(cc), z = tzAbbr(cc);
    var bits = [String(name).toUpperCase(), num(count) + ' STATIONS'];
    if (t) bits.push(t + (z ? ' ' + z : ''));
    $('ribbon-country').textContent = bits.join(' • ');
  }

  /* ── country pills ── */
  function renderPills() {
    var top = state.countries.slice(0, 9);
    var html = '<button class="pill is-on" data-cc="" type="button">' +
      '<span class="pdot" style="background:' + DOTS[0] + '"></span>Popular' +
      '<span class="pk">' + num(state.featured.length) + '</span></button>';
    top.forEach(function (c) {
      html += '<button class="pill" data-cc="' + esc(c.c) + '" type="button">' +
        '<span class="pdot" style="background:' + dotFor(c.c) + '"></span>' +
        esc(shortName(c.n)) + '<span class="pk">' + num(c.k) + '</span></button>';
    });
    $('country-pills').innerHTML = html;
  }
  function shortName(n) {
    return String(n)
      .replace(/^The\s+/i, '')
      .replace(/\s+Of\s+America$/i, '')
      .replace(/\s+Federation$/i, '');
  }

  /* ── grid ── */
  function cardHTML(s, i) {
    var logo = s.f
      ? '<img src="' + esc(s.f) + '" alt="" loading="lazy" decoding="async" ' +
        'onerror="this.parentNode.textContent=this.dataset.ini" data-ini="' + esc(initials(s.t)) + '">'
      : esc(initials(s.t));
    return '<button class="card" data-i="' + i + '" type="button">' +
      '<div class="card-top">' +
        '<span class="card-logo">' + logo + '</span>' +
        '<span class="card-id">' +
          '<span class="card-name"><span class="nm">' + esc(s.t) + '</span>' +
            '<span class="tag-live">Live</span></span>' +
          '<span class="card-loc">' + esc(s.l || '') + '</span>' +
        '</span>' +
      '</div>' +
      '<div class="card-mid"><div class="card-genre">' +
        '<span class="g">' + esc(s.g || 'Radio') + '</span>' +
        '<span class="card-cc">' + esc(s.c || '') + '</span>' +
      '</div></div>' +
      '<div class="card-bot">' +
        '<span class="card-status">Streams in browser</span>' +
        '<span class="card-play">▶</span>' +
      '</div>' +
    '</button>';
  }

  function renderGrid(list, eyebrow, title) {
    state.list = list;
    $('grid-eyebrow').textContent = eyebrow;
    $('grid-title').textContent = title;
    $('cards-empty').hidden = list.length > 0;
    $('cards').innerHTML = list.slice(0, 48).map(cardHTML).join('');
    markPlaying();
  }

  function markPlaying() {
    var nodes = $('cards').querySelectorAll('.card'), i;
    for (i = 0; i < nodes.length; i++) {
      var on = Number(nodes[i].dataset.i) === state.idx && !audio.paused;
      nodes[i].classList.toggle('is-playing', on);
      nodes[i].querySelector('.card-play').textContent = on ? '❚❚' : '▶';
    }
  }

  /* ── scale under the monitor ── */
  function renderScale(cc) {
    var top = state.countries.slice(0, 6);
    $('scale-labels').innerHTML = top.map(function (c) {
      return '<span class="' + (c.c === cc ? 'on' : '') + '">' + esc(c.c) + '</span>';
    }).join('');
    var sel = state.countries.filter(function (c) { return c.c === cc; })[0];
    var pct = sel ? Math.max(3, Math.min(100, (sel.k / state.countries[0].k) * 100)) : 0;
    $('scale-fill').style.width = pct + '%';
    $('scale-note').textContent = sel
      ? num(sel.k) + ' of ' + num(state.stats.web) + ' browser-ready'
      : 'Catalogue coverage';
  }

  /* ── country selection ── */
  function loadCountry(cc) {
    var pills = $('country-pills').querySelectorAll('.pill'), i;
    for (i = 0; i < pills.length; i++) {
      pills[i].classList.toggle('is-on', pills[i].dataset.cc === (cc || ''));
    }
    state.cc = cc || null;

    if (!cc) {
      $('hero-count').textContent = num(state.stats.web);
      $('hero-country').textContent = 'Radio from around the world';
      $('hero-sub').textContent =
        'Hand-picked stations from ' + num(state.stats.countries) +
        ' countries, all playing straight in your browser. No sign-up, no download.';
      setRibbon('Worldwide', state.stats.web, null);
      renderScale(null);
      renderGrid(state.featured, 'Popular right now', 'Editor’s picks');
      return;
    }

    var meta = state.countries.filter(function (c) { return c.c === cc; })[0] || { n: cc, k: 0 };
    $('hero-count').textContent = num(meta.k);
    $('hero-country').textContent = shortName(meta.n);
    $('hero-sub').textContent =
      num(meta.k) + ' live stations from ' + shortName(meta.n) +
      ' that play in your browser. Tap any card to start listening.';
    setRibbon(shortName(meta.n), meta.k, cc);
    renderScale(cc);

    if (state.cache[cc]) { renderGrid(state.cache[cc], shortName(meta.n), 'Live stations'); return; }
    $('cards').innerHTML = '<div class="sk"></div><div class="sk"></div><div class="sk"></div>';
    json('/data/c/' + cc + '.json').then(function (list) {
      state.cache[cc] = list;
      if (state.cc === cc) renderGrid(list, shortName(meta.n), 'Live stations');
    }).catch(function () {
      if (state.cc === cc) renderGrid([], shortName(meta.n), 'Live stations');
    });
  }

  /* ── gateways ── */
  function renderGateways() {
    var skip = state.cc;
    var picks = state.countries.filter(function (c) { return c.c !== skip; }).slice(0, 4);
    Promise.all(picks.map(function (c) {
      if (state.cache[c.c]) return Promise.resolve(state.cache[c.c]);
      return json('/data/c/' + c.c + '.json')
        .then(function (l) { state.cache[c.c] = l; return l; })
        .catch(function () { return []; });
    })).then(function (lists) {
      $('gateways').innerHTML = picks.map(function (c, i) {
        var names = lists[i].slice(0, 3).map(function (s) { return s.t; }).join(', ');
        var t = localTime(c.c), z = tzAbbr(c.c);
        return '<button class="gw" data-cc="' + esc(c.c) + '" type="button">' +
          '<span class="gw-ico" style="color:' + dotFor(c.c) + '">◉</span>' +
          '<span class="gw-k">' + num(c.k) + ' stations</span>' +
          '<span class="gw-n">' + esc(shortName(c.n)) + '</span>' +
          '<span class="gw-s">' + esc(names || 'Browse the full list') + '</span>' +
          '<span class="gw-f"><span>' + (t ? esc(t + (z ? ' ' + z : '')) : 'Local radio') +
          '</span><span>→</span></span>' +
        '</button>';
      }).join('');
    });
  }

  /* ── genres ── */
  function renderGenres() {
    $('genres').innerHTML = state.genres.slice(0, 18).map(function (g) {
      return '<button class="chip" data-g="' + esc(g.g) + '" type="button">' +
        esc(g.g) + ' <b>' + num(g.k) + '</b></button>';
    }).join('');
  }

  /* ── search ── */
  var searchTimer;
  function runSearch(q) {
    q = q.trim().toLowerCase();
    $('clear-search').hidden = !q;
    if (!q) { loadCountry(state.cc); return; }

    // country name match -> jump straight to that country
    var byCountry = state.countries.filter(function (c) {
      return c.n.toLowerCase().indexOf(q) === 0 || c.c.toLowerCase() === q;
    })[0];
    if (byCountry) { loadCountry(byCountry.c); return; }

    var pool = state.featured.slice();
    Object.keys(state.cache).forEach(function (k) { pool = pool.concat(state.cache[k]); });

    var seen = {}, hits = [];
    pool.forEach(function (s) {
      if (seen[s.i]) return;
      var hay = (s.t + ' ' + (s.g || '') + ' ' + (s.l || '')).toLowerCase();
      if (hay.indexOf(q) !== -1) { seen[s.i] = 1; hits.push(s); }
    });
    renderGrid(hits, 'Search', '“' + q + '” — ' + hits.length + ' station' + (hits.length === 1 ? '' : 's'));
    if (hits.length < 6) {
      $('cards-empty').hidden = hits.length > 0;
      $('cards-empty').textContent = hits.length
        ? ''
        : 'Nothing matched here. Try a country name, or search all ' +
          num(state.stats.total) + ' stations in the app.';
    }
  }

  /* ── player ── */
  function play(i) {
    var s = state.list[i];
    if (!s) return;
    state.idx = i;
    $('player').hidden = false;

    var art = $('np-art');
    art.innerHTML = s.f
      ? '<img src="' + esc(s.f) + '" alt="" onerror="this.parentNode.textContent=\'' +
        esc(initials(s.t)).replace(/'/g, '') + '\'">'
      : esc(initials(s.t));

    $('np-title').textContent = s.t;
    $('np-sub').textContent = [s.g, s.l].filter(Boolean).join(' · ');
    $('mon-title').textContent = s.t;
    $('mon-sub').textContent = [s.g, s.l].filter(Boolean).join(' · ');
    setState('Connecting');

    audio.src = s.u;
    audio.play().catch(function () { setState('Blocked', true); });
    markPlaying();
    history.replaceState(null, '', '#' + encodeURIComponent(s.i));
  }

  function setState(txt, isErr) {
    var st = $('np-state');
    st.textContent = txt;
    st.classList.toggle('err', !!isErr);
    $('mon-state').textContent = txt;
    var live = txt === 'Live';
    $('mon-state').classList.toggle('on', live);
    $('viz').classList.toggle('live', live);
    $('now-eq').classList.toggle('live', live);
    $('toggle-icon').textContent = live || txt === 'Connecting' ? '❚❚' : '▶';
    $('toggle').classList.toggle('loading', txt === 'Connecting');
  }

  function step(d) {
    if (!state.list.length) return;
    play((state.idx + d + state.list.length) % state.list.length);
  }
  function random() {
    if (!state.list.length) return;
    play(Math.floor(Math.random() * Math.min(state.list.length, 48)));
  }

  audio.addEventListener('playing', function () { setState('Live'); markPlaying(); });
  audio.addEventListener('waiting', function () { setState('Buffering'); });
  audio.addEventListener('pause',   function () { setState('Paused'); markPlaying(); });
  audio.addEventListener('error',   function () { setState('Offline', true); markPlaying(); });

  /* ── events ── */
  document.addEventListener('click', function (e) {
    var pill = e.target.closest('.pill');
    if (pill) { $('search').value = ''; $('clear-search').hidden = true;
                loadCountry(pill.dataset.cc || null); renderGateways(); return; }

    var gw = e.target.closest('.gw');
    if (gw) { loadCountry(gw.dataset.cc); renderGateways();
              document.querySelector('.console').scrollIntoView({ behavior: 'smooth', block: 'start' }); return; }

    var chip = e.target.closest('.chip');
    if (chip) { $('search').value = chip.dataset.g; runSearch(chip.dataset.g); 
                $('grid-panel').scrollIntoView({ behavior: 'smooth', block: 'start' }); return; }

    var card = e.target.closest('.card');
    if (card) {
      var i = Number(card.dataset.i);
      if (i === state.idx && !audio.paused) { audio.pause(); } else { play(i); }
      return;
    }

    var nav = e.target.closest('.nav-item');
    if (nav) {
      var items = document.querySelectorAll('.nav-item');
      for (var k = 0; k < items.length; k++) items[k].classList.remove('is-on');
      nav.classList.add('is-on');
      var v = nav.dataset.view;
      if (v === 'countries') location.href = '/countries/';
      else if (v === 'genres') location.href = '/genres/';
      else if (v === 'recent') { loadCountry(null); window.scrollTo({ top: 0, behavior: 'smooth' }); }
      return;
    }
  });

  $('toggle').addEventListener('click', function () {
    if (audio.paused) { audio.play().catch(function () { setState('Blocked', true); }); }
    else audio.pause();
  });
  $('next').addEventListener('click', function () { step(1); });
  $('prev').addEventListener('click', function () { step(-1); });
  $('act-next').addEventListener('click', function () { step(1); });
  $('act-random').addEventListener('click', random);
  $('close-player').addEventListener('click', function () {
    audio.pause(); audio.removeAttribute('src'); audio.load();
    $('player').hidden = true; state.idx = -1; setState(''); markPlaying();
  });
  $('vol').addEventListener('input', function () { audio.volume = Number(this.value); });
  $('clear-search').addEventListener('click', function () {
    $('search').value = ''; runSearch('');
  });
  $('search').addEventListener('input', function () {
    var v = this.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () { runSearch(v); }, 180);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && document.activeElement !== $('search')) {
      e.preventDefault(); $('search').focus();
    }
    if (e.key === ' ' && document.activeElement === document.body && state.idx >= 0) {
      e.preventDefault(); $('toggle').click();
    }
  });

  /* ── boot ── */
  Promise.all([
    json('/data/stats.json'),
    json('/data/countries.json'),
    json('/data/genres.json'),
    json('/data/featured.json')
  ]).then(function (r) {
    state.stats = r[0]; state.countries = r[1]; state.genres = r[2]; state.featured = r[3];

    $('stat-web').textContent       = num(state.stats.web);
    $('stat-countries').textContent = num(state.stats.countries);
    $('strip-web').textContent      = num(state.stats.web);
    $('strip-countries').textContent= num(state.stats.countries);
    $('strip-app').textContent      = num(state.stats.appOnly);
    $('stat-apponly').textContent   = num(state.stats.appOnly);

    renderPills();
    renderGenres();
    loadCountry(null);
    renderGateways();

    // keep the ribbon's clock honest
    setInterval(function () {
      var cc = state.cc;
      if (!cc) return;
      var m = state.countries.filter(function (c) { return c.c === cc; })[0];
      if (m) setRibbon(shortName(m.n), m.k, cc);
    }, 30000);

    var q = new URLSearchParams(location.search).get('q');
    if (q) { $('search').value = q; runSearch(q); }
  }).catch(function () {
    $('cards').innerHTML = '';
    $('cards-empty').hidden = false;
    $('cards-empty').textContent = 'Could not load the station list. Please refresh.';
  });
})();
