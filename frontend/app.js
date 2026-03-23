let positionChart = null;

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
  return (x * 100).toFixed(2) + "%";
}

function fmtNum(x) {
  if (x === null || x === undefined || isNaN(x)) return "—";
  return Number(x).toFixed(2);
}

function badgeClassForRisk(risk) {
  if (!risk) return "badge-neutral";
  const r = risk.toLowerCase();
  if (r === "low") return "badge-green";
  if (r === "medium") return "badge-yellow";
  if (r === "high") return "badge-red";
  return "badge-neutral";
}

function badgeClassForSafety(safety) {
  if (!safety) return "badge-neutral";
  const s = safety.toLowerCase();
  if (s === "safe") return "badge-green";
  if (s === "cautious") return "badge-yellow";
  if (s === "unsafe") return "badge-red";
  return "badge-neutral";
}

function badgeClassForConviction(conviction) {
  if (!conviction) return "badge-neutral";
  const c = conviction.toLowerCase();
  if (c === "strong buy") return "badge-green";
  if (c === "buy") return "badge-blue";
  if (c === "watch") return "badge-yellow";
  if (c === "speculative" || c === "avoid") return "badge-red";
  return "badge-neutral";
}

function renderBadge(text, cls) {
  return `<span class="status-badge ${cls}">${text ?? "—"}</span>`;
}

function renderBar(label, value) {
  const pct = value ? (value / 10) * 100 : 0;
  return `
    <div class="factor-bar">
      <div class="factor-bar-header">
        <span>${label}</span>
        <span>${value ?? "—"}/10</span>
      </div>
      <div class="factor-bar-track">
        <div class="factor-bar-fill" style="width:${pct}%"></div>
      </div>
    </div>
  `;
}

async function runSnapshot(evt) {
  evt.preventDefault();
  clearError();

  const tickersStr = document.getElementById("tickers").value || "";
  const start = document.getElementById("start").value || "2015-01-01";
  const horizon = document.getElementById("horizon").value || 10;
  const buy = document.getElementById("buy_thresh").value || 0.6;
  const sell = document.getElementById("sell_thresh").value || 0.4;

  const params = new URLSearchParams({
    tickers: tickersStr,
    start,
    horizon,
    buy_thresh: buy,
    sell_thresh: sell,
  });

  const btn = document.getElementById("runBtn");
  btn.disabled = true;
  btn.textContent = "Running…";

  try {
    const resp = await fetch(`/api/compare?${params.toString()}`);
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
      selectTicker(clean[0], raw.horizon_days || horizon);
    } else if (clean.length > 1) {
      clearDetails();
    } else {
      clearDetails();
      showError("No valid tickers returned.");
    }
  } catch (err) {
    console.error(err);
    showError("Failed to call /api/compare.");
  } finally {
    btn.disabled = false;
    btn.textContent = "▶ Run Snapshot";
  }
}

function renderComparisonTable(rows) {
  const tbody = document.getElementById("comparisonBody");
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
  details.innerHTML = `<p>Select a row in the comparison table to see full details here.</p>`;

  if (positionChart) {
    positionChart.destroy();
    positionChart = null;
  }
}

function selectTicker(row, horizonOverride) {
  const details = document.getElementById("tickerDetails");
  const proba = row.proba_pos_move ?? null;
  const horizon = horizonOverride || row.horizon || 10;
  const factor = row.factor_model || {};
  const factors = factor.factors || {};
  const finalScore = factor.final_score ?? "—";
  const conviction = factor.conviction || "—";
  const bestFactor = factor.best_factor?.name || "—";
  const weakestFactor = factor.weakest_factor?.name || "—";
  const riskLevel = row.risk_level || factor.risk_level || "—";
  const buySafety = row.buy_safety || factor.buy_safety || "—";
  const interpretation = factor.interpretation || "—";
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

  <p><strong>Final Score:</strong> ${finalScore}/10</p>
  <p><strong>Conviction:</strong> ${renderBadge(conviction, badgeClassForConviction(conviction))}</p>
  <p><strong>Risk Level:</strong> ${renderBadge(riskLevel, badgeClassForRisk(riskLevel))}</p>
  <p><strong>Buy Safety:</strong> ${renderBadge(buySafety, badgeClassForSafety(buySafety))}</p>

  <div style="margin-top:10px;padding:10px 12px;border:1px solid #1f2937;border-radius:10px;background:#020617;">
    <p style="margin:0 0 4px;"><strong>Interpretation</strong></p>
    <p style="margin:0;color:#cbd5e1;">${interpretation}</p>
  </div>

  <p style="margin-top:12px;"><strong>Best Factor:</strong> ${bestFactor}</p>
  <p><strong>Weakest Factor:</strong> ${weakestFactor}</p>

  <div style="margin-top:10px;">
    <p><strong>Factor Breakdown</strong></p>
    ${renderBar("Quality", factors.quality)}
    ${renderBar("Growth", factors.growth)}
    ${renderBar("Value", factors.value)}
    ${renderBar("Momentum", factors.momentum)}
    ${renderBar("Risk", factors.risk)}
  </div>
`;

  if (proba !== null && proba !== undefined && !isNaN(proba)) {
    const up = proba * 100;
    const notUp = 100 - up;

    const canvas = document.getElementById("positionPie");
    const ctx = canvas.getContext("2d");

    if (positionChart) {
      positionChart.destroy();
    }

    positionChart = new Chart(ctx, {
      type: "pie",
      data: {
        labels: ["Chance price UP", "Chance flat / down"],
        datasets: [
          {
            data: [up, notUp],
          },
        ],
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
  }
}

async function checkHealth() {
  const el = document.getElementById("apiStatus");
  if (!el) return;
  try {
    const resp = await fetch("/health");
    if (!resp.ok) throw new Error();
    el.textContent = "API: healthy";
    el.classList.remove("badge-danger");
    el.classList.add("badge-success");
  } catch {
    el.textContent = "API: error";
    el.classList.remove("badge-success");
    el.classList.add("badge-danger");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("snapshotForm");
  if (form) {
    form.addEventListener("submit", runSnapshot);
  }
  checkHealth();
  clearDetails();
});