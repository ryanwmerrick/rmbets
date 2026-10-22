// Every bet is one flat stake. The database stores results in stakes ("units");
// the page shows them as dollars at this bet size.
const STAKE = 100;

const STRATEGIES = {
  market_ev: { label: "Market EV", desc: "Bets sportsbook prices that beat the sharp market. No AI." },
  ai_analyst: { label: "AI analyst", desc: "Gemini reads injuries and rest, then bets its edges." },
  baseline_fav: { label: "Favorite", desc: "Control: always bets the favorite." },
  baseline_random: { label: "Coin flip", desc: "Control: bets a random side." },
};
const ORDER = Object.keys(STRATEGIES);

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const cls = (v) => (v == null || Math.abs(v) < 1e-9 ? "" : v > 0 ? "pos" : "neg");
const pct = (v, d = 1) => (v == null ? "–" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(d)}%`);
const plainPct = (v) => (v == null ? "–" : `${(v * 100).toFixed(0)}%`);
const odds = (p) => (p > 0 ? `+${p}` : `${p}`);
const usd = (units, sign = true) => {
  if (units == null) return "–";
  const v = units * STAKE;
  const s = `$${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  return !sign || Math.abs(v) < 0.5 ? s : `${v > 0 ? "+" : "−"}${s}`;
};
const et = (iso, opts = { weekday: "short", hour: "numeric", minute: "2-digit" }) =>
  new Date(iso).toLocaleString("en-US", { timeZone: "America/New_York", ...opts });
const day = (iso) => et(iso, { month: "short", day: "numeric" });
const dot = (s) => `<span class="dot" style="--c:var(--c-${s})"></span>`;
const name = (s) => `${dot(s)}${STRATEGIES[s]?.label ?? esc(s)}`;

function pick(b) {
  if (b.market === "h2h") return `${esc(b.outcome)} to win`;
  if (b.market === "spreads") return `${esc(b.outcome)} ${b.point > 0 ? "+" : ""}${b.point}`;
  return `${esc(b.outcome)} ${b.point}`;
}

function renderCards(summary) {
  const by = Object.fromEntries(summary.map((r) => [r.strategy, r]));
  $("cards").innerHTML = ORDER.map((s) => {
    const r = by[s] || {};
    const settled = (r.decided ?? 0) + (r.pushes ?? 0);
    return `<article class="card" style="--c:var(--c-${s})">
      <h3>${STRATEGIES[s].label}</h3>
      <p class="desc">${STRATEGIES[s].desc}</p>
      <div class="big ${cls(r.units)}">${usd(r.units ?? 0)}</div>
      <div class="stats">
        <div><span>Record</span>${r.wins ?? 0}-${r.losses ?? 0}</div>
        <div><span>ROI</span><b class="${cls(r.roi)}">${pct(r.roi)}</b></div>
        <div><span>CLV</span><b class="${cls(r.avg_clv)}">${pct(r.avg_clv)}</b></div>
      </div>
      <p class="foot">${r.pending ?? 0} open · ${settled} settled</p>
    </article>`;
  }).join("");
}

