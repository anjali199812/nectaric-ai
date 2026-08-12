let positionChart = null;
let decisionChart = null;
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

  // ── Tab switching ──────────────────────────────────────────────────────────
  const overviewEls  = [
    document.querySelector('.main-grid'),
    document.querySelector('.card-details'),
  ];
  const decisionEl   = document.getElementById('decisionSection');
  const dataSourceEl = document.querySelector('.data-sources');

  document.querySelectorAll('.nav-tabs .tab[data-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.nav-tabs .tab[data-tab]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const tab = btn.dataset.tab;
      if (tab === 'overview') {
        overviewEls.forEach(el => el && (el.style.display = ''));
        if (decisionEl) decisionEl.style.display = 'none';
        if (dataSourceEl) dataSourceEl.style.display = '';
      } else if (tab === 'decision') {
        overviewEls.forEach(el => el && (el.style.display = 'none'));
        if (decisionEl) decisionEl.style.display = 'block';
        if (dataSourceEl) dataSourceEl.style.display = 'none';
      }
    });
  });

  // ── Decision Engine form ───────────────────────────────────────────────────
  const decisionForm = document.getElementById('decisionForm');
  if (decisionForm) {
    decisionForm.addEventListener('submit', async (evt) => {
      evt.preventDefault();
      const ticker   = (document.getElementById('decisionTicker')?.value || '').trim().toUpperCase();
      const mode     = document.getElementById('decisionMode')?.value     || 'short';
      const duration = document.getElementById('decisionDuration')?.value || '1 to 3 months';
      const errBox   = document.getElementById('decisionError');
      const btn      = document.getElementById('decisionBtn');

      if (!ticker) { if (errBox) { errBox.textContent = 'Please enter a ticker.'; errBox.style.display = 'block'; } return; }
      if (errBox) errBox.style.display = 'none';
      if (btn)    { btn.disabled = true; btn.textContent = 'Analysing…'; }

      try {
        const resp = await fetch(
          `${API_BASE}/api/decision?ticker=${encodeURIComponent(ticker)}&mode=${mode}&duration=${encodeURIComponent(duration)}`
        );
        if (!resp.ok) {
          const txt = await resp.text();
          if (errBox) { errBox.textContent = `Error: ${txt}`; errBox.style.display = 'block'; }
          return;
        }
        const data = await resp.json();
        renderDecision(data);
      } catch (err) {
        if (errBox) { errBox.textContent = `Could not reach API: ${err.message}`; errBox.style.display = 'block'; }
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = '▶ Analyse Stock'; }
      }
    });
  }
});


// ── Decision Engine render ─────────────────────────────────────────────────────

function deIcon(status) {
  return status === '+' ? '✓' : status === '-' ? '✗' : status === '~' ? '~' : status === 'info' ? 'i' : '?';
}
function deStatusClass(status) {
  return status === '+' ? '#22c55e' : status === '-' ? '#ef4444' : status === '~' ? '#facc15' : '#94a3b8';
}

