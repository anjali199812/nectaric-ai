let positionChart = null;
const API_BASE =
  window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost"
    ? "http://127.0.0.1:8000"
    : "https://nectaric-ai.onrender.com";

// Autocomplete state
let suggestionIndex = -1;
let suggestionItems = [];
let autocompleteDebounce = null;


// -------------------------
// General helpers
// -------------------------
function showError(msg) {
  console.error(msg);
  const el = document.getElementById("errorBox");
  if (el) {
    el.textContent = msg;
    el.style.display = "block";
  }
}

function clearError() {
  const el = document.getElementById("errorBox");
  if (el) {
    el.textContent = "";
    el.style.display = "none";
  }
}

function fmtPct(x) {
  if (x === null || x === undefined || isNaN(x)) return "—";
  return (Number(x) * 100).toFixed(2) + "%";
}

function fmtNum(x) {
  if (x === null || x === undefined || isNaN(x)) return "—";
  return Number(x).toFixed(2);
}

function fmtPrice(x) {
  if (x === null || x === undefined || isNaN(x)) return "—";
  return "$" + Number(x).toFixed(2);
}


// -------------------------
// Badge helpers
// -------------------------
function badgeClassForRisk(risk) {
  if (!risk) return "badge-neutral";
  const r = String(risk).toLowerCase();
  if (r === "low") return "badge-green";
  if (r === "medium") return "badge-yellow";
  if (r === "high") return "badge-red";
  return "badge-neutral";
}

function badgeClassForSafety(safety) {
  if (!safety) return "badge-neutral";
  const s = String(safety).toLowerCase();
  if (s === "safe") return "badge-green";
  if (s === "cautious") return "badge-yellow";
  if (s === "unsafe") return "badge-red";
  return "badge-neutral";
}

function badgeClassForConviction(conviction) {
  if (!conviction) return "badge-neutral";
  const c = String(conviction).toLowerCase();
  if (c === "strong buy") return "badge-green";
  if (c === "buy") return "badge-blue";
  if (c === "watch") return "badge-yellow";
  if (c === "speculative" || c === "avoid") return "badge-red";
  return "badge-neutral";
}

function renderBadge(text, cls) {
  return `<span class="status-badge ${cls}">${text ?? "—"}</span>`;
}


// -------------------------
// Factor bar helper
// -------------------------
function renderBar(label, value) {
  const num = Number(value);
  const hasValue = Number.isFinite(num);
  const safeValue = hasValue ? Math.max(0, Math.min(num, 10)) : 0;
  const pct = safeValue * 10;

  return `
    <div class="factor-bar">
      <div class="factor-bar-header">
        <span>${label}</span>
        <span>${hasValue ? safeValue.toFixed(2) : "N/A"}/10</span>
      </div>
      <div class="factor-bar-track">
        <div class="factor-bar-fill" style="width:${pct}%"></div>
      </div>
    </div>
  `;
}


// -------------------------
// Autocomplete helpers
// -------------------------
function getCurrentSearchToken(fullText) {
  const parts = fullText.split(",");
  return parts[parts.length - 1].trim();
}

function replaceCurrentToken(fullText, replacement) {
  const parts = fullText.split(",");
  parts[parts.length - 1] = ` ${replacement}`;
  return parts
    .map((p, i) => (i === 0 ? p.trim() : p.trim()))
    .join(", ");
}

function hideSuggestions() {
  const box = document.getElementById("tickerSuggestions");
  if (!box) return;
  box.style.display = "none";
  box.innerHTML = "";
  suggestionItems = [];
  suggestionIndex = -1;
}

