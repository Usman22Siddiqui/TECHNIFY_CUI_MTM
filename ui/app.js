/* Mind to Machine — Offline UI interactions (F1, F5, F6, F10) */
(function () {
  "use strict";

  const dataEl = document.getElementById("mtm-data");
  if (!dataEl) return;

  const DATA = JSON.parse(dataEl.textContent || "{}");
  const I18N = DATA.i18n || { en: {}, ur: {} };
  const PLAN = DATA.plan || {};
  const TRACE_TEXT = DATA.trace_text || "";

  const URDU_DIGITS = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];

  let currentLang = localStorage.getItem("mtm_lang") || "en";
  let lakhMode = localStorage.getItem("mtm_lakh") === "1";
  let urduDigits = localStorage.getItem("mtm_urdu_digits") === "1";

  function toUrduDigits(str) {
    return String(str).replace(/[0-9]/g, function (d) {
      return URDU_DIGITS[Number(d)];
    });
  }

  function formatIntLakh(n) {
    const neg = n < 0;
    const s = String(Math.abs(Math.round(n)));
    if (s.length <= 3) return (neg ? "-" : "") + s;
    const last3 = s.slice(-3);
    let rest = s.slice(0, -3);
    const groups = [];
    while (rest.length > 2) {
      groups.unshift(rest.slice(-2));
      rest = rest.slice(0, -2);
    }
    if (rest.length > 0) groups.unshift(rest);
    return (neg ? "-" : "") + groups.join(",") + "," + last3;
  }

  function formatIntIntl(n) {
    return Math.round(n).toLocaleString("en-US");
  }

  function formatCurrency(val) {
    if (val === null || val === undefined || val === "unknown" || isNaN(Number(val))) {
      return (I18N[currentLang] && I18N[currentLang].unknown) || "Unknown";
    }
    const num = Number(val);
    const unit = (I18N[currentLang] && I18N[currentLang].rupees) || "Rs";
    let formatted = lakhMode ? formatIntLakh(num) : formatIntIntl(num);
    if (lakhMode && Math.abs(num) >= 100000) {
      const lakhVal = (num / 100000).toFixed(2).replace(/\.?0+$/, "");
      formatted += " (" + lakhVal + " lakh)";
    }
    let out = unit + " " + formatted;
    if (currentLang === "ur" && urduDigits) {
      out = toUrduDigits(out);
    }
    return out;
  }

  function formatNum(val) {
    if (val === null || val === undefined || val === "unknown") {
      return (I18N[currentLang] && I18N[currentLang].unknown) || "Unknown";
    }
    let out = String(val);
    if (currentLang === "ur" && urduDigits) {
      out = toUrduDigits(out);
    }
    return out;
  }

  function applyLanguage(lang) {
    currentLang = lang === "ur" ? "ur" : "en";
    localStorage.setItem("mtm_lang", currentLang);

    const dict = I18N[currentLang] || I18N.en;
    document.documentElement.lang = currentLang;
    document.documentElement.dir = currentLang === "ur" ? "rtl" : "ltr";

    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      const key = el.getAttribute("data-i18n");
      if (dict[key]) {
        el.textContent = dict[key];
      }
    });

    document.querySelectorAll(".lang-btn").forEach(function (btn) {
      const active = btn.getAttribute("data-lang") === currentLang;
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });

    refreshNumbers();
  }

  function refreshNumbers() {
    document.querySelectorAll("[data-rs]").forEach(function (el) {
      el.textContent = formatCurrency(el.getAttribute("data-rs"));
    });
    document.querySelectorAll("[data-num]").forEach(function (el) {
      el.textContent = formatNum(el.getAttribute("data-num"));
    });
  }

  function buildWhatsAppText() {
    const t = I18N[currentLang] || I18N.en;
    const j = PLAN.judging || {};
    const h = PLAN.headcount || {};
    const v = PLAN.venue || {};
    const f = PLAN.food || {};
    const s = PLAN.schedule || {};
    const b = PLAN.budget || {};

    const lines = [];
    lines.push("*" + (t.page_heading || "Event plan") + "*");
    lines.push(
      (t.students || "Students") + ": " + formatNum(h.students) +
      " | " + (t.teams || "Teams") + ": " + formatNum(j.teams) +
      " | " + (t.headcount || "Headcount") + ": " + formatNum(h.total)
    );
    lines.push("");
    lines.push("*" + (t.venue || "Venue") + "*: " + (v.selected || t.unknown) + " (" + formatCurrency(v.cost) + ")");
    lines.push(
      "*" + (t.food || "Food") + "*: " + (f.tier || t.unknown) +
      " — " + formatNum(f.quantity) + " " + (t.boxes || "boxes") +
      " (" + formatCurrency(f.cost) + ")"
    );
    lines.push(
      "*" + (t.judging || "Judging") + "*: " + formatNum(j.judges_used) + "/" + formatNum(j.judges_confirmed) +
      " (" + formatCurrency(j.cost) + ")"
    );
    lines.push(
      "*" + (t.budget || "Budget") + "*: " +
      (t.spent || "Spent") + " " + formatCurrency(b.spent) +
      " / " + formatCurrency(b.budget_total) +
      " | " + (t.remaining || "Remaining") + " " + formatCurrency(b.remaining)
    );

    if (s.blocks && s.blocks.length) {
      lines.push("");
      lines.push("*" + (t.schedule || "Schedule") + "* (" + formatNum(s.duration_min) + " " + (t.minutes || "min") + "):");
      s.blocks.forEach(function (blk) {
        const label = t[blk.name] || blk.name;
        lines.push("• " + blk.start_label + "–" + blk.end_label + " " + label + " (" + formatNum(blk.minutes) + " " + (t.minutes || "min") + ")");
      });
    }
    return lines.join("\n");
  }

  // Bind language switch
  document.querySelectorAll(".lang-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      applyLanguage(btn.getAttribute("data-lang"));
    });
  });

  // Bind lakh grouping toggle
  const lakhCheckbox = document.getElementById("toggle-lakh");
  if (lakhCheckbox) {
    lakhCheckbox.checked = lakhMode;
    lakhCheckbox.addEventListener("change", function () {
      lakhMode = Boolean(lakhCheckbox.checked);
      localStorage.setItem("mtm_lakh", lakhMode ? "1" : "0");
      refreshNumbers();
    });
  }

  // Bind Urdu digits toggle
  const urduDigitsCheckbox = document.getElementById("toggle-urdu-digits");
  if (urduDigitsCheckbox) {
    urduDigitsCheckbox.checked = urduDigits;
    urduDigitsCheckbox.addEventListener("change", function () {
      urduDigits = Boolean(urduDigitsCheckbox.checked);
      localStorage.setItem("mtm_urdu_digits", urduDigits ? "1" : "0");
      refreshNumbers();
    });
  }

  // Bind WhatsApp copy button
  const waBtn = document.getElementById("btn-whatsapp");
  if (waBtn) {
    waBtn.addEventListener("click", function () {
      const text = buildWhatsAppText();
      const labelEl = waBtn.querySelector("[data-i18n]");
      const dict = I18N[currentLang] || I18N.en;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
          if (labelEl && dict.copied_whatsapp) {
            labelEl.textContent = dict.copied_whatsapp;
            setTimeout(function () {
              labelEl.textContent = dict.copy_whatsapp;
            }, 1800);
          }
        });
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
    });
  }

  // Bind offline trace download button
  const dlBtn = document.getElementById("btn-download-trace");
  if (dlBtn) {
    dlBtn.addEventListener("click", function () {
      const blob = new Blob([TRACE_TEXT], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "trace.txt";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  }

  // Bind print button
  const printBtn = document.getElementById("btn-print");
  if (printBtn) {
    printBtn.addEventListener("click", function () {
      window.print();
    });
  }

  // One motion moment: stagger trace lines across ~1.2s on first load
  const traceLines = document.querySelectorAll(".trace-line");
  if (traceLines.length > 0) {
    const step = Math.min(80, Math.floor(1200 / traceLines.length));
    traceLines.forEach(function (el, idx) {
      el.style.animationDelay = idx * step + "ms";
    });
  }

  applyLanguage(currentLang);
})();
