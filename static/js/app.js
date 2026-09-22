/* Fitness Empire - site behaviour.
   Small, dependency-free replacement for Bootstrap's JS bundle. */
(function () {
  "use strict";

  /* ---- Mobile navigation ---- */
  function initNav() {
    var toggle = document.querySelector("[data-nav-toggle]");
    var menu = document.getElementById("nav-menu");
    if (!toggle || !menu) return;

    toggle.addEventListener("click", function () {
      var open = menu.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });

    // Close the menu when a link inside it is followed.
    menu.addEventListener("click", function (e) {
      if (e.target.closest("a")) {
        menu.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* ---- Account dropdown (hover handled in CSS; this adds click + keyboard) ---- */
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

  /* ---- Slideshow (replaces the Bootstrap carousel) ---- */
  function initSlides() {
    document.querySelectorAll("[data-slides]").forEach(function (root) {
      var items = Array.prototype.slice.call(
        root.querySelectorAll(".slides__item")
      );
      if (items.length < 2) return;

      var dotsWrap = root.querySelector(".slides__dots");
      var index = items.findIndex(function (el) {
        return el.classList.contains("is-active");
      });
      if (index < 0) index = 0;

      var dots = [];
      if (dotsWrap) {
        items.forEach(function (_, i) {
          var b = document.createElement("button");
          b.type = "button";
          b.setAttribute("aria-label", "Go to slide " + (i + 1));
          b.addEventListener("click", function () {
            show(i);
            restart();
          });
          dotsWrap.appendChild(b);
          dots.push(b);
        });
      }

      function show(next) {
        items[index].classList.remove("is-active");
        if (dots[index]) dots[index].classList.remove("is-active");
        index = (next + items.length) % items.length;
        items[index].classList.add("is-active");
        if (dots[index]) dots[index].classList.add("is-active");
      }

      var timer = null;
      function start() {
        if (
          window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ) {
          return;
        }
        timer = window.setInterval(function () {
          show(index + 1);
        }, 5500);
      }
      function stop() {
        if (timer) window.clearInterval(timer);
        timer = null;
      }
      function restart() {
        stop();
        start();
      }

      var prev = root.querySelector(".slides__nav--prev");
      var next = root.querySelector(".slides__nav--next");
      if (prev)
        prev.addEventListener("click", function () {
          show(index - 1);
          restart();
        });
      if (next)
        next.addEventListener("click", function () {
          show(index + 1);
          restart();
        });

      root.addEventListener("mouseenter", stop);
      root.addEventListener("mouseleave", start);
      root.addEventListener("focusin", stop);
      root.addEventListener("focusout", start);

      show(index);
      start();
    });
  }

  /* ---- Confirm destructive links ---- */
  function initConfirms() {
    document.addEventListener("click", function (e) {
      var el = e.target.closest("[data-confirm]");
      if (!el) return;
      if (!window.confirm(el.getAttribute("data-confirm"))) {
        e.preventDefault();
      }
    });
  }

  /* ---- Auto-dismiss flash messages ---- */
  function initMessages() {
    var box = document.querySelector(".messages");
    if (!box) return;
    window.setTimeout(function () {
      box.style.transition = "opacity .4s ease, transform .4s ease";
      box.style.opacity = "0";
      box.style.transform = "translateY(-8px)";
      window.setTimeout(function () {
        box.remove();
      }, 420);
    }, 6000);
  }

  /* ---- Give Django-rendered form widgets the themed look ---- */
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

  ready(function () {
    initNav();
    initAccount();
    initSlides();
    initConfirms();
    initMessages();
    initForms();
  });
})();
