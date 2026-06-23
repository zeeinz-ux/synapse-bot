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

    // Tutup saat klik link dalam menu mobile
    mobileMenu.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        mobileMenu.classList.remove("open");
        hamburgerBtn.classList.remove("open");
        hamburgerBtn.setAttribute("aria-expanded", "false");
        mobileMenu.setAttribute("aria-hidden", "true");
      });
    });

    // Tutup saat klik di luar
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
      const targetEl = document.querySelector(targetId);
      if (targetEl) {
        e.preventDefault();
        // Tutup mobile menu kalau terbuka
        if (mobileMenu && mobileMenu.classList.contains("open")) {
          mobileMenu.classList.remove("open");
          hamburgerBtn.classList.remove("open");
          hamburgerBtn.setAttribute("aria-expanded", "false");
          mobileMenu.setAttribute("aria-hidden", "true");
        }
        // Scroll ke target section dengan offset navbar
        const offset = 80;
        const targetPos =
          targetEl.getBoundingClientRect().top + window.scrollY - offset;
        window.scrollTo({ top: targetPos, behavior: "smooth" });
      }
    });
  });

  // ── Scroll reveal ──
  const revealEls = document.querySelectorAll("[data-reveal]");
  if ("IntersectionObserver" in window && revealEls.length) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("revealed");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" },
    );
    revealEls.forEach((el) => observer.observe(el));
  } else {
    // Fallback: langsung tampilkan semua
    revealEls.forEach((el) => el.classList.add("revealed"));
  }

  // ── Active nav link by scroll position ──
  const sections = document.querySelectorAll("section[id]");
  const navLinks = document.querySelectorAll(".navbar-links a");
  if (sections.length && navLinks.length) {
    const onNavScroll = () => {
      let current = "";
      sections.forEach((sec) => {
        if (window.scrollY >= sec.offsetTop - 80) current = sec.id;
      });
      navLinks.forEach((link) => {
        const href = link.getAttribute("href").replace("/", "");
        link.classList.toggle(
          "active",
          href === "#" + current ||
            (current === "" && link.getAttribute("href") === "/"),
        );
      });
    };
    window.addEventListener("scroll", onNavScroll, { passive: true });
  }

  // ── Format angka stats dari API ──
  async function loadStats() {
    try {
      const res = await fetch("/api/stats");
      if (!res.ok) return;
      const data = await res.json();
      const guildsEl = document.getElementById("stat-guilds");
      const membersEl = document.getElementById("stat-members");
      if (guildsEl && data.guilds !== undefined)
        guildsEl.textContent = data.guilds.toLocaleString("id-ID");
      if (membersEl && data.members !== undefined)
        membersEl.textContent = data.members.toLocaleString("id-ID");
    } catch (_) {
      // API tidak tersedia — nilai default dari template tetap tampil
    }
  }
  loadStats();

  // ── FAQ Accordion ──
  const faqItems = document.querySelectorAll(".faq-item");
  faqItems.forEach((item) => {
    const question = item.querySelector(".faq-question");
    if (question) {
      question.addEventListener("click", () => {
        const isActive = item.classList.contains("active");
        // Close all other items
        faqItems.forEach((other) => {
          if (other !== item) {
            other.classList.remove("active");
            const q = other.querySelector(".faq-question");
            const a = other.querySelector(".faq-answer");
            if (q) q.setAttribute("aria-expanded", "false");
            if (a) a.setAttribute("aria-hidden", "true");
          }
        });
        // Toggle current
        item.classList.toggle("active", !isActive);
        question.setAttribute("aria-expanded", String(!isActive));
        const answer = item.querySelector(".faq-answer");
        if (answer) answer.setAttribute("aria-hidden", String(isActive));
      });
    }
  });

  // ── Commands Search (Real-time) ──
  const cmdSearch = document.getElementById("cmdSearch");
  const cmdCount = document.getElementById("cmdCount");
  const cmdGrid = document.getElementById("commandsGrid");

  if (cmdSearch && cmdGrid) {
    const commandCards = cmdGrid.querySelectorAll(".command-card");

    cmdSearch.addEventListener("input", (e) => {
      const query = e.target.value.trim().toLowerCase();
      let totalVisible = 0;
      let totalCommands = 0;

      commandCards.forEach((card) => {
        const rows = card.querySelectorAll(".command-row");
        let cardHasMatch = false;

        rows.forEach((row) => {
          totalCommands++;
          const cmdName = row.getAttribute("data-cmd") || "";
          const cmdDesc =
            row.querySelector("span")?.textContent.toLowerCase() || "";
          const match = cmdName.includes(query) || cmdDesc.includes(query);

          row.classList.toggle("hidden", !match);
          if (match) {
            cardHasMatch = true;
            totalVisible++;
          }
        });

        card.classList.toggle("hidden", !cardHasMatch);
      });

      if (cmdCount) {
        if (query === "") {
          cmdCount.textContent = `Menampilkan semua ${totalCommands} perintah`;
        } else if (totalVisible === 0) {
          cmdCount.textContent = "Tidak ada perintah yang cocok";
        } else {
          cmdCount.textContent = `Menampilkan ${totalVisible} perintah`;
        }
      }
    });

    // Initialize count
    let initialCount = 0;
    commandCards.forEach((card) => {
      initialCount += card.querySelectorAll(".command-row").length;
    });
    if (cmdCount)
      cmdCount.textContent = `Menampilkan semua ${initialCount} perintah`;
  }

  // ── Active nav link by scroll position (updated for new sections) ──
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
        // Handle both "#section" and "/" for home
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
