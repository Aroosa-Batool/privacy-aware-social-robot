// PASR documentation: theme, navigation drawer, search (⌘K), "On this page", copy buttons, tabs,
// videos that play while visible, image zoom and diagrams. No dependencies.
(function () {
  "use strict";
  var root = document.documentElement;
  var base = root.dataset.root || "./";
  var $ = function (sel, el) { return (el || document).querySelector(sel); };
  var $$ = function (sel, el) { return Array.prototype.slice.call((el || document).querySelectorAll(sel)); };

  function store(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(key);
      localStorage.setItem(key, value);
    } catch (e) { return null; }
  }

  function toast(text) {
    var el = $(".copied-toast") || document.body.appendChild(Object.assign(document.createElement("div"), { className: "copied-toast" }));
    el.textContent = text;
    el.classList.add("show");
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.classList.remove("show"); }, 1600);
  }

  function copy(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    var area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try { document.execCommand("copy"); } finally { area.remove(); }
    return Promise.resolve();
  }

  // ------------------------------------------------------------------ theme
  var media = matchMedia("(prefers-color-scheme: dark)");
  function applyTheme(pref) {
    var dark = pref === "dark" || (pref === "system" && media.matches);
    root.dataset.theme = dark ? "dark" : "light";
    root.dataset.themePref = pref;
    $$("[data-theme-set]").forEach(function (b) {
      b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", String(b.dataset.themeSet === pref));
    });
    document.dispatchEvent(new Event("pasr:theme"));
  }
  applyTheme(store("pasr-theme") || "system");
  media.addEventListener("change", function () {
    if ((store("pasr-theme") || "system") === "system") applyTheme("system");
  });
  $$("[data-theme-toggle]").forEach(function (b) {
    b.addEventListener("click", function () {
      var next = root.dataset.theme === "dark" ? "light" : "dark";
      store("pasr-theme", next);
      applyTheme(next);
    });
  });
  $$("[data-theme-set]").forEach(function (b) {
    b.addEventListener("click", function () {
      store("pasr-theme", b.dataset.themeSet);
      applyTheme(b.dataset.themeSet);
    });
  });

  // ------------------------------------------------------------------ drawer (phones, tablets)
  function setNav(open) {
    document.body.classList.toggle("nav-open", open);
    $$("[data-menu]").forEach(function (b) { b.setAttribute("aria-expanded", String(open)); });
  }
  $$("[data-menu]").forEach(function (b) {
    b.addEventListener("click", function () { setNav(!document.body.classList.contains("nav-open")); });
  });
  $$("[data-scrim]").forEach(function (s) { s.addEventListener("click", function () { setNav(false); }); });
  var active = $(".nav-link.is-active");
  if (active) active.scrollIntoView({ block: "center" });

  // ------------------------------------------------------------------ page actions
  var actions = $("[data-page-actions]");
  if (actions) {
    var menu = $(".action-menu", actions);
    var toggle = $("[data-actions-toggle]", actions);
    var close = function () { menu.hidden = true; toggle.setAttribute("aria-expanded", "false"); };
    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      menu.hidden = !menu.hidden;
      toggle.setAttribute("aria-expanded", String(!menu.hidden));
    });
    document.addEventListener("click", function (e) { if (!actions.contains(e.target)) close(); });
    $$("[data-copy-page]", actions).forEach(function (b) {
      b.addEventListener("click", function () {
        var source = $("#page-source");
        var title = $("h1") ? "# " + $("h1").textContent.trim() + "\n\n" : "";
        copy(title + (source ? source.textContent.trim() : "") + "\n").then(function () { toast("Page copied as Markdown"); });
        close();
      });
    });
  }

  // ------------------------------------------------------------------ code blocks
  $$(".prose .highlight").forEach(function (block) {
    var holder = block.closest("[data-lang]");
    var lang = holder ? holder.dataset.lang.toLowerCase() : "";
    var names = { bash: "Terminal", shell: "Terminal", console: "Terminal", sh: "Terminal", yaml: "YAML", python: "Python", py: "Python", js: "JavaScript", javascript: "JavaScript", json: "JSON", toml: "TOML", text: "Text", ini: "INI", env: ".env", sql: "SQL", bibtex: "BibTeX" };
    var head = document.createElement("div");
    head.className = "code-head";
    head.innerHTML = '<span></span><button class="code-copy" type="button" aria-label="Copy code"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg><span>Copy</span></button>';
    head.firstChild.textContent = names[lang] || lang || "Code";
    block.insertBefore(head, block.firstChild);
    $(".code-copy", head).addEventListener("click", function (e) {
      var label = $("span", e.currentTarget);
      copy(($("pre", block) || block).innerText.replace(/\n$/, "")).then(function () {
        label.textContent = "Copied";
        setTimeout(function () { label.textContent = "Copy"; }, 1400);
      });
    });
  });

  // ------------------------------------------------------------------ tabs
  $$("[data-tabs]").forEach(function (tabs) {
    var buttons = $$(".tab", tabs);
    var panels = $$(".tab-panel", tabs);
    buttons.forEach(function (button, i) {
      button.addEventListener("click", function () {
        buttons.forEach(function (b, j) { b.setAttribute("aria-selected", String(i === j)); });
        panels.forEach(function (p, j) { p.hidden = i !== j; });
      });
    });
  });

  // ------------------------------------------------------------------ on this page
  var links = $$("[data-toc]");
  if (links.length && "IntersectionObserver" in window) {
    var byId = {};
    links.forEach(function (a) { byId[decodeURIComponent(a.hash.slice(1))] = a; });
    var headings = Object.keys(byId).map(function (id) { return document.getElementById(id); }).filter(Boolean);
    var visible = new Set();
    var mark = function () {
      var current = headings.filter(function (h) { return h.getBoundingClientRect().top < 140; }).pop() || headings[0];
      links.forEach(function (a) { a.classList.toggle("is-active", byId[current.id] === a); });
    };
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) visible.add(e.target); else visible.delete(e.target); });
      mark();
    }, { rootMargin: "-80px 0px -60% 0px" });
    headings.forEach(function (h) { io.observe(h); });
    addEventListener("scroll", function () { requestAnimationFrame(mark); }, { passive: true });
    mark();
  }

  // ------------------------------------------------------------------ videos play while on screen
  var videos = $$("video[data-autoplay]");
  if (videos.length && "IntersectionObserver" in window) {
    var still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    var vo = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        var v = e.target;
        if (e.isIntersecting && !still && !v.dataset.userPaused) { var p = v.play(); if (p) p.catch(function () {}); }
        else if (!e.isIntersecting) v.pause();
      });
    }, { threshold: 0.35 });
    videos.forEach(function (v) {
      vo.observe(v);
      v.addEventListener("pause", function () { if (v.getBoundingClientRect().top < innerHeight && v.getBoundingClientRect().bottom > 0) v.dataset.userPaused = "1"; });
      v.addEventListener("play", function () { delete v.dataset.userPaused; });
    });
  }

  // ------------------------------------------------------------------ image zoom
  $$("img[data-zoom]").forEach(function (img) {
    img.addEventListener("click", function () {
      var overlay = document.createElement("div");
      overlay.className = "zoom";
      overlay.innerHTML = '<img alt="">';
      overlay.firstChild.src = img.currentSrc || img.src;
      overlay.firstChild.alt = img.alt;
      var shut = function () { overlay.remove(); removeEventListener("keydown", onKey); };
      var onKey = function (e) { if (e.key === "Escape") shut(); };
      overlay.addEventListener("click", shut);
      addEventListener("keydown", onKey);
      document.body.appendChild(overlay);
    });
  });

  // ------------------------------------------------------------------ GitHub stars
  var stars = $("[data-stars]");
  if (stars) {
    var cached = null;
    try { cached = JSON.parse(sessionStorage.getItem("pasr-stars") || "null"); } catch (e) { cached = null; }
    var show = function (n) { if (typeof n === "number" && n > 0) stars.textContent = n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(n); };
    if (cached !== null) show(cached);
    else if (window.fetch) {
      fetch("https://api.github.com/repos/Aroosa-Batool/privacy-aware-social-robot")
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          if (!d) return;
          show(d.stargazers_count);
          try { sessionStorage.setItem("pasr-stars", JSON.stringify(d.stargazers_count)); } catch (e) { /* private mode */ }
        })
        .catch(function () {});
    }
  }

  // ------------------------------------------------------------------ diagrams (mermaid, loaded only where used)
  var diagrams = $$("pre.mermaid");
  diagrams.forEach(function (d) { d.dataset.source = d.textContent; });
  function drawDiagrams() {
    var mermaid = window.PASR_MERMAID;
    if (!mermaid || !diagrams.length) return;
    var dark = root.dataset.theme === "dark";
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: "base",
      fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
      themeVariables: dark ? {
        background: "#0e131d", primaryColor: "#16223a", primaryBorderColor: "#3b6fd8", primaryTextColor: "#e6ebf5",
        lineColor: "#5d7bb5", secondaryColor: "#122a2a", tertiaryColor: "#131a27", noteBkgColor: "#1d2a40",
        noteTextColor: "#c9d2e3", noteBorderColor: "#3b6fd8", fontSize: "13px"
      } : {
        background: "#f8fafc", primaryColor: "#e8f0ff", primaryBorderColor: "#2563eb", primaryTextColor: "#0b1220",
        lineColor: "#6b86bd", secondaryColor: "#e6fbf7", tertiaryColor: "#f2f5fa", noteBkgColor: "#fff7e6",
        noteTextColor: "#2d3748", noteBorderColor: "#f59e0b", fontSize: "13px"
      }
    });
    diagrams.forEach(function (d) { d.removeAttribute("data-processed"); d.textContent = d.dataset.source; });
    mermaid.run({ nodes: diagrams }).catch(function (e) { console.warn("diagram", e); });
  }
  document.addEventListener("pasr:mermaid", drawDiagrams);
  document.addEventListener("pasr:theme", drawDiagrams);
  drawDiagrams();

  // ------------------------------------------------------------------ search
  var dialog = $("[data-search-dialog]");
  if (!dialog) return;
  var input = $("input", dialog);
  var list = $(".search-results", dialog);
  var selected = 0;
  var index = null;
  list.dataset.empty = "Type to search the documentation.";

  function loadIndex(done) {
    if (window.PASR_SEARCH) { index = window.PASR_SEARCH; return done(); }
    var s = document.createElement("script");
    s.src = base + "search-index.js";
    s.onload = function () { index = window.PASR_SEARCH || []; done(); };
    document.head.appendChild(s);
  }

  function escapeHtml(text) {
    return text.replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }

  function highlight(text, terms) {
    var out = escapeHtml(text);
    terms.forEach(function (t) {
      if (t.length < 2) return;
      out = out.replace(new RegExp("(" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig"), "<mark>$1</mark>");
    });
    return out;
  }

  function snippet(text, terms) {
    var lower = text.toLowerCase();
    var at = terms.reduce(function (best, t) { var i = lower.indexOf(t); return i >= 0 && (best < 0 || i < best) ? i : best; }, -1);
    if (at < 0) return text.slice(0, 160);
    var start = Math.max(0, at - 50);
    return (start > 0 ? "…" : "") + text.slice(start, start + 170);
  }

  function search(query) {
    var terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) { list.innerHTML = ""; list.dataset.empty = "Type to search the documentation."; return; }
    var results = [];
    index.forEach(function (e) {
      var title = e.t.toLowerCase(), head = e.h.toLowerCase(), text = e.x.toLowerCase();
      var score = 0;
      for (var i = 0; i < terms.length; i++) {
        var t = terms[i], s = 0;
        if (title.indexOf(t) >= 0) s += e.h ? 4 : 12;
        if (head.indexOf(t) >= 0) s += 8;
        if (text.indexOf(t) >= 0) s += 1 + Math.min(3, text.split(t).length - 1) * 0.5;
        if (!s) return;
        score += s;
      }
      if (title === query.toLowerCase() && !e.h) score += 30;
      results.push({ e: e, score: score });
    });
    results.sort(function (a, b) { return b.score - a.score; });
    results = results.slice(0, 14);
    selected = 0;
    list.dataset.empty = "No results for “" + query + "”.";
    list.innerHTML = results.map(function (r, i) {
      var e = r.e;
      return '<li><a role="option" href="' + base + e.u + '" aria-selected="' + (i === 0) + '">' +
        '<span class="sr-path">' + escapeHtml(e.g + (e.h ? " › " + e.t : "")) + "</span>" +
        '<span class="sr-title">' + highlight(e.h || e.t, terms) + "</span>" +
        '<span class="sr-text">' + highlight(snippet(e.x, terms), terms) + "</span></a></li>";
    }).join("");
  }

  function move(step) {
    var items = $$("a", list);
    if (!items.length) return;
    selected = (selected + step + items.length) % items.length;
    items.forEach(function (a, i) { a.setAttribute("aria-selected", String(i === selected)); });
    items[selected].scrollIntoView({ block: "nearest" });
  }

  function open() {
    dialog.hidden = false;
    document.body.style.overflow = "hidden";
    input.focus();
    input.select();
    loadIndex(function () { if (input.value) search(input.value); });
  }
  function shut() { dialog.hidden = true; document.body.style.overflow = ""; }

  $$("[data-search]").forEach(function (b) { b.addEventListener("click", open); });
  dialog.addEventListener("click", function (e) { if (e.target === dialog) shut(); });
  input.addEventListener("input", function () { if (index) search(input.value); });
  input.addEventListener("keydown", function (e) {
    if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    else if (e.key === "Enter") { var a = $$("a", list)[selected]; if (a) { shut(); location.href = a.href; } }
    else if (e.key === "Escape") shut();
  });
  addEventListener("keydown", function (e) {
    var typing = /input|textarea|select/i.test((e.target || {}).tagName || "");
    if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) { e.preventDefault(); dialog.hidden ? open() : shut(); }
    else if (e.key === "/" && !typing && dialog.hidden) { e.preventDefault(); open(); }
    else if (e.key === "Escape" && !dialog.hidden) shut();
  });
})();