function renderSuggestions(results) {
  const box = document.getElementById("tickerSuggestions");
  if (!box) return;

  if (!results || results.length === 0) {
    hideSuggestions();
    return;
  }

  suggestionItems = results;
  suggestionIndex = -1;

  box.innerHTML = results
    .map(
      (item, idx) => `
      <div class="suggestion-item" data-index="${idx}">
        <div class="suggestion-symbol">${item.symbol}</div>
        <div class="suggestion-name">${item.name || ""}</div>
        <div class="suggestion-meta">${item.exchange || "Unknown exchange"}</div>
      </div>
    `
    )
    .join("");

  box.style.display = "block";

  box.querySelectorAll(".suggestion-item").forEach((el) => {
    el.addEventListener("click", () => {
      const idx = Number(el.dataset.index);
      selectSuggestion(idx);
    });
  });
}

function highlightSuggestion() {
  const box = document.getElementById("tickerSuggestions");
  if (!box) return;

  const nodes = box.querySelectorAll(".suggestion-item");
  nodes.forEach((n, idx) => {
    n.classList.toggle("active", idx === suggestionIndex);
  });
}

function selectSuggestion(index) {
  if (index < 0 || index >= suggestionItems.length) return;

  const input = document.getElementById("tickers");
  if (!input) return;

  const selected = suggestionItems[index];
  input.value = replaceCurrentToken(input.value, selected.symbol);
  hideSuggestions();
  input.focus();
}

async function fetchSuggestions(query) {
  if (!query || query.length < 2) {
    hideSuggestions();
    return;
  }

  try {
    const resp = await fetch(
      `${API_BASE}/api/search_symbols?query=${encodeURIComponent(query)}&max_results=8`
    );
    if (!resp.ok) {
      hideSuggestions();
      return;
    }

    const data = await resp.json();
    renderSuggestions(data.results || []);
  } catch (err) {
    console.error("Suggestion fetch failed:", err);
    hideSuggestions();
  }
}


// -------------------------
// Signal card helpers (NEW)
// -------------------------
function signalDecisionColor(decision) {
  if (decision === "BUY")  return "#22c55e";
  if (decision === "HOLD") return "#3b82f6";
  return "#6b7280";
}

function renderSignalRow(label, value, valueColor) {
  if (value === null || value === undefined) return "";
  return `
    <div style="display:flex;justify-content:space-between;align-items:center;
                padding:6px 0;border-bottom:1px solid #1f2937;">
      <span style="color:#9ca3af;font-size:12px;">${label}</span>
      <span style="color:${valueColor || "#e2e8f0"};font-weight:600;font-size:13px;">${value}</span>
    </div>`;
}

function renderSignalCard(signal, label) {
  if (!signal) return "";

  const dec   = signal.decision || "NO POSITION";
  const color = signalDecisionColor(dec);
  const isActive = dec === "BUY" || dec === "HOLD";

  const rows = isActive
    ? `
      ${renderSignalRow("Entry Price",    fmtPrice(signal.entry_price),  "#e2e8f0")}
      ${renderSignalRow("Stop Loss",      fmtPrice(signal.stop_loss),    "#ef4444")}
      ${renderSignalRow("Target Price",   fmtPrice(signal.target_price), "#22c55e")}
      ${renderSignalRow("Risk / Reward",  signal.risk_reward_ratio ? "1 : " + fmtNum(signal.risk_reward_ratio) : "—", "#e2e8f0")}
      ${renderSignalRow("Max Loss",       signal.max_loss_pct       ? "-" + fmtNum(signal.max_loss_pct) + "%" : "—", "#ef4444")}
      ${renderSignalRow("Potential Gain", signal.potential_gain_pct ? "+" + fmtNum(signal.potential_gain_pct) + "%" : "—", "#22c55e")}
    `
    : `<div style="text-align:center;padding:12px 0;color:#6b7280;font-size:12px;font-style:italic;">
         No active trade signal — model probability below buy threshold
       </div>`;

  return `
    <div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;
                padding:14px;margin-bottom:12px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="font-size:12px;font-weight:700;color:#94a3b8;letter-spacing:0.06em;">${label}</span>
        <span style="padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;
                     background:${color}22;color:${color};border:1px solid ${color}55;">${dec}</span>
      </div>
      <div style="font-size:11px;color:#64748b;margin-bottom:8px;">${signal.duration || ""}</div>
      <div style="font-size:12px;margin-bottom:8px;">
        <span style="color:#9ca3af;">P(Up) </span>
        <strong style="color:#e2e8f0;">${signal.probability_up ?? "—"}%</strong>
        <span style="color:#475569;margin:0 6px;">|</span>
        <span style="color:#9ca3af;">ATR </span>
        <strong style="color:#e2e8f0;">${fmtPrice(signal.atr_14)}</strong>
      </div>
      ${rows}
      <div style="margin-top:10px;padding-top:8px;border-top:1px solid #1f2937;
                  font-size:11px;color:#475569;">
        Backtest: <strong style="color:#94a3b8;">${fmtPct(signal.annual_return)}</strong> ann. return
        &nbsp;|&nbsp; Sharpe <strong style="color:#94a3b8;">${fmtNum(signal.sharpe)}</strong>
      </div>
    </div>
  `;
}

