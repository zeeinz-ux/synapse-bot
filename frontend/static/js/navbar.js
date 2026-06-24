(function () {
  "use strict";

  // ── Navbar scroll effect ──
  const navbar = document.getElementById("navbar");
  if (navbar) {
    const onScroll = () => {
      navbar.classList.toggle("scrolled", window.scrollY > 40);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // ── Hamburger menu ──
  const hamburgerBtn = document.getElementById("hamburgerBtn");
  const mobileMenu = document.getElementById("mobileMenu");
  if (hamburgerBtn && mobileMenu) {
    hamburgerBtn.addEventListener("click", () => {
      const isOpen = mobileMenu.classList.toggle("open");
      hamburgerBtn.classList.toggle("open", isOpen);
      hamburgerBtn.setAttribute("aria-expanded", isOpen);
      mobileMenu.setAttribute("aria-hidden", !isOpen);
    });

    mobileMenu.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        mobileMenu.classList.remove("open");
        hamburgerBtn.classList.remove("open");
        hamburgerBtn.setAttribute("aria-expanded", "false");
        mobileMenu.setAttribute("aria-hidden", "true");
      });
    });

    document.addEventListener("click", (e) => {
      if (!navbar.contains(e.target) && !mobileMenu.contains(e.target)) {
        mobileMenu.classList.remove("open");
        hamburgerBtn.classList.remove("open");
        hamburgerBtn.setAttribute("aria-expanded", "false");
        mobileMenu.setAttribute("aria-hidden", "true");
      }
    });
  }

  // ── Smooth scroll for anchor links & mobile menu auto-close ──
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener("click", (e) => {
      const targetId = anchor.getAttribute("href");
      if (targetId === "#") return;

      if (targetId === "#home") {
        e.preventDefault();
        if (mobileMenu && mobileMenu.classList.contains("open")) {
          mobileMenu.classList.remove("open");
          hamburgerBtn.classList.remove("open");
          hamburgerBtn.setAttribute("aria-expanded", "false");
          mobileMenu.setAttribute("aria-hidden", "true");
        }
        window.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }

      const targetEl = document.querySelector(targetId);
      if (targetEl) {
        e.preventDefault();
        if (mobileMenu && mobileMenu.classList.contains("open")) {
          mobileMenu.classList.remove("open");
          hamburgerBtn.classList.remove("open");
          hamburgerBtn.setAttribute("aria-expanded", "false");
          mobileMenu.setAttribute("aria-hidden", "true");
        }
        const offset = 80;
        const targetPos =
          targetEl.getBoundingClientRect().top + window.scrollY - offset;
        window.scrollTo({ top: targetPos, behavior: "smooth" });
      }
    });
  });

  // ── Active nav link by scroll position ──
  const allSections = document.querySelectorAll("section[id]");
  const allNavLinks = document.querySelectorAll(".navbar-links a");

  if (allSections.length && allNavLinks.length) {
    const onNavScroll = () => {
      let current = "";
      allSections.forEach((sec) => {
        const sectionTop = sec.offsetTop;
        const sectionHeight = sec.offsetHeight;
        if (window.scrollY >= sectionTop - 100) {
          current = sec.id;
        }
      });

      allNavLinks.forEach((link) => {
        const href = link.getAttribute("href");
        let isActive = false;
        if (href === "/" && current === "") {
          isActive = true;
        } else if (href === "/" + current || href === "#" + current) {
          isActive = true;
        }
        link.classList.toggle("active", isActive);
      });
    };
    window.addEventListener("scroll", onNavScroll, { passive: true });
    onNavScroll();
  }
})();
