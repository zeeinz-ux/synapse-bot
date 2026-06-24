(function () {
  "use strict";

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
    revealEls.forEach((el) => el.classList.add("revealed"));
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
    } catch (_) {}
  }
  loadStats();

  // ── FAQ Accordion ──
  const faqItems = document.querySelectorAll(".faq-item");
  faqItems.forEach((item) => {
    const question = item.querySelector(".faq-question");
    if (question) {
      question.addEventListener("click", () => {
        const isActive = item.classList.contains("active");
        faqItems.forEach((other) => {
          if (other !== item) {
            other.classList.remove("active");
            const q = other.querySelector(".faq-question");
            const a = other.querySelector(".faq-answer");
            if (q) q.setAttribute("aria-expanded", "false");
            if (a) a.setAttribute("aria-hidden", "true");
          }
        });
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

    let initialCount = 0;
    commandCards.forEach((card) => {
      initialCount += card.querySelectorAll(".command-row").length;
    });
    if (cmdCount)
      cmdCount.textContent = `Menampilkan semua ${initialCount} perintah`;
  }
})();