async function fetchAndRenderSignals(ticker) {
  const section = document.getElementById("signalsSection");
  if (!section) return;

  section.innerHTML = `
    <p style="color:#64748b;font-size:12px;font-style:italic;">Loading trade signals...</p>`;

  try {
    const resp = await fetch(
      `${API_BASE}/api/actionable_signals?ticker=${encodeURIComponent(ticker)}`
    );
    if (!resp.ok) throw new Error("HTTP " + resp.status);

    const data = await resp.json();

    section.innerHTML = `
      <hr style="margin:14px 0;border-color:#1f2937;" />
      <p style="font-size:13px;font-weight:700;color:#94a3b8;
                letter-spacing:0.06em;margin-bottom:10px;">TRADE SIGNALS</p>
      ${renderSignalCard(data.short_term, "SHORT-TERM")}
      ${renderSignalCard(data.long_term,  "LONG-TERM")}
    `;
  } catch (err) {
    section.innerHTML = `
      <p style="color:#ef4444;font-size:12px;">Could not load signals: ${err.message}</p>`;
  }
}


// -------------------------
// Table / details rendering
// -------------------------
function renderComparisonTable(rows) {
  const tbody = document.getElementById("comparisonBody");
  if (!tbody) return;

  tbody.innerHTML = "";

  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.classList.add("clickable-row");
    tr.dataset.ticker = row.ticker;

    tr.innerHTML = `
      <td>
        <div><strong>${row.ticker}</strong></div>
        <div style="font-size:11px;color:#9ca3af;">${row.resolved_name || row.input_query || ""}</div>
      </td>
      <td>${row.decision_today || "—"}</td>
      <td>${fmtNum(row.price_today)}</td>
      <td>${fmtPct(row.proba_pos_move)}</td>
      <td>${fmtPct(row.last_10d_actual)}</td>
      <td>${fmtPct(row.annual_return)}</td>
      <td>${fmtNum(row.sharpe)}</td>
      <td>${fmtPct(row.cum_return)}</td>
      <td>${renderBadge(row.valuation_status || "—", badgeClassForConviction(row.valuation_status))}</td>
      <td>${renderBadge(row.risk_level || "—", badgeClassForRisk(row.risk_level))}</td>
      <td>${renderBadge(row.buy_safety || "—", badgeClassForSafety(row.buy_safety))}</td>
      <td>${row.nectaric_score ?? "—"}</td>
    `;

    tr.addEventListener("click", () => selectTicker(row));
    tbody.appendChild(tr);
  });
}

function clearDetails() {
  const details = document.getElementById("tickerDetails");
  if (details) {
    details.innerHTML = `<p>Select a row in the comparison table to see full details here.</p>`;
  }

  if (positionChart) {
    positionChart.destroy();
    positionChart = null;
  }
}