function renderChart(daily) {
  if (!daily.length || !window.Chart) {
    $("chart-empty").hidden = false;
    $("profit-chart").parentElement.style.height = "120px";
    return;
  }
  const days = [...new Set(daily.map((d) => d.day))].sort();
  const muted = css("--muted"), grid = css("--line");
  const datasets = ORDER.map((s) => {
    let last = 0;
    const map = Object.fromEntries(daily.filter((d) => d.strategy === s).map((d) => [d.day, d.cumulative_units]));
    return {
      label: STRATEGIES[s].label,
      data: days.map((d) => (last = map[d] ?? last) * STAKE),
      borderColor: css(`--c-${s}`),
      backgroundColor: css(`--c-${s}`),
      tension: 0.2,
      pointRadius: days.length > 30 ? 0 : 3,
      borderWidth: s.startsWith("baseline") ? 1.5 : 2.5,
    };
  });
  new Chart($("profit-chart"), {
    type: "line",
    data: { labels: days.map((d) => new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })), datasets },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: muted, usePointStyle: true } },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${usd(c.parsed.y / STAKE)}` } },
      },
      scales: {
        x: { ticks: { color: muted }, grid: { color: grid } },
        y: { ticks: { color: muted, callback: (v) => usd(v / STAKE) }, grid: { color: grid } },
      },
    },
  });
}

function renderOpen(rows) {
  let active = "all";
  const draw = () => {
    const list = rows.filter((r) => active === "all" || r.strategy === active);
    $("today").innerHTML = list.length
      ? `<thead><tr><th>Portfolio</th><th>Game</th><th>Bet</th><th class="num">Odds</th><th class="num">To win</th><th class="num">CLV</th></tr></thead><tbody>` +
        list.map((b) => `<tr><td>${name(b.strategy)}</td>
          <td>${esc(b.matchup)}<div class="muted">${b.league} · ${et(b.commence_time)}</div></td>
          <td>${pick(b)}</td>
          <td class="num">${odds(b.price_american)}<div class="muted">${esc(b.book)}</div></td>
          <td class="num">${usd(b.price_american > 0 ? b.price_american / 100 : 100 / Math.abs(b.price_american), false)}</td>
          <td class="num ${cls(b.clv)}">${pct(b.clv)}</td></tr>`).join("") + "</tbody>"
      : `<tbody><tr><td class="muted">No open bets.</td></tr></tbody>`;
    $("today-filters").innerHTML = ["all", ...ORDER].map((f) => {
      const n = f === "all" ? rows.length : rows.filter((r) => r.strategy === f).length;
      return `<button role="tab" aria-selected="${f === active}" data-f="${f}">${f === "all" ? "All" : STRATEGIES[f].label} ${n}</button>`;
    }).join("");
    $("today-filters").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { active = b.dataset.f; draw(); }));
  };
  draw();
}

function renderReads(reads) {
  if (!reads.length) {
    $("reads").innerHTML = `<p class="muted">No upcoming games yet.</p>`;
    return;
  }
  $("reads").innerHTML = reads.map((r) => {
    const raw = r.ai_prob - r.market_prob;
    const delta = Math.abs(raw) < 0.005 ? 0 : raw;
    const verdict = delta === 0 ? "Agrees with the market" : `${delta > 0 ? "Likes" : "Fades"} ${esc(r.home)} by ${Math.abs(delta * 100).toFixed(0)} ${Math.abs(delta * 100).toFixed(0) === "1" ? "pt" : "pts"}`;
    return `<article class="read">
      <div class="read-head"><h3>${esc(r.matchup)}</h3><span class="muted">${et(r.commence_time)}</span></div>
      <div class="probs"><span>${esc(r.home)}: AI <b>${plainPct(r.ai_prob)}</b> · market ${plainPct(r.market_prob)}</span><b class="${cls(delta)}">${verdict}</b></div>
      <div class="bar"><span class="m" style="left:${r.market_prob * 100}%"></span><span class="a" style="left:${r.ai_prob * 100}%"></span></div>
      <p>${esc(r.summary)}</p>
    </article>`;
  }).join("");
}

function renderRecent(rows) {
  $("recent").innerHTML = rows.length
    ? `<thead><tr><th>Portfolio</th><th>Game</th><th>Bet</th><th class="num">Odds</th><th class="num">Final</th><th>Result</th><th class="num">Profit</th></tr></thead><tbody>` +
      rows.map((b) => `<tr><td>${name(b.strategy)}</td>
        <td>${esc(b.matchup)}<div class="muted">${day(b.commence_time)}</div></td>
        <td>${pick(b)}</td><td class="num">${odds(b.price_american)}</td>
        <td class="num">${b.away_score ?? "–"}-${b.home_score ?? "–"}</td>
        <td><span class="pill ${b.result}">${b.result}</span></td>
        <td class="num ${cls(b.profit_units)}">${usd(b.profit_units)}</td></tr>`).join("") + "</tbody>"
    : `<tbody><tr><td class="muted">Nothing settled yet. Results post the morning after games.</td></tr></tbody>`;
}

function renderBrier(rows) {
  const r = rows[0];
  $("brier").innerHTML = r
    ? `<thead><tr><th class="num">Games</th><th class="num">AI error</th><th class="num">Market error</th><th>So far</th></tr></thead><tbody>
        <tr><td class="num">${r.games}</td><td class="num">${r.ai_brier.toFixed(4)}</td><td class="num">${r.market_brier.toFixed(4)}</td>
        <td>${r.games < 100 ? '<span class="muted">Too early to tell</span>' : r.ai_brier < r.market_brier ? '<span class="pos">AI is more accurate</span>' : '<span class="neg">Market is more accurate</span>'}</td></tr></tbody>`
    : `<tbody><tr><td class="muted">Shows up after the first games finish. Lower error wins.</td></tr></tbody>`;
}

function renderRuns(runs) {
  $("runs").innerHTML = `<thead><tr><th>Job</th><th>When</th><th>Status</th><th class="num">Odds credits left</th></tr></thead><tbody>` +
    runs.slice(0, 5).map((r) => `<tr><td>${esc(r.job)}</td><td>${et(r.started_at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</td>
      <td><span class="pill ${r.status}" title="${esc(r.error || "")}">${r.status}</span></td>
      <td class="num">${r.credits_remaining ?? "–"}</td></tr>`).join("") + "</tbody>";
}

async function main() {
  $("stake-note").textContent = `$${STAKE} paper bets`;
  try {
    const d = await fetch(`data.json?t=${Date.now()}`).then((r) => r.json());
    $("updated").textContent = `Updated ${et(d.generated_at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} ET`;
    renderCards(d.summary);
    renderChart(d.daily_units);
    renderOpen(d.today);
    renderReads(d.ai_reads);
    renderRecent(d.recent);
    renderBrier(d.ai_vs_market);
    renderRuns(d.runs);
  } catch (e) {
    $("updated").textContent = "Couldn't load data";
    console.error(e);
  }
}
main();
