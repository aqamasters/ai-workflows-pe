(() => {
  "use strict";

  const navToggle = document.querySelector(".nav-toggle");
  const primaryNavigation = document.querySelector("#primary-navigation");
  const closeNavigation = () => {
    if (!navToggle || !primaryNavigation) return;
    navToggle.setAttribute("aria-expanded", "false");
    primaryNavigation.classList.remove("is-open");
  };
  if (navToggle && primaryNavigation) {
    navToggle.addEventListener("click", () => {
      const shouldOpen = navToggle.getAttribute("aria-expanded") !== "true";
      navToggle.setAttribute("aria-expanded", String(shouldOpen));
      primaryNavigation.classList.toggle("is-open", shouldOpen);
    });
    primaryNavigation.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", closeNavigation);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeNavigation();
        navToggle.focus();
      }
    });
    window.matchMedia("(min-width: 761px)").addEventListener("change", closeNavigation);
  }

  const providerDefaults = {
    openai: "gpt-5.6-sol",
    anthropic: "claude-sonnet-5",
    google: "gemini-3.5-flash",
    compatible: "local-model",
    fake: "deterministic-demo-v1"
  };
  document.querySelectorAll("[data-ai-profile-form]").forEach((form) => {
    const provider = form.querySelector("[data-profile-provider]");
    const model = form.querySelector("[data-profile-model]");
    const compatibleField = form.querySelector(".compatible-only");
    const credentialField = form.querySelector(".credential-only");
    const keyOptional = form.querySelector("[data-key-optional]");
    const refreshProfileForm = (providerChanged = false) => {
      const selected = provider.value;
      if (providerChanged && model && !model.dataset.edited) {
        model.value = providerDefaults[selected];
      }
      if (compatibleField) compatibleField.hidden = selected !== "compatible";
      if (credentialField) credentialField.hidden = selected === "fake";
      if (keyOptional) {
        keyOptional.textContent = selected === "compatible" ? "optional" : "";
        keyOptional.hidden = selected !== "compatible";
      }
    };
    provider.addEventListener("change", () => refreshProfileForm(true));
    if (model) model.addEventListener("input", () => { model.dataset.edited = "true"; });
    refreshProfileForm();
  });

  const aiProfileSelect = document.querySelector("#ai-profile-select");
  const modelSummary = document.querySelector(".model-configured");
  const refreshModelSummary = () => {
    if (!aiProfileSelect || !modelSummary) return;
    const selected = aiProfileSelect.selectedOptions[0];
    if (!selected) return;
    modelSummary.querySelector("[data-model-label]").textContent = selected.dataset.label;
    modelSummary.querySelector("[data-model-provider]").textContent = selected.dataset.provider;
    modelSummary.querySelector("[data-model-id]").textContent = selected.dataset.model;
    modelSummary.querySelector("[data-model-destination]").textContent = selected.dataset.destination;
    modelSummary.querySelector("[data-model-credential]").textContent = selected.dataset.credential;
  };
  if (aiProfileSelect) aiProfileSelect.addEventListener("change", refreshModelSummary);
  refreshModelSummary();

  const approvalProfileSelect = document.querySelector("#approval-profile-select");
  const approvalDestination = document.querySelector("[data-approval-destination]");
  const approvalCredential = document.querySelector("[data-approval-credential]");
  const refreshApprovalProfile = () => {
    if (!approvalProfileSelect) return;
    const selected = approvalProfileSelect.selectedOptions[0];
    if (!selected) return;
    if (approvalDestination) {
      approvalDestination.textContent = `${selected.dataset.provider} · ${selected.dataset.model}`;
    }
    if (approvalCredential) approvalCredential.textContent = selected.dataset.credential;
  };
  if (approvalProfileSelect) {
    approvalProfileSelect.addEventListener("change", refreshApprovalProfile);
  }
  refreshApprovalProfile();

  const progress = document.querySelector("[data-progress-url]");
  if (progress) {
    const progressTrack = document.querySelector("[role='progressbar']");
    const progressBar = document.querySelector("#progress-bar");
    if (progressTrack && progressBar) {
      progressBar.style.width = `${progressTrack.getAttribute("aria-valuenow") || 0}%`;
    }
    const poll = async () => {
      try {
        const response = await fetch(progress.dataset.progressUrl, { credentials: "same-origin" });
        const data = await response.json();
        document.querySelector("#progress-message").textContent = data.message;
        document.querySelector("#progress-percent").textContent = `${data.progress}%`;
        document.querySelector("#progress-status").textContent = data.status;
        if (progressTrack && progressBar) {
          progressBar.style.width = `${data.progress}%`;
          progressTrack.setAttribute("aria-valuenow", data.progress);
        }
        if (data.next_url) {
          window.location.assign(data.next_url);
          return;
        }
        if (data.status === "failed") {
          const error = document.querySelector("#progress-error");
          error.textContent = data.error || "The review stopped. Return to the home page and retry.";
          error.hidden = false;
          document.querySelector("#progress-detail").textContent = "No source code was executed or sent after the failure point.";
          return;
        }
        window.setTimeout(poll, 900);
      } catch (error) {
        window.setTimeout(poll, 1800);
      }
    };
    poll();
  }

  const tabs = Array.from(document.querySelectorAll("[data-tab]"));
  const assessmentSections = document.querySelector("#assessment-sections");
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const scrollToAssessmentStart = (panel) => {
    if (!assessmentSections || !panel) return;
    window.requestAnimationFrame(() => {
      const stickyTop = Number.parseFloat(window.getComputedStyle(assessmentSections).top) || 0;
      const tabStyles = window.getComputedStyle(assessmentSections);
      const panelTop = panel.getBoundingClientRect().top + window.scrollY;
      const panelOffset = stickyTop + assessmentSections.offsetHeight
        + (Number.parseFloat(tabStyles.marginBottom) || 0);
      window.scrollTo({
        top: Math.max(0, panelTop - panelOffset),
        behavior: prefersReducedMotion.matches ? "auto" : "smooth"
      });
    });
  };
  const activateTab = (tab, moveFocus = false, resetScroll = true) => {
    tabs.forEach((candidate) => {
      const active = candidate === tab;
      candidate.classList.toggle("active", active);
      candidate.setAttribute("aria-selected", String(active));
      candidate.tabIndex = active ? 0 : -1;
    });
    let activePanel;
    document.querySelectorAll("[data-panel]").forEach((panel) => {
      const active = panel.dataset.panel === tab.dataset.tab;
      panel.classList.toggle("active", active);
      panel.hidden = !active;
      if (active) activePanel = panel;
    });
    if (moveFocus) tab.focus({ preventScroll: true });
    if (resetScroll) scrollToAssessmentStart(activePanel);
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateTab(tab));
    tab.addEventListener("keydown", (event) => {
      let nextIndex;
      if (event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = tabs.length - 1;
      if (nextIndex === undefined) return;
      event.preventDefault();
      activateTab(tabs[nextIndex], true);
    });
  });

  if (window.location.hash && window.location.hash.startsWith("#E")) {
    const evidenceTab = document.querySelector('[data-tab="evidence"]');
    if (evidenceTab) {
      activateTab(evidenceTab, false, false);
      window.setTimeout(() => {
        const target = document.querySelector(window.location.hash);
        if (target) { target.open = true; target.scrollIntoView(); }
      }, 0);
    }
  }
})();
