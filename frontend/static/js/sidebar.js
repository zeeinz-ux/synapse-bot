/* ============================================
   SIDEBAR JS — Hidden Hamlet Dashboard
   ============================================ */

(function () {
  "use strict";

  const sidebar = document.getElementById("sidebar");
  const sidebarToggle = document.getElementById("sidebarToggle");
  const mobileMenuBtn = document.getElementById("mobileMenuBtn");
  const sidebarOverlay = document.getElementById("sidebarOverlay");
  const moduleSearch = document.getElementById("moduleSearch");
  const guildDropdown = document.getElementById("guildDropdown");
  const mobileGuildDropdown = document.getElementById("mobileGuildDropdown");

  // --- Toggle icon SVGs ---
  const ICON_COLLAPSE = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>`;
  const ICON_EXPAND = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"></polyline></svg>`;

  // --- State ---
  let isCollapsed = localStorage.getItem("sidebarCollapsed") === "true";

  // --- Apply state ---
  function applySidebarState() {
    if (!sidebar) return;
    if (isCollapsed) {
      sidebar.classList.add("collapsed");
    } else {
      sidebar.classList.remove("collapsed");
    }
    updateToggleIcon();
  }

  function updateToggleIcon() {
    if (!sidebarToggle) return;
    sidebarToggle.innerHTML = isCollapsed ? ICON_EXPAND : ICON_COLLAPSE;
    sidebarToggle.setAttribute(
      "aria-label",
      isCollapsed ? "Expand sidebar" : "Collapse sidebar",
    );
  }

  // --- Toggle desktop sidebar ---
  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", function () {
      isCollapsed = !isCollapsed;
      localStorage.setItem("sidebarCollapsed", isCollapsed);
      applySidebarState();
    });
  }

  // --- Mobile menu ---
  if (mobileMenuBtn && sidebarOverlay) {
    mobileMenuBtn.addEventListener("click", function () {
      sidebar.classList.add("open");
      sidebarOverlay.classList.add("active");
      document.body.style.overflow = "hidden";
    });

    sidebarOverlay.addEventListener("click", function () {
      sidebar.classList.remove("open");
      sidebarOverlay.classList.remove("active");
      document.body.style.overflow = "";
    });
  }

  // --- Section collapse/expand ---
  document.querySelectorAll(".section-header").forEach(function (header) {
    header.addEventListener("click", function () {
      const section = header.closest(".nav-section");
      if (!section) return;
      section.classList.toggle("collapsed");
      const sectionName = section.dataset.section;
      const collapsedSections = JSON.parse(
        localStorage.getItem("collapsedSections") || "[]",
      );
      if (section.classList.contains("collapsed")) {
        if (!collapsedSections.includes(sectionName))
          collapsedSections.push(sectionName);
      } else {
        const idx = collapsedSections.indexOf(sectionName);
        if (idx > -1) collapsedSections.splice(idx, 1);
      }
      localStorage.setItem(
        "collapsedSections",
        JSON.stringify(collapsedSections),
      );
    });
  });

  // Restore section states
  (function restoreSections() {
    const collapsedSections = JSON.parse(
      localStorage.getItem("collapsedSections") || "[]",
    );
    document.querySelectorAll(".nav-section").forEach(function (section) {
      if (collapsedSections.includes(section.dataset.section)) {
        section.classList.add("collapsed");
      }
    });
  })();

  // --- Search (Ctrl+K) ---
  if (moduleSearch) {
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        moduleSearch.focus();
      }
    });

    moduleSearch.addEventListener("input", function () {
      const query = this.value.toLowerCase().trim();
      document.querySelectorAll(".nav-item").forEach(function (item) {
        const searchTerms = (item.dataset.search || "").toLowerCase();
        const label = item.querySelector(".nav-label");
        const text = label ? label.textContent.toLowerCase() : "";
        const match =
          !query || searchTerms.includes(query) || text.includes(query);
        item.style.display = match ? "flex" : "none";
      });

      document.querySelectorAll(".nav-section").forEach(function (section) {
        const visibleItems = section.querySelectorAll(
          '.nav-item[style="display: flex;"], .nav-item:not([style*="none"])',
        );
        const header = section.querySelector(".section-header");
        if (header)
          header.style.display = visibleItems.length > 0 ? "flex" : "none";
      });
    });
  }

  // --- Guild dropdown navigation ---
  function setupGuildDropdown(dropdown) {
    if (!dropdown) return;
    dropdown.addEventListener("change", function () {
      const newGuildId = this.value;
      const currentPath = window.location.pathname;
      const pathParts = currentPath.split("/").filter(Boolean);
      if (pathParts.length >= 2 && /^\d+$/.test(pathParts[1])) {
        pathParts[1] = newGuildId;
        window.location.href = "/" + pathParts.join("/");
      } else {
        window.location.href = "/dashboard/" + newGuildId + "/";
      }
    });
  }

  setupGuildDropdown(guildDropdown);
  setupGuildDropdown(mobileGuildDropdown);

  // --- Scroll active item into view ---
  (function () {
    const activeItem = document.querySelector(".nav-item.active");
    if (activeItem && sidebar) {
      activeItem.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  })();

  // --- Init ---
  applySidebarState();
})();
