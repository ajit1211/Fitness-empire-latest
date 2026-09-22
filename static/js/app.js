/* Fitness Empire - site behaviour.
   Dependency-free. Replaces the old Bootstrap bundle. */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---- Mobile navigation ---- */
  function initNav() {
    var toggle = document.querySelector("[data-nav-toggle]");
    var menu = document.getElementById("nav-menu");
    if (!toggle || !menu) return;

    toggle.addEventListener("click", function () {
      var open = menu.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });

    menu.addEventListener("click", function (e) {
      if (e.target.closest("a")) {
        menu.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* ---- Mark the current page in the menu ---- */
  function initActiveLink() {
    var here = window.location.pathname;
    document.querySelectorAll(".nav__menu a").forEach(function (a) {
      var href = a.getAttribute("href");
      if (!href || href === "/") return;
      if (here === href || here.indexOf(href) === 0) {
        a.setAttribute("aria-current", "page");
      }
    });
  }

  /* ---- Shrink + shadow the navbar once scrolled ---- */
  function initStickyNav() {
    var nav = document.querySelector("[data-nav]");
    if (!nav) return;
    var ticking = false;

    function update() {
      nav.classList.toggle("is-stuck", window.scrollY > 40);
      ticking = false;
    }
    window.addEventListener(
      "scroll",
      function () {
        if (!ticking) {
          window.requestAnimationFrame(update);
          ticking = true;
        }
      },
      { passive: true }
    );
    update();
  }

  /* ---- Account dropdown (CSS handles hover; this adds click + keyboard) ---- */
  function initAccount() {
    var wrap = document.querySelector("[data-account]");
    if (!wrap) return;
    var btn = wrap.querySelector(".account__toggle");
    var menu = wrap.querySelector(".account__menu");
    if (!btn || !menu) return;

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = menu.classList.toggle("is-open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });

    document.addEventListener("click", function (e) {
      if (!wrap.contains(e.target)) {
        menu.classList.remove("is-open");
        btn.setAttribute("aria-expanded", "false");
      }
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        menu.classList.remove("is-open");
        btn.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* ---- Hero video ----
     Sources stay inert until we opt in, so phones and metered connections
     never download the clip - they keep the ~37KB poster instead. */
  function initHeroVideo() {
    var video = document.querySelector("[data-hero-video]");
    if (!video) return;

    var conn = navigator.connection || {};
    var cheapData = conn.saveData === true;
    var slow = /(^|-)2g$/.test(conn.effectiveType || "");
    var bigEnough = window.innerWidth >= 700;

    if (!bigEnough || cheapData || slow || reduceMotion) return;

    var sources = video.querySelectorAll("source[data-src]");
    if (!sources.length) return;
    Array.prototype.forEach.call(sources, function (s) {
      s.setAttribute("src", s.getAttribute("data-src"));
      s.removeAttribute("data-src");
    });

    video.load();
    var playing = video.play();
    if (playing && playing.catch) {
      playing.catch(function () {
        /* Autoplay blocked; the poster stays visible, which is fine. */
      });
    }

    // Pause while off-screen so it costs nothing on the rest of the page.
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              var p = video.play();
              if (p && p.catch) p.catch(function () {});
            } else {
              video.pause();
            }
          });
        },
        { threshold: 0.1 }
      ).observe(video);
    }

    // Sound toggle
    var sound = document.querySelector("[data-video-sound]");
    if (!sound) return;
    sound.hidden = false;
    sound.addEventListener("click", function () {
      video.muted = !video.muted;
      sound.setAttribute("aria-pressed", video.muted ? "false" : "true");
      sound.querySelector("[data-icon-on]").hidden = video.muted;
      sound.querySelector("[data-icon-off]").hidden = !video.muted;
    });
  }

  /* ---- Auto-tag common blocks for scroll reveal ----
     Saves marking up every template by hand, and keeps the motion consistent
     across the site. Anything already carrying data-reveal is left alone. */
  var AUTO_REVEAL = [
    ".section-head",
    ".panel",
    ".info-card",
    ".order-card",
    ".media-card",
    ".prod",
    ".plan",
    ".class-tile",
    ".feature",
    ".stat-row > *",
    ".split > *",
    ".empty-state",
    ".table-wrap",
    ".auth-card",
    ".cart-line",
    ".address-card",
    ".detail"
  ].join(",");

  var STAGGER_PARENTS =
    ".grid, .prod-grid, .plans, .class-grid, .stat-row, .detail-grid, .chip-row";

  function autoReveal() {
    if (reduceMotion) return;

    document.querySelectorAll(AUTO_REVEAL).forEach(function (el) {
      if (el.hasAttribute("data-reveal")) return;
      if (el.closest(".hero-video, .nav, .footer")) return;
      el.setAttribute("data-reveal", "");
      // Already on screen at load: show at once so nothing flashes.
      if (el.getBoundingClientRect().top < window.innerHeight * 0.92) {
        el.classList.add("is-visible");
      }
    });

    document.querySelectorAll(STAGGER_PARENTS).forEach(function (group) {
      if (group.hasAttribute("data-stagger")) return;
      Array.prototype.forEach.call(group.children, function (child, i) {
        if (child.hasAttribute("data-reveal") && !child.classList.contains("is-visible")) {
          child.style.setProperty("--reveal-delay", Math.min(i, 8) * 80 + "ms");
        }
      });
    });
  }

  /* ---- Scroll reveal ---- */
  function initReveal() {
    var items = document.querySelectorAll("[data-reveal]");
    if (!items.length) return;

    if (reduceMotion || !("IntersectionObserver" in window)) {
      items.forEach(function (el) {
        el.classList.add("is-visible");
      });
      return;
    }

    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          io.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
    );

    items.forEach(function (el) {
      io.observe(el);
    });
  }

  /* ---- Stagger children of [data-stagger] ---- */
  function initStagger() {
    document.querySelectorAll("[data-stagger]").forEach(function (group) {
      var step = parseInt(group.getAttribute("data-stagger"), 10) || 90;
      Array.prototype.forEach.call(group.children, function (child, i) {
        if (child.hasAttribute("data-reveal")) {
          child.style.setProperty("--reveal-delay", i * step + "ms");
        }
      });
    });
  }

  /* ---- Count up numbers when they scroll into view ---- */
  function initCounters() {
    var els = document.querySelectorAll("[data-count]");
    if (!els.length) return;

    function run(el) {
      var target = parseFloat(el.getAttribute("data-count"));
      if (isNaN(target)) return;
      var suffix = el.getAttribute("data-count-suffix") || "";
      if (reduceMotion) {
        el.textContent = target + suffix;
        return;
      }
      var dur = 1400;
      var start = null;

      function tick(ts) {
        if (start === null) start = ts;
        var p = Math.min((ts - start) / dur, 1);
        var eased = 1 - Math.pow(1 - p, 3);
        el.textContent = Math.round(target * eased) + suffix;
        if (p < 1) window.requestAnimationFrame(tick);
      }
      window.requestAnimationFrame(tick);
    }

    if (!("IntersectionObserver" in window)) {
      els.forEach(run);
      return;
    }
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          run(entry.target);
          io.unobserve(entry.target);
        });
      },
      { threshold: 0.5 }
    );
    els.forEach(function (el) {
      io.observe(el);
    });
  }

  /* ---- Back to top ---- */
  function initToTop() {
    var btn = document.querySelector("[data-to-top]");
    if (!btn) return;
    var ticking = false;

    function update() {
      btn.classList.toggle("is-visible", window.scrollY > 600);
      ticking = false;
    }
    window.addEventListener(
      "scroll",
      function () {
        if (!ticking) {
          window.requestAnimationFrame(update);
          ticking = true;
        }
      },
      { passive: true }
    );
    btn.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
    });
    update();
  }

  /* ---- Confirm destructive links ---- */
  function initConfirms() {
    document.addEventListener("click", function (e) {
      var el = e.target.closest("[data-confirm]");
      if (!el) return;
      if (!window.confirm(el.getAttribute("data-confirm"))) e.preventDefault();
    });
  }

  /* ---- Auto-dismiss flash messages ---- */
  function initMessages() {
    var box = document.querySelector(".messages");
    if (!box) return;
    window.setTimeout(function () {
      box.style.transition = "opacity .4s ease, transform .4s ease";
      box.style.opacity = "0";
      box.style.transform = "translateY(-10px)";
      window.setTimeout(function () {
        box.remove();
      }, 420);
    }, 6500);
  }

  /* ---- Theme Django's rendered form widgets ---- */
  function initForms() {
    document
      .querySelectorAll(
        ".form-body input:not([type=checkbox]):not([type=radio]):not([type=submit])," +
          ".form-body select, .form-body textarea"
      )
      .forEach(function (el) {
        el.classList.add("form-control");
      });
  }

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  document.documentElement.classList.remove("no-js");

  ready(function () {
    initNav();
    initActiveLink();
    initStickyNav();
    initAccount();
    initHeroVideo();
    initStagger();
    autoReveal();
    initReveal();
    initCounters();
    initToTop();
    initConfirms();
    initMessages();
    initForms();
  });
})();