function renderDecision(d) {
  const R = document.getElementById('decisionResults');
  if (!R) return;
  R.innerHTML = '';
  let _pendingChart = null;

  const decColor = d.decision === 'BUY' ? '#22c55e' : d.decision === 'WATCH' ? '#facc15' : '#ef4444';
  const muted    = '#94a3b8';
  const surf     = '#0f172a';
  const border   = '#1f2937';

  // ── Stock header
  const pos = d.wk52_high === d.wk52_low ? 50
    : Math.round((d.price - d.wk52_low) / (d.wk52_high - d.wk52_low) * 100);
  R.innerHTML += `
  <div class="card" style="margin-bottom:14px">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px">
      <div>
        <div style="font-size:22px;font-weight:800;color:#f8fafc">${d.ticker}</div>
        <div style="font-size:13px;color:${muted}">${d.name}</div>
        <div style="font-size:11px;color:${muted};margin-top:2px">${d.sector} · Market Cap ${d.market_cap} · ${d.mode_label}</div>
      </div>
      <div style="text-align:right">
        <div style="font-size:28px;font-weight:800;color:#f8fafc">$${Number(d.price).toFixed(2)}</div>
        <div style="font-size:11px;color:${muted}">52wk ${d.wk52_low.toFixed(2)} – ${d.wk52_high.toFixed(2)}</div>
      </div>
    </div>
    <div style="margin-top:12px">
      <div style="display:flex;justify-content:space-between;font-size:10px;color:${muted};margin-bottom:4px">
        <span>52wk Low</span><span>52wk High</span>
      </div>
      <div style="position:relative;height:6px;background:${border};border-radius:999px;overflow:visible">
        <div style="position:absolute;left:0;top:0;height:100%;width:100%;background:linear-gradient(90deg,#0ea5e9,#22c55e);border-radius:999px;opacity:.3"></div>
        <div style="position:absolute;top:-3px;width:12px;height:12px;background:#f8fafc;border-radius:50%;left:calc(${pos}% - 6px);box-shadow:0 0 0 2px #0ea5e9"></div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px">
      <div><div style="font-size:10px;color:${muted};text-transform:uppercase;letter-spacing:.5px">Beta</div><div style="font-size:13px;font-weight:700;margin-top:3px">${d.beta}</div></div>
      <div><div style="font-size:10px;color:${muted};text-transform:uppercase;letter-spacing:.5px">Dividend</div><div style="font-size:13px;font-weight:700;margin-top:3px">${d.dividend_yield}</div></div>
      <div><div style="font-size:10px;color:${muted};text-transform:uppercase;letter-spacing:.5px">Holding Plan</div><div style="font-size:13px;font-weight:700;margin-top:3px">${d.holding_plan}</div></div>
      <div><div style="font-size:10px;color:${muted};text-transform:uppercase;letter-spacing:.5px">52wk Position</div><div style="font-size:12px;font-weight:600;margin-top:3px">${(d.wk52_position||'').split('—')[0].trim()}</div></div>
    </div>
  </div>`;

  // ── Price chart (HTML only — init after all mutations)
  if (d.chart_dates && d.chart_dates.length > 0) {
    const atLine = d.analyst_target
      ? `<span style="color:#d29922;font-size:11px">— — Analyst Target: <b>$${Number(d.analyst_target).toFixed(2)}</b></span>` : '';
    R.innerHTML += `
    <div class="card" style="margin-bottom:14px;padding:14px 18px">
      <div style="font-size:13px;font-weight:700;color:${muted};text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px">
        Price Chart — 1 Year &nbsp;·&nbsp; MA 50 &nbsp;·&nbsp; MA 200 &nbsp;${atLine}
      </div>
      <div style="height:240px;position:relative"><canvas id="decisionChart"></canvas></div>
    </div>`;
    _pendingChart = d;
  }

  // ── Technical signals
  if (d.rsi !== null && d.rsi !== undefined) {
    const rsiCol  = d.rsi > 70 ? '#ef4444' : d.rsi < 30 ? '#22c55e' : '#0ea5e9';
    const macdCol = d.macd_bullish ? '#22c55e' : '#ef4444';
    const atUp    = d.analyst_target ? ((d.analyst_target - d.price) / d.price * 100).toFixed(1) : null;
    const atCol   = atUp > 10 ? '#22c55e' : atUp < 0 ? '#ef4444' : '#facc15';
    R.innerHTML += `
    <div class="card" style="margin-bottom:14px">
      <div style="font-size:13px;font-weight:700;color:${muted};text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px">Technical Signals &amp; Analyst Data</div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">
        <div style="background:${surf};border-radius:8px;padding:12px">
          <div style="font-size:10px;color:${muted};text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">RSI (14)</div>
          <div style="font-size:26px;font-weight:800;color:${rsiCol}">${Number(d.rsi).toFixed(1)}</div>
          <div style="font-size:11px;color:${muted};margin-top:3px">${d.rsi>70?'Overbought':d.rsi<30?'Oversold':'Neutral zone'}</div>
        </div>
        <div style="background:${surf};border-radius:8px;padding:12px">
          <div style="font-size:10px;color:${muted};text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">MACD Histogram</div>
          <div style="font-size:20px;font-weight:800;color:${macdCol}">${d.macd_hist !== null ? (d.macd_hist >= 0 ? '+' : '') + Number(d.macd_hist).toFixed(4) : '—'}</div>
          <div style="font-size:11px;color:${muted};margin-top:3px">${d.macd_bullish ? 'Bullish momentum' : 'Bearish momentum'}</div>
        </div>
        ${d.analyst_target ? `
        <div style="background:${surf};border-radius:8px;padding:12px">
          <div style="font-size:10px;color:${muted};text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Analyst Target</div>
          <div style="font-size:20px;font-weight:800;color:${atCol}">$${Number(d.analyst_target).toFixed(2)}</div>
          <div style="font-size:11px;color:${muted};margin-top:3px">${atUp > 0 ? '+' : ''}${atUp}% upside · ${d.analyst_rec}</div>
        </div>` : `
        <div style="background:${surf};border-radius:8px;padding:12px">
          <div style="font-size:10px;color:${muted};text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Bollinger Bands</div>
          <div style="font-size:13px;font-weight:700;color:#f8fafc">Upper $${d.bb_upper}</div>
          <div style="font-size:13px;font-weight:700;color:#f8fafc;margin-top:4px">Lower $${d.bb_lower}</div>
          <div style="font-size:11px;color:${muted};margin-top:3px">Price $${Number(d.price).toFixed(2)}</div>
        </div>`}
      </div>
    </div>`;
  }

  // ── Decision score card
  R.innerHTML += `
  <div class="card" style="margin-bottom:14px;border-color:${decColor}">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
      <div>
        <div style="font-size:11px;color:${muted};text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">${d.mode_label}</div>
        <div style="display:flex;align-items:center;gap:12px">
          <span style="font-size:36px;font-weight:900;color:${decColor}">${d.decision}</span>
          <span style="font-size:16px;color:${muted}">${d.score} / ${d.max_pts}</span>
        </div>
        <div style="font-size:13px;color:${muted};margin-top:4px">${d.verdict}</div>
      </div>
      <div style="text-align:right">
        <div style="font-size:11px;color:${muted};margin-bottom:6px">Score</div>
        <div style="display:flex;gap:4px">
          ${Array.from({length: d.max_pts}, (_, i) =>
            `<div style="width:14px;height:24px;border-radius:3px;background:${i < d.score ? decColor : border}"></div>`
          ).join('')}
        </div>
        <div style="font-size:10px;color:${muted};margin-top:6px">BUY ≥8 · WATCH 5-7 · SKIP ≤4</div>
      </div>
    </div>
  </div>`;

  // ── Scoring guide
  let sgHTML = '';
  d.scoring_guide.forEach(sec => {
    sgHTML += `<div style="margin-bottom:14px">
      <div style="font-size:11px;font-weight:700;color:#0ea5e9;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">${sec.section}${sec.max ? ` — ${sec.max} pts` : ''}</div>`;
    if (sec.info) {
      sgHTML += `<div style="font-size:12px;color:${muted};line-height:1.5;padding:8px 10px;background:${surf};border-radius:6px">${sec.info}</div>`;
    }
    (sec.items || []).forEach(it => {
      sgHTML += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px;padding:8px 10px;background:${surf};border-radius:6px;font-size:12px">
        <div><strong style="color:#f8fafc">${it.factor}</strong> <span style="color:${muted}">${it.pts}</span><br><span style="color:${muted}">${it.what}</span></div>
        <div><span style="color:#22c55e">✓ ${it.pass}</span><br><span style="color:#ef4444">✗ ${it.fail}</span></div>
      </div>`;
    });
    sgHTML += '</div>';
  });
  R.innerHTML += `<details style="margin-bottom:14px">
    <summary style="cursor:pointer;list-style:none;padding:12px 18px;background:${surf};border-radius:10px;border:1px solid ${border};font-size:13px;font-weight:700;color:#f8fafc">
      ▸ Scoring Guide — how each point is earned
    </summary>
    <div style="padding:14px;border:1px solid ${border};border-top:none;border-radius:0 0 10px 10px">${sgHTML}</div>
  </details>`;

  // ── Factor analysis
  const sectionHeaders = d.mode === 'short'
    ? {0:'BUSINESS QUALITY', 3:'VALUATION', 5:'ENTRY TIMING', 7:'TECHNICAL CONFIRMATION'}
    : {0:'STEP 1: BUSINESS QUALITY', 4:'STEP 2: VALUATION', 6:'STEP 5: ENTRY ZONE', 8:'LONG-TERM TREND'};

  let faHTML = '';
  d.factors.forEach((f, i) => {
    if (sectionHeaders[i]) {
      faHTML += `<div style="font-size:10px;font-weight:700;color:#0ea5e9;text-transform:uppercase;letter-spacing:.5px;margin:12px 0 6px">${sectionHeaders[i]}</div>`;
    }
    const col   = deStatusClass(f.status);
    const ic    = deIcon(f.status);
    const isInfo = f.status === 'info';
    const pts   = f.max > 0 ? `${f.scored}/${f.max}` : '';
    faHTML += `<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid ${border}">
      <span style="color:${col};font-size:13px;font-weight:700;min-width:16px;margin-top:1px">${ic}</span>
      <div style="flex:1;min-width:0">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:12px;font-weight:600;color:${isInfo?muted:'#f8fafc'}">${f.label}</span>
          ${pts ? `<span style="font-size:11px;color:${col};font-weight:700">${pts}</span>` : ''}
        </div>
        <div style="font-size:12px;color:${muted};margin-top:2px;line-height:1.4">${f.note}</div>
      </div>
    </div>`;
  });
  R.innerHTML += `<div class="card" style="margin-bottom:14px">
    <div style="font-size:13px;font-weight:700;color:${muted};text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Factor Analysis</div>
    ${faHTML}
  </div>`;

  // ── Buy limit tiers
  const t = d.tiers;
  const price = d.price;
  function inRange(range) {
    if (!range) return false;
    if (range.startsWith('below')) return price < parseFloat(range.replace('below $',''));
    const parts = range.split(' to ');
    if (parts.length < 2) return false;
    return price >= parseFloat(parts[0].replace('$','')) && price <= parseFloat(parts[1].replace('$',''));
  }
  const inT1 = inRange(t.t1_range), inT2 = inRange(t.t2_range), inT3 = inRange(t.t3_range);
  const aboveAll = !inT1 && !inT2 && !inT3;
  function tierCard(range, label, idx, isHere) {
    return `<div style="background:${isHere?'rgba(14,165,233,.12)':surf};border:1px solid ${isHere?'#0ea5e9':border};border-radius:8px;padding:12px;text-align:center">
      <div style="font-size:10px;font-weight:700;color:${isHere?'#0ea5e9':muted};text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Tier ${idx}${isHere?' ← You are here':''}</div>
      <div style="font-size:15px;font-weight:700;color:#f8fafc;margin-bottom:4px">${range}</div>
      <div style="font-size:11px;color:${muted}">${label}</div>
    </div>`;
  }
  R.innerHTML += `<div class="card" style="margin-bottom:14px">
    <div style="font-size:13px;font-weight:700;color:${muted};text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">Buy Limit Tiers — ${t.method}</div>
    <div style="font-size:11px;color:${muted};margin-bottom:12px">${t.method_detail}</div>
    ${aboveAll ? `<div style="background:rgba(250,204,21,.08);border:1px solid #facc15;border-radius:6px;padding:10px 14px;font-size:12px;color:#facc15;margin-bottom:12px">Current price is above all tiers — wait for a pullback before buying.</div>` : ''}
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">
      ${tierCard(t.t1_range, t.t1_label, 1, inT1)}
      ${tierCard(t.t2_range, t.t2_label, 2, inT2)}
      ${tierCard(t.t3_range, t.t3_label, 3, inT3)}
    </div>
  </div>`;

  // ── Action plan
  let aHTML = '';
  d.action.forEach(a => {
    const body = a.points
      ? `<ul style="margin:6px 0 0;padding-left:18px;font-size:12px;color:${muted};line-height:1.6">${a.points.map(p=>`<li>${p}</li>`).join('')}</ul>`
      : `<div style="font-size:12px;color:${muted};margin-top:6px;line-height:1.5">${a.text}</div>`;
    const accentColor = a.cls==='stop'?'#ef4444':a.cls==='target'?'#22c55e':a.cls==='size'?'#0ea5e9':'#94a3b8';
    aHTML += `<div style="border-left:3px solid ${accentColor};padding:8px 0 8px 14px;margin-bottom:10px">
      <div style="font-size:11px;font-weight:700;color:${accentColor};text-transform:uppercase;letter-spacing:.5px">${a.heading}</div>
      ${body}
    </div>`;
  });
  R.innerHTML += `<div class="card" style="margin-bottom:14px">
    <div style="font-size:13px;font-weight:700;color:${muted};text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px">What to Do Now</div>
    ${aHTML}
  </div>`;

  // ── Closing section
  const c = d.closing;
  if (c) {
    let cHTML = '';
    if (c.type === 'buy') {
      cHTML = `<ul style="margin:0;padding-left:0;list-style:none">${c.checklist.map(x=>`
        <li style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid ${border};font-size:12px;color:${muted}">
          <span style="width:16px;height:16px;border:2px solid #22c55e;border-radius:3px;flex-shrink:0;margin-top:1px;display:inline-block"></span>${x}
        </li>`).join('')}</ul>`;
    } else if (c.type === 'watch' && c.items && c.items.length) {
      cHTML = `<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="color:${muted}"><th style="padding:6px 8px;text-align:left;border-bottom:1px solid ${border}">Factor</th><th style="text-align:left;padding:6px 8px;border-bottom:1px solid ${border}">Currently</th><th style="padding:6px 8px;border-bottom:1px solid ${border}">→</th><th style="text-align:left;padding:6px 8px;border-bottom:1px solid ${border}">Needs to be</th></tr></thead>
        <tbody>${c.items.map(it=>`<tr><td style="padding:6px 8px;border-bottom:1px solid ${border}"><strong>${it.label}</strong></td><td style="padding:6px 8px;border-bottom:1px solid ${border};color:#facc15">${it.currently}</td><td style="padding:6px 8px;border-bottom:1px solid ${border};color:${muted}">→</td><td style="padding:6px 8px;border-bottom:1px solid ${border};color:#22c55e">${it.needs}</td></tr>`).join('')}</tbody>
      </table></div>
      <div style="margin-top:12px;font-size:12px;color:${muted}">${c.footer}</div>`;
    } else if (c.type === 'skip') {
      cHTML = `<div style="font-size:12px;color:${muted};margin-bottom:12px">${c.score_context}</div>
        ${(c.reasons||[]).map(r=>`<div style="background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.25);border-radius:6px;padding:10px 14px;margin-bottom:8px">
          <div style="font-size:12px;font-weight:600;color:#fca5a5">${r.problem}</div>
          <div style="font-size:11px;color:${muted};margin-top:4px">${r.threshold}</div>
        </div>`).join('')}
        ${c.bottom_line?`<div style="margin-top:10px;padding:10px 14px;background:${surf};border-radius:6px;font-size:12px;color:${muted};font-style:italic">${c.bottom_line}</div>`:''}`;
    }
    if (cHTML) {
      R.innerHTML += `<div class="card" style="border-color:${decColor}">
        <div style="font-size:13px;font-weight:700;color:${muted};text-transform:uppercase;letter-spacing:.5px;margin-bottom:12px">${c.title}</div>
        ${cHTML}
      </div>`;
    }
  }

  // ── Init Chart.js AFTER all innerHTML mutations
  if (_pendingChart) {
    const _d = _pendingChart;
    setTimeout(() => {
      const ctx = document.getElementById('decisionChart');
      if (!ctx) return;
      if (decisionChart) { decisionChart.destroy(); decisionChart = null; }
      const datasets = [
        { label:'Price',   data:_d.chart_close,  borderColor:'#e6edf3', borderWidth:1.5, pointRadius:0, fill:false, tension:0.1 },
        { label:'MA 50',   data:_d.chart_ma50,   borderColor:'#388bfd', borderWidth:1.4, borderDash:[5,3], pointRadius:0, fill:false, spanGaps:true },
        { label:'MA 200',  data:_d.chart_ma200,  borderColor:'#d29922', borderWidth:1.4, borderDash:[5,3], pointRadius:0, fill:false, spanGaps:true },
      ];
      if (_d.analyst_target) {
        datasets.push({ label:'Analyst Target', data:_d.chart_dates.map(()=>_d.analyst_target),
          borderColor:'#d29922', borderWidth:1, borderDash:[2,4], pointRadius:0, fill:false, spanGaps:true });
      }
      decisionChart = new Chart(ctx, {
        type:'line',
        data:{ labels:_d.chart_dates, datasets },
        options:{
          responsive:true, maintainAspectRatio:false,
          interaction:{ mode:'index', intersect:false },
          plugins:{
            legend:{ labels:{ color:'#8b949e', font:{size:10}, boxWidth:16 } },
            tooltip:{ backgroundColor:'#161b22', borderColor:'#30363d', borderWidth:1,
              titleColor:'#e6edf3', bodyColor:'#8b949e',
              callbacks:{ label: c => c.dataset.label+': $'+(c.raw||0).toFixed(2) } }
          },
          scales:{
            x:{ ticks:{ color:'#8b949e', maxTicksLimit:8, font:{size:9} }, grid:{ color:'#21262d' } },
            y:{ position:'right', ticks:{ color:'#8b949e', font:{size:9}, callback:v=>'$'+v.toFixed(2) }, grid:{ color:'#21262d' } }
          }
        }
      });
    }, 0);
  }
}
