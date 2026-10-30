const navToggle = document.querySelector(".nav-toggle");
const siteNav = document.querySelector(".site-nav");

if (navToggle && siteNav) {
  navToggle.addEventListener("click", () => {
    const isOpen = navToggle.getAttribute("aria-expanded") === "true";
    navToggle.setAttribute("aria-expanded", String(!isOpen));
    siteNav.classList.toggle("is-open", !isOpen);
  });

  siteNav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      navToggle.setAttribute("aria-expanded", "false");
      siteNav.classList.remove("is-open");
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && navToggle.getAttribute("aria-expanded") === "true") {
      navToggle.setAttribute("aria-expanded", "false");
      siteNav.classList.remove("is-open");
      navToggle.focus();
    }
  });
}

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    const text = button.dataset.copy;
    const feedback = document.querySelector(
      button.closest(".install-panel") ? ".install-note" : ".copy-feedback",
    );

    try {
      await navigator.clipboard.writeText(text);
      if (feedback) feedback.textContent = "Copied to clipboard.";
    } catch {
      if (feedback) feedback.textContent = "Copy unavailable — select and copy the command manually.";
    }
  });
});
