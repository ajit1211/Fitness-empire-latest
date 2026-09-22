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

  /* ---- Toasts ----
     Used for anything answered over fetch(), where a Django flash message
     would only appear on the next full page load. */
  var toastStack = null;

  function toast(message, level) {
    if (!message) return;
    if (!toastStack) {
      toastStack = document.createElement("div");
      toastStack.className = "toast-stack";
      toastStack.setAttribute("role", "status");
      toastStack.setAttribute("aria-live", "polite");
      document.body.appendChild(toastStack);
    }

    var box = document.createElement("div");
    box.className = "toast toast--" + (level || "success");

    var text = document.createElement("span");
    text.textContent = message;
    box.appendChild(text);

    var close = document.createElement("button");
    close.type = "button";
    close.className = "toast__close";
    close.setAttribute("aria-label", "Dismiss");
    close.innerHTML = "&times;";
    box.appendChild(close);

    toastStack.appendChild(box);
    window.requestAnimationFrame(function () {
      box.classList.add("is-in");
    });

    var timer = window.setTimeout(dismiss, 4200);
    close.addEventListener("click", function () {
      window.clearTimeout(timer);
      dismiss();
    });

    function dismiss() {
      box.classList.remove("is-in");
      window.setTimeout(function () {
        if (box.parentNode) box.parentNode.removeChild(box);
      }, 300);
    }
  }

  /* ---- Navbar counters ---- */
  function setBadge(selector, value) {
    if (typeof value !== "number") return;
    document.querySelectorAll(selector).forEach(function (el) {
      el.textContent = value;
      el.classList.toggle("is-empty", value <= 0);
    });
  }

  function applyCounts(data) {
    setBadge("[data-cart-count]", data.cart_count);
    setBadge("[data-wishlist-count]", data.wishlist_count);
  }

  /* ---- Submit a form over fetch, keeping the plain POST as the fallback ---- */
  function postForm(form) {
    var body = new FormData(form);
    var token = body.get("csrfmiddlewaretoken");

    return fetch(form.action, {
      method: "POST",
      body: body,
      credentials: "same-origin",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": token || ""
      }
    }).then(function (res) {
      // A redirect to the sign-in page, or any non-JSON answer, means we
      // cannot handle this in place: let the browser do a real submit.
      var type = res.headers.get("Content-Type") || "";
      if (!res.ok || type.indexOf("application/json") === -1) {
        throw new Error("non-json");
      }
      return res.json();
    });
  }

  /* ---- Quantity stepper on the product page ---- */
  function initQtyStepper() {
    document.querySelectorAll("[data-buybox]").forEach(function (box) {
      var input = box.querySelector("[data-qty-input]");
      if (!input) return;

      var mirrors = box.querySelectorAll("[data-qty-mirror]");
      var steppers = box.querySelectorAll("[data-qty-step]");
      var min = parseInt(input.getAttribute("min"), 10) || 1;
      var max = parseInt(input.getAttribute("max"), 10) || 1;

      function sync() {
        var value = parseInt(input.value, 10);
        if (isNaN(value)) value = min;
        value = Math.max(min, Math.min(value, max));
        input.value = value;

        mirrors.forEach(function (field) {
          field.value = value;
        });
        steppers.forEach(function (btn) {
          var step = parseInt(btn.getAttribute("data-qty-step"), 10);
          btn.disabled = step < 0 ? value <= min : value >= max;
        });
      }

      steppers.forEach(function (btn) {
        btn.addEventListener("click", function () {
          var step = parseInt(btn.getAttribute("data-qty-step"), 10) || 0;
          input.value = (parseInt(input.value, 10) || min) + step;
          sync();
        });
      });

      input.addEventListener("change", sync);
      input.addEventListener("blur", sync);
      sync();
    });
  }

  /* ---- Add to cart without a reload ----
     On the product page the primary slot swaps to "View cart", which is the
     whole point of the two-slot layout: slot one tracks whether the product is
     already in the basket, slot two always offers the direct purchase. */
  function initAddToCart() {
    document.querySelectorAll("[data-add-form]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();

        var button = form.querySelector("[data-add-btn]");
        var original = button ? button.innerHTML : "";
        if (button) {
          button.disabled = true;
          button.textContent = "Adding...";
        }

        postForm(form)
          .then(function (data) {
            applyCounts(data);
            toast(data.message, data.level);

            var box = form.closest("[data-buybox]");
            var viewCart = box && box.querySelector("[data-view-cart]");

            if (data.ok && viewCart) {
              var count = viewCart.querySelector("[data-cart-qty]");
              if (count && typeof data.in_cart === "number") {
                count.textContent = data.in_cart;
              }
              form.hidden = true;
              viewCart.hidden = false;
              return;
            }

            // A card in the grid has no second slot to swap in, so the button
            // confirms in place and returns to normal.
            if (button) {
              button.disabled = false;
              button.innerHTML = original;
              if (data.ok) {
                button.textContent = "Added ✓";
                window.setTimeout(function () {
                  button.innerHTML = original;
                }, 2200);
              }
            }
          })
          .catch(function () {
            // Fetch failed, or we were bounced to the sign-in page. Fall back
            // to a normal submit so the shopper still gets somewhere useful.
            form.submit();
          });
      });
    });
  }

  /* ---- Wishlist toggle without a reload ---- */
  function initWishlist() {
    document.querySelectorAll("[data-wish-form]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();

        var button = form.querySelector("[data-wish-btn]");
        if (button) button.disabled = true;

        postForm(form)
          .then(function (data) {
            applyCounts(data);
            toast(data.message, data.level);

            // The product page shows the same product twice (the heart over
            // the image and the labelled button), so every control pointing at
            // this URL is updated, not just the one that was clicked.
            document
              .querySelectorAll('[data-wish-form][action="' + form.getAttribute("action") + '"]')
              .forEach(function (twin) {
                var btn = twin.querySelector("[data-wish-btn]");
                if (!btn) return;
                btn.disabled = false;
                btn.classList.toggle("is-saved", data.saved);
                btn.setAttribute("aria-pressed", data.saved ? "true" : "false");
                btn.title = data.saved ? "Remove from wishlist" : "Save to wishlist";

                var label = btn.querySelector("[data-wish-text]");
                if (label) label.textContent = data.saved ? "Saved" : "Save for later";

                if (data.saved && !reduceMotion) {
                  btn.classList.add("is-pulsing");
                  window.setTimeout(function () {
                    btn.classList.remove("is-pulsing");
                  }, 460);
                }
              });
          })
          .catch(function () {
            form.submit();
          });
      });
    });
  }

  /* ---- Keep the PayPal button from being double-submitted ---- */
  function initPaypal() {
    document.querySelectorAll(".paypal-form").forEach(function (form) {
      form.addEventListener("submit", function () {
        var btn = form.querySelector("[data-paypal-btn]");
        if (!btn) return;
        btn.classList.add("is-busy");
        var label = btn.querySelector(".paypal-btn__label");
        if (label) label.textContent = "Redirecting...";
      });
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
    initQtyStepper();
    initAddToCart();
    initWishlist();
    initPaypal();
  });
})();
