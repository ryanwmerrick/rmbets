const STRATEGIES = {
  market_ev: { label: "Market EV", desc: "Line shopping vs Pinnacle's fair line. No AI." },
  ai_analyst: { label: "AI analyst", desc: "Gemini adjusts the market using ESPN injuries and rest." },
  baseline_fav: { label: "Favorite", desc: "Control: always bet the moneyline favorite." },
  baseline_random: { label: "Coin flip", desc: "Control: a seeded random side." },
};
const ORDER = Object.keys(STRATEGIES);

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const color = (s) => getComputedStyle(document.documentElement).getPropertyValue(`--c-${s}`).trim();
const signed = (v, d = 2) => (v == null ? "–" : `${v > 0 ? "+" : ""}${Number(v).toFixed(d)}`);
const pct = (v, d = 1) => (v == null ? "–" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(d)}%`);
const plainPct = (v, d = 1) => (v == null ? "–" : `${(v * 100).toFixed(d)}%`);
const cls = (v) => (v == null ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "");
const price = (p) => (p > 0 ? `+${p}` : `${p}`);
const et = (iso, opts = { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) =>
  new Date(iso).toLocaleString("en-US", { timeZone: "America/New_York", ...opts });
const dot = (s) => `<span class="dot" style="--c:var(--c-${s})"></span>`;

function pick(b) {
  if (b.market === "h2h") return `${esc(b.outcome)} ML`;
  if (b.market === "spreads") return `${esc(b.outcome)} ${signed(b.point, 1)}`;
  return `${esc(b.outcome)} ${b.point}`;
}

function renderCards(summary) {
  const by = Object.fromEntries(summary.map((r) => [r.strategy, r]));
  $("cards").innerHTML = ORDER.map((s) => {
    const r = by[s] || {};
    const record = `${r.wins ?? 0}-${r.losses ?? 0}${r.pushes ? `-${r.pushes}` : ""}`;
    return `<article class="card" style="--c:var(--c-${s})">
      <h3>${STRATEGIES[s].label}<span class="muted">${esc(r.strategy_version ? "v" + r.strategy_version : "")}</span></h3>
      <p class="desc">${STRATEGIES[s].desc}</p>
      <div class="big ${cls(r.units)}">${signed(r.units ?? 0)} u</div>
      <div class="stats">
        <div><span>Record</span>${record}</div>
        <div><span>ROI</span><b class="${cls(r.roi)}">${pct(r.roi)}</b></div>
        <div><span>Avg CLV</span><b class="${cls(r.avg_clv)}">${pct(r.avg_clv)}</b></div>
      </div>
      <div class="stats"><div><span>Pending</span>${r.pending ?? 0}</div><div><span>Graded</span>${(r.decided ?? 0) + (r.pushes ?? 0)}</div><div><span>Toward 300</span>${Math.min(100, Math.round(((r.decided ?? 0) / 300) * 100))}%</div></div>
    </article>`;
  }).join("");
}

function renderChart(daily) {
  if (!daily.length || !window.Chart) {
    $("chart-empty").hidden = false;
    $("units-chart").parentElement.style.height = "120px";
    return;
  }
  const days = [...new Set(daily.map((d) => d.day))].sort();
  const datasets = ORDER.map((s) => {
    let last = 0;
    const map = Object.fromEntries(daily.filter((d) => d.strategy === s).map((d) => [d.day, d.cumulative_units]));
    return {
      label: STRATEGIES[s].label,
      data: days.map((d) => (last = map[d] ?? last)),
      borderColor: color(s),
      backgroundColor: color(s),
      tension: 0.2,
      pointRadius: days.length > 30 ? 0 : 3,
      borderWidth: s === "ai_analyst" || s === "market_ev" ? 2.5 : 1.5,
    };
  });
  const ink = getComputedStyle(document.documentElement).getPropertyValue("--muted").trim();
  const grid = getComputedStyle(document.documentElement).getPropertyValue("--line").trim();
  new Chart($("units-chart"), {
    type: "line",
    data: { labels: days.map((d) => new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })), datasets },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: ink, usePointStyle: true } } },
      scales: {
        x: { ticks: { color: ink }, grid: { color: grid } },
        y: { ticks: { color: ink }, grid: { color: grid }, title: { display: true, text: "Units", color: ink } },
      },
    },
  });
}

function renderToday(rows) {
  const filters = ["all", ...ORDER];
  let active = "all";
  const draw = () => {
    const list = rows.filter((r) => active === "all" || r.strategy === active);
    $("today").innerHTML = list.length
      ? `<thead><tr><th>Portfolio</th><th>Game (ET)</th><th>Pick</th><th>Book</th><th class="num">Price</th><th class="num">EV</th><th class="num">CLV</th></tr></thead><tbody>` +
        list.map((b) => `<tr><td>${dot(b.strategy)}${STRATEGIES[b.strategy]?.label ?? b.strategy}</td>
          <td>${esc(b.matchup)}<div class="muted">${b.league} · ${et(b.commence_time)}</div></td>
          <td>${pick(b)}</td><td>${esc(b.book)}</td><td class="num">${price(b.price_american)}</td>
          <td class="num ${cls(b.ev)}">${pct(b.ev)}</td><td class="num ${cls(b.clv)}">${pct(b.clv)}</td></tr>`).join("") + "</tbody>"
      : `<tbody><tr><td class="muted">No open bets${active === "all" ? "" : " for this portfolio"}.</td></tr></tbody>`;
    $("today-filters").innerHTML = filters.map((f) => {
      const n = f === "all" ? rows.length : rows.filter((r) => r.strategy === f).length;
      return `<button role="tab" aria-selected="${f === active}" data-f="${f}">${f === "all" ? "All" : STRATEGIES[f].label} (${n})</button>`;
    }).join("");
    $("today-filters").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { active = b.dataset.f; draw(); }));
  };
  draw();
}

function renderReads(reads) {
  if (!reads.length) {
    $("reads").innerHTML = `<p class="muted">No upcoming games analyzed yet.</p>`;
    return;
  }
  $("reads").innerHTML = reads.map((r) => {
    const raw = r.ai_prob - r.market_prob;
    const delta = Math.abs(raw) < 0.0005 ? 0 : raw;
    const factors = (r.factors || []).slice(0, 4).map((f) => `<li>${esc(f.factor)}</li>`).join("");
    return `<article class="read">
      <h3>${esc(r.matchup)}</h3>
      <div class="meta">${r.league} · ${et(r.commence_time)} · confidence ${esc(r.confidence)}</div>
      <div class="probs"><span>${esc(r.home)} win chance</span><span>AI <b class="${cls(delta)}">${plainPct(r.ai_prob)}</b> vs market ${plainPct(r.market_prob)}</span></div>
      <div class="bar"><span class="m" style="left:${r.market_prob * 100}%"></span><span class="a" style="left:${r.ai_prob * 100}%"></span></div>
      <p>${esc(r.summary)}</p>${factors ? `<ul>${factors}</ul>` : ""}
    </article>`;
  }).join("");
}

function renderBrier(rows) {
  $("brier").innerHTML = rows.length
    ? `<thead><tr><th>Version</th><th class="num">Games</th><th class="num">AI Brier</th><th class="num">Market Brier</th><th>Verdict</th></tr></thead><tbody>` +
      rows.map((r) => {
        const better = r.ai_brier < r.market_brier;
        return `<tr><td>v${esc(r.strategy_version)}</td><td class="num">${r.games}</td><td class="num">${r.ai_brier.toFixed(4)}</td>
          <td class="num">${r.market_brier.toFixed(4)}</td><td>${r.games < 100 ? '<span class="muted">Too early (needs ~100+ games)</span>' : better ? '<span class="pos">AI more accurate</span>' : '<span class="neg">Market more accurate</span>'}</td></tr>`;
      }).join("") + "</tbody>"
    : `<tbody><tr><td class="muted">No completed games yet.</td></tr></tbody>`;
}

function renderRecent(rows) {
  $("recent").innerHTML = rows.length
    ? `<thead><tr><th>Portfolio</th><th>Game</th><th>Pick</th><th class="num">Price</th><th class="num">Score</th><th>Result</th><th class="num">Units</th><th class="num">CLV</th></tr></thead><tbody>` +
      rows.map((b) => `<tr><td>${dot(b.strategy)}${STRATEGIES[b.strategy]?.label ?? b.strategy}</td>
        <td>${esc(b.matchup)}<div class="muted">${et(b.commence_time, { month: "short", day: "numeric" })}</div></td>
        <td>${pick(b)}</td><td class="num">${price(b.price_american)}</td>
        <td class="num">${b.away_score ?? "–"}-${b.home_score ?? "–"}</td>
        <td><span class="pill ${b.result}">${b.result}</span></td>
        <td class="num ${cls(b.profit_units)}">${signed(b.profit_units)}</td><td class="num ${cls(b.clv)}">${pct(b.clv)}</td></tr>`).join("") + "</tbody>"
    : `<tbody><tr><td class="muted">Nothing graded yet. Results appear the morning after games finish.</td></tr></tbody>`;
}

function renderV1(v1) {
  $("v1").innerHTML = `<div class="v1">
    <div class="muted">${esc(v1.period)} · Gemini picks, odds written by the AI</div>
    <div class="big neg">${signed(v1.units)} u</div>
    <div class="stats"><div><span>Record</span>${v1.wins}-${v1.bets - v1.wins}</div><div><span>ROI</span><b class="neg">${pct(v1.roi)}</b></div><div><span>Bets</span>${v1.bets}</div></div>
    <p class="muted" style="font-size:13px;margin:12px 0 0">v1's AI had no live data and invented both its research and its edges. v2 fixes both and adds controls.</p>
  </div>`;
}

function renderRuns(runs) {
  $("runs").innerHTML = `<thead><tr><th>Job</th><th>Started (ET)</th><th>Status</th><th class="num">Credits left</th></tr></thead><tbody>` +
    runs.slice(0, 8).map((r) => `<tr><td>${esc(r.job)}</td><td>${et(r.started_at)}</td>
      <td><span class="pill ${r.status}" title="${esc(r.error || "")}">${r.status}</span></td>
      <td class="num">${r.credits_remaining ?? "–"}</td></tr>`).join("") + "</tbody>";
}

async function main() {
  try {
    const res = await fetch(`data.json?t=${Date.now()}`);
    const d = await res.json();
    $("updated").textContent = `Updated ${et(d.generated_at)} ET`;
    renderCards(d.summary);
    renderChart(d.daily_units);
    renderToday(d.today);
    renderReads(d.ai_reads);
    renderBrier(d.ai_vs_market);
    renderRecent(d.recent);
    renderV1(d.v1);
    renderRuns(d.runs);
  } catch (e) {
    $("updated").textContent = "Couldn't load data.json";
    console.error(e);
  }
}
main();
