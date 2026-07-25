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

  // ── Guild Marquee ──
  function renderMarquee(guilds) {
    const container = document.getElementById("guildMarquee");
    const rightTrack = document.getElementById("marqueeTrackRight");
    const leftTrack = document.getElementById("marqueeTrackLeft");
    if (!container || !rightTrack || !leftTrack) return;

    const statItem = document.getElementById("statItemServers");

    if (!guilds || guilds.length === 0) {
      container.style.display = "none";
      if (statItem) statItem.style.display = "";
      return;
    }

    function createItem(guild) {
      const item = document.createElement("div");
      item.className = "marquee-item";
      if (guild.icon) {
        const img = document.createElement("img");
        img.src = guild.icon;
        img.alt = guild.name;
        img.loading = "lazy";
        item.appendChild(img);
      } else {
        const fallback = document.createElement("div");
        fallback.className = "marquee-fallback";
        fallback.textContent = guild.name.charAt(0).toUpperCase();
        item.appendChild(fallback);
      }
      const span = document.createElement("span");
      span.textContent = guild.name;
      item.appendChild(span);
      return item;
    }

    const items = guilds.map(createItem);

    if (statItem) statItem.style.display = "none";
    container.style.display = "";

    if (guilds.length < 5) {
      container.classList.add("grid");
      rightTrack.append(...items);
      leftTrack.style.display = "none";
      return;
    }

    // 3 copies for seamless overlap (portfolio technique)
    const dupRight1 = items.map((item) => item.cloneNode(true));
    const dupRight2 = items.map((item) => item.cloneNode(true));
    rightTrack.append(...items, ...dupRight1, ...dupRight2);

    const reversed = guilds.map(createItem).reverse();
    const dupLeft1 = reversed.map((item) => item.cloneNode(true));
    const dupLeft2 = reversed.map((item) => item.cloneNode(true));
    leftTrack.append(...reversed, ...dupLeft1, ...dupLeft2);

    // RAF-driven marquee — no CSS keyframes, no reset snap
    const DURATION = Math.max(40000, Math.min(120000, guilds.length * 3000));
    const DISTANCE = 100 / 3;

    let paused = false;
    let rafId = null;
    let lastTime = 0;
    let elapsed = 0;

    function tick(now) {
      if (lastTime && !paused) {
        elapsed += now - lastTime;
        const pct = (elapsed % (DURATION * 3)) / (DURATION * 3) * 100;
        const r = -(pct / 3);
        const l = -(DISTANCE) + (pct / 3);
        rightTrack.style.transform = "translateX(" + r + "%)";
        leftTrack.style.transform = "translateX(" + l + "%)";
      }
      lastTime = now;
      rafId = requestAnimationFrame(tick);
    }

    rafId = requestAnimationFrame(tick);

    function onEnter() { paused = true; }
    function onLeave() { paused = false; }
    container.addEventListener("mouseenter", onEnter);
    container.addEventListener("mouseleave", onLeave);

    // Store cleanup on container
    container._marqueeCleanup = function () {
      if (rafId) cancelAnimationFrame(rafId);
      container.removeEventListener("mouseenter", onEnter);
      container.removeEventListener("mouseleave", onLeave);
    };
  }

  // ── Fetch stats from API ──
  async function loadStats() {
    try {
      const res = await fetch("/api/stats");
      if (!res.ok) return;
      const data = await res.json();
      const membersEl = document.getElementById("stat-members");
      if (membersEl && data.members !== undefined)
        membersEl.textContent = data.members.toLocaleString("id-ID");
      renderMarquee(data.guilds_list);
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