function selectTicker(row, horizonOverride) {
  const details = document.getElementById("tickerDetails");
  if (!details) return;

  const proba   = row.proba_pos_move ?? null;
  const horizon = horizonOverride || row.horizon || 10;

  const factor       = row.factor_model || {};
  const factors      = factor.factors || {};
  const finalScore   = factor.final_score ?? row.nectaric_score ?? "—";
  const conviction   = factor.conviction  || row.valuation_status || "—";
  const riskLevel    = row.risk_level     || factor.risk_level    || "—";
  const buySafety    = row.buy_safety     || factor.buy_safety    || "—";
  const interpretation = factor.interpretation || "—";
  const bestFactor   = factor.best_factor?.name    || "—";
  const weakestFactor = factor.weakest_factor?.name || "—";
  const resolvedName = row.resolved_name || row.input_query || row.ticker;
  const resolvedExchange = row.resolved_exchange || "—";

  details.innerHTML = `
    <h3>${row.ticker}</h3>
    <p style="color:#9ca3af;margin-top:-4px;">${resolvedName}</p>
    <p><strong>Exchange:</strong> ${resolvedExchange}</p>
    <p><strong>Decision:</strong> ${row.decision_today || "—"}</p>
    <p><strong>Price:</strong> $${fmtNum(row.price_today)}</p>
    <p><strong>Horizon:</strong> ${horizon} days</p>
    <p><strong>P(Up in horizon):</strong> ${fmtPct(proba)}</p>
    <p><strong>Last ${horizon}d actual move:</strong> ${fmtPct(row.last_10d_actual)}</p>
    <p><strong>Annual return (strategy):</strong> ${fmtPct(row.annual_return)}</p>
    <p><strong>Sharpe:</strong> ${fmtNum(row.sharpe)}</p>
    <p><strong>Cumulative return (strategy):</strong> ${fmtPct(row.cum_return)}</p>

    <hr style="margin:12px 0;border-color:#1f2937;" />

    <p><strong>Final Score:</strong> ${fmtNum(finalScore)}/10</p>
    <p><strong>Conviction:</strong> ${renderBadge(conviction, badgeClassForConviction(conviction))}</p>
    <p><strong>Risk Level:</strong> ${renderBadge(riskLevel, badgeClassForRisk(riskLevel))}</p>
    <p><strong>Buy Safety:</strong> ${renderBadge(buySafety, badgeClassForSafety(buySafety))}</p>

    <div style="margin-top:10px;padding:10px 12px;border:1px solid #1f2937;
                border-radius:10px;background:#020617;">
      <p style="margin:0 0 4px;"><strong>Interpretation</strong></p>
      <p style="margin:0;color:#cbd5e1;">${interpretation}</p>
    </div>

    <p style="margin-top:12px;"><strong>Best Factor:</strong> ${bestFactor}</p>
    <p><strong>Weakest Factor:</strong> ${weakestFactor}</p>

    <div style="margin-top:10px;">
      <p><strong>Factor Breakdown</strong></p>
      ${renderBar("Quality",  factors.quality)}
      ${renderBar("Growth",   factors.growth)}
      ${renderBar("Value",    factors.value)}
      ${renderBar("Momentum", factors.momentum)}
      ${renderBar("Risk",     factors.risk)}
    </div>

    <div id="signalsSection" style="margin-top:4px;"></div>
  `;

  // Fetch and render short-term + long-term trade signals
  fetchAndRenderSignals(row.ticker);

  // Pie chart
  if (proba !== null && proba !== undefined && !isNaN(proba)) {
    const up    = Number(proba) * 100;
    const notUp = 100 - up;

    const canvas = document.getElementById("positionPie");
    if (!canvas) return;

    const ctx = canvas.getContext("2d");

    if (positionChart) {
      positionChart.destroy();
    }

    positionChart = new Chart(ctx, {
      type: "pie",
      data: {
        labels: ["Chance price UP", "Chance flat / down"],
        datasets: [{ data: [up, notUp] }],
      },
      options: {
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.label}: ${ctx.parsed.toFixed(1)}%`,
            },
          },
        },
      },
    });
  } else {
    if (positionChart) {
      positionChart.destroy();
      positionChart = null;
    }
  }
}


// -------------------------
// API / health / main action
// -------------------------
async function checkHealth() {
  const el = document.getElementById("apiStatus");
  if (!el) return;

  try {
    const resp = await fetch(`${API_BASE}/health`);
    if (!resp.ok) throw new Error("Health check failed");

    el.textContent = "API: healthy";
    el.classList.remove("badge-danger");
    el.classList.add("badge-success");
  } catch {
    el.textContent = "API: error";
    el.classList.remove("badge-success");
    el.classList.add("badge-danger");
  }
}

async function runSnapshot(evt) {
  evt.preventDefault();
  clearError();

  const tickersStr = document.getElementById("tickers")?.value || "";
  const start      = document.getElementById("start")?.value   || "2015-01-01";
  const horizon    = document.getElementById("horizon")?.value || 10;
  const buy        = document.getElementById("buy_thresh")?.value  || 0.6;
  const sell       = document.getElementById("sell_thresh")?.value || 0.4;

  const params = new URLSearchParams({
    tickers: tickersStr,
    start,
    horizon,
    buy_thresh:  buy,
    sell_thresh: sell,
  });

  const btn = document.getElementById("runBtn");
  if (btn) {
    btn.disabled     = true;
    btn.textContent  = "Running…";
  }

  try {
    const resp = await fetch(`${API_BASE}/api/compare?${params.toString()}`);
    if (!resp.ok) {
      const text = await resp.text();
      showError(`API error (${resp.status}): ${text}`);
      return;
    }

    const raw = await resp.json();
    console.log("compare response:", raw);

    let rows;
    if (Array.isArray(raw)) {
      rows = raw;
    } else if (Array.isArray(raw.results)) {
      rows = raw.results;
    } else {
      showError("Unexpected response from /api/compare");
      return;
    }

    const clean = rows.filter((row) => !row.error);

    renderComparisonTable(clean);

    if (clean.length === 1) {
      selectTicker(clean[0], raw.horizon_days || Number(horizon));
    } else if (clean.length > 1) {
      clearDetails();
    } else {
      clearDetails();
      const errors = rows
        .filter((r) => r.error)
        .map((r) => `${r.ticker || r.input_query}: ${r.error}`)
        .join(" | ");
      showError(errors || "No valid tickers returned.");
    }
  } catch (err) {
    console.error(err);
    showError("Failed to call /api/compare.");
  } finally {
    if (btn) {
      btn.disabled    = false;
      btn.textContent = "▶ Run Snapshot";
    }
  }
}


// -------------------------
// Init
// -------------------------
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("snapshotForm");
  if (form) {
    form.addEventListener("submit", runSnapshot);
  }

  const tickerInput    = document.getElementById("tickers");
  const suggestionsBox = document.getElementById("tickerSuggestions");

  if (tickerInput && suggestionsBox) {
    tickerInput.addEventListener("input", () => {
      const token = getCurrentSearchToken(tickerInput.value);
      clearTimeout(autocompleteDebounce);
      autocompleteDebounce = setTimeout(() => {
        fetchSuggestions(token);
      }, 250);
    });

    tickerInput.addEventListener("keydown", (e) => {
      if (!suggestionItems.length) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        suggestionIndex = Math.min(suggestionIndex + 1, suggestionItems.length - 1);
        highlightSuggestion();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        suggestionIndex = Math.max(suggestionIndex - 1, 0);
        highlightSuggestion();
      } else if (e.key === "Enter") {
        if (suggestionIndex >= 0) {
          e.preventDefault();
          selectSuggestion(suggestionIndex);
        }
      } else if (e.key === "Escape") {
        hideSuggestions();
      }
    });

    document.addEventListener("click", (e) => {
      if (!tickerInput.contains(e.target) && !suggestionsBox.contains(e.target)) {
        hideSuggestions();
      }
    });
  }

  checkHealth();
  clearDetails();
});
