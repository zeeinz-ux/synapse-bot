/**
 * dashboard.js — Hidden Hamlet Dashboard Logic
 * Features: auto-refresh countdown, artwork fallback, progress bar animation
 */

document.addEventListener("DOMContentLoaded", () => {
  // ── 1. Auto-refresh countdown ──
  let countdown = 10;
  const metaEl = document.querySelector(".dash-meta");

  if (metaEl) {
    const originalText = metaEl.textContent;
    const timer = setInterval(() => {
      countdown--;
      if (countdown <= 0) {
        clearInterval(timer);
        window.location.reload();
      } else {
        metaEl.textContent = originalText.replace(
          /Auto-refresh \d+s/,
          `Auto-refresh ${countdown}s`,
        );
      }
    }, 1000);
  }

  // ── 2. Artwork fallback on error ──
  document.querySelectorAll(".p-art").forEach((img) => {
    img.addEventListener("error", function () {
      const fallback = this.dataset.fallback;
      if (fallback && this.src !== fallback) {
        this.src = fallback;
      }
    });
  });

  // ── 3. Animate progress bars ──
  document.querySelectorAll(".bar-fill").forEach((bar) => {
    const progress = bar.dataset.progress || 0;
    // Small delay for smooth animation
    requestAnimationFrame(() => {
      bar.style.setProperty("--progress", progress + "%");
    });
  });

  console.log("[DASHBOARD] ✅ Dashboard JS loaded and initialized");
});
