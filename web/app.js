// Every bet is one flat stake. The database stores results in stakes ("units");
// the page shows them as dollars at this bet size.
const STAKE = 10;

const STRATEGIES = {
  ai_analyst: {
    label: "AI analyst",
    desc: "Gemini reads injuries and rest, then bets its edges.",
    rules: "Starts from the market's fair odds for each game, reads today's ESPN injury reports, team records and back-to-backs, and adjusts the win probability by up to 5 points. It bets the moneyline only when its probability gives a 3% or better edge at the best available price.",
  },
  market_ev: {
    label: "Market EV",
    desc: "Bets sportsbook prices that beat the sharp market. No AI.",
    rules: "Removes the bookmaker's margin from Pinnacle's prices to get fair odds, then checks every US sportsbook. When a book pays at least 2.5% more than fair, it bets that price. One bet per game per market at most.",
  },
  baseline_fav: {
    label: "Favorite",
    desc: "Control: always bets the favorite.",
    rules: "A control group. Bets the moneyline favorite in every game at the best price available. Favorites win often but pay little, so this shows what simple chalk betting does.",
  },
  baseline_random: {
    label: "Coin flip",
    desc: "Control: bets a random side.",
    rules: "A control group. Picks a side at random for every game. Over time this should lose about the bookmaker's margin. Any real strategy has to beat it.",
  },
};
const ORDER = ["market_ev", "ai_analyst", "baseline_fav", "baseline_random"];
const RAIL_ORDER = ["ai_analyst", "market_ev"];

const BOOKS = {
  draftkings: "DraftKings", fanduel: "FanDuel", betmgm: "BetMGM", williamhill_us: "Caesars",
  espnbet: "ESPN BET", betrivers: "BetRivers", fanatics: "Fanatics", bovada: "Bovada", betonlineag: "BetOnline",
};
const book = (k) => BOOKS[k] ?? k;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const cls = (v) => (v == null || Math.abs(v) < 1e-9 ? "" : v > 0 ? "pos" : "neg");
const pct = (v, d = 1) => (v == null ? "–" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(d)}%`);
const plainPct = (v) => (v == null ? "–" : `${(v * 100).toFixed(0)}%`);
const odds = (p) => (p > 0 ? `+${p}` : `${p}`);
const winUnits = (american) => (american > 0 ? american / 100 : 100 / Math.abs(american));
const usd = (units, sign = true) => {
  if (units == null) return "–";
  const v = units * STAKE;
  const s = `$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return !sign || Math.abs(v) < 0.005 ? s : `${v > 0 ? "+" : "−"}${s}`;
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

// Show `limit` rows/cards until the button is pressed.
function collapsible({ button, total, limit, noun, draw, label }) {
  let open = false;
  const update = () => {
    draw(open ? total : limit);
    button.hidden = total <= limit;
    button.textContent = open ? "Show less" : label ?? `Show all ${total} ${noun}`;
  };
  button.onclick = () => { open = !open; update(); };
  update();
}

let DATA = null;

// ---------- Today's bets rail ----------
function renderRail(today) {
  const bets = RAIL_ORDER.flatMap((s) => today.filter((b) => b.strategy === s));
  $("today-count").textContent = bets.length ? `${bets.length} bet${bets.length === 1 ? "" : "s"} · scroll for more` : "";
  if (!bets.length) {
    $("rail").innerHTML = `<div class="none">No AI or Market EV bets today. They only bet when they find an edge.</div>`;
    return;
  }
  $("rail").innerHTML = bets.map((b) => {
    const why = b.strategy === "ai_analyst" && b.summary ? b.summary : `${esc(book(b.book))} pays more than the fair odds.`;
    return `<article class="bet" style="--c:var(--c-${b.strategy})">
      <div class="who">${dot(b.strategy)}${STRATEGIES[b.strategy].label}</div>
      <div class="pick">${pick(b)}</div>
      <div class="game">${esc(b.matchup)} · ${et(b.commence_time)}</div>
      <div class="why">${esc(why)}</div>
      <div class="nums">
        <div><span>Odds</span>${odds(b.price_american)}</div>
        <div><span>To win</span>${usd(winUnits(b.price_american), false)}</div>
        <div><span>Edge</span><b class="pos">${pct(b.ev)}</b></div>
      </div>
    </article>`;
  }).join("");
}

// ---------- Portfolio cards ----------
function statsFor(s) {
  return (DATA.summary || []).find((r) => r.strategy === s) || {};
}

function renderCards() {
  $("cards").innerHTML = ORDER.map((s) => {
    const r = statsFor(s);
    const settled = (r.decided ?? 0) + (r.pushes ?? 0);
    return `<button class="card" style="--c:var(--c-${s})" data-s="${s}" aria-label="Open ${STRATEGIES[s].label} details">
      <h3>${STRATEGIES[s].label}<span class="go">›</span></h3>
      <p class="desc">${STRATEGIES[s].desc}</p>
      <div class="big ${cls(r.units)}">${usd(r.units ?? 0)}</div>
      <div class="stats">
        <div><span>Record</span>${r.wins ?? 0}-${r.losses ?? 0}</div>
        <div><span>ROI</span><b class="${cls(r.roi)}">${pct(r.roi)}</b></div>
        <div><span>CLV</span><b class="${cls(r.avg_clv)}">${pct(r.avg_clv)}</b></div>
      </div>
      <p class="foot">${r.pending ?? 0} open · ${settled} settled</p>
    </button>`;
  }).join("");
  $("cards").querySelectorAll(".card").forEach((c) => c.addEventListener("click", () => { openedFromPage = true; location.hash = c.dataset.s; }));
}

// ---------- Charts ----------
function profitChart(canvas, strategies) {
  const daily = DATA.daily_units.filter((d) => strategies.includes(d.strategy));
  if (!daily.length || !window.Chart) return null;
  const days = [...new Set(daily.map((d) => d.day))].sort();
  const muted = css("--muted"), grid = css("--line");
  const datasets = strategies.map((s) => {
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
  return new Chart(canvas, {
    type: "line",
    data: { labels: days.map((d) => new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })), datasets },
    options: {
      animation: false,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: strategies.length > 1, labels: { color: muted, usePointStyle: true } },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${usd(c.parsed.y / STAKE)}` } },
      },
      scales: {
        x: { ticks: { color: muted }, grid: { color: grid } },
        y: { ticks: { color: muted, callback: (v) => usd(v / STAKE) }, grid: { color: grid } },
      },
    },
  });
}

function renderMainChart() {
  if (!profitChart($("profit-chart"), ORDER)) {
    $("chart-empty").hidden = false;
    $("profit-chart").parentElement.style.height = "120px";
  }
}

// ---------- Tables ----------
function openTable(rows, { showPortfolio = true } = {}) {
  if (!rows.length) return `<tbody><tr><td class="muted">No open bets.</td></tr></tbody>`;
  return `<thead><tr>${showPortfolio ? "<th>Portfolio</th>" : ""}<th>Game</th><th>Bet</th><th class="num">Odds</th><th class="num">To win</th><th class="num">CLV</th></tr></thead><tbody>` +
    rows.map((b) => `<tr>${showPortfolio ? `<td>${name(b.strategy)}</td>` : ""}
      <td>${esc(b.matchup)}<div class="muted">${b.league} · ${et(b.commence_time)}</div></td>
      <td>${pick(b)}</td>
      <td class="num">${odds(b.price_american)}<div class="muted">${esc(book(b.book))}</div></td>
      <td class="num">${usd(winUnits(b.price_american), false)}</td>
      <td class="num ${cls(b.clv)}">${pct(b.clv)}</td></tr>`).join("") + "</tbody>";
}

function settledTable(rows, { showPortfolio = true } = {}) {
  if (!rows.length) return `<tbody><tr><td class="muted">Nothing settled yet. Results post the morning after games.</td></tr></tbody>`;
  return `<thead><tr>${showPortfolio ? "<th>Portfolio</th>" : ""}<th>Game</th><th>Bet</th><th class="num">Odds</th><th class="num">Final</th><th>Result</th><th class="num">Profit</th></tr></thead><tbody>` +
    rows.map((b) => `<tr>${showPortfolio ? `<td>${name(b.strategy)}</td>` : ""}
      <td>${esc(b.matchup)}<div class="muted">${day(b.commence_time)}</div></td>
      <td>${pick(b)}</td><td class="num">${odds(b.price_american)}</td>
      <td class="num">${b.away_score ?? "–"}-${b.home_score ?? "–"}</td>
      <td><span class="pill ${b.result}">${b.result}</span></td>
      <td class="num ${cls(b.profit_units)}">${usd(b.profit_units)}</td></tr>`).join("") + "</tbody>";
}

function renderOpen(rows) {
  let active = "all";
  const draw = () => {
    const list = rows.filter((r) => active === "all" || r.strategy === active);
    collapsible({ button: $("open-more"), total: list.length, limit: 5, noun: "bets", draw: (n) => { $("open").innerHTML = openTable(list.slice(0, n)); } });
    $("open-filters").innerHTML = ["all", ...ORDER].map((f) => {
      const n = f === "all" ? rows.length : rows.filter((r) => r.strategy === f).length;
      return `<button role="tab" aria-selected="${f === active}" data-f="${f}">${f === "all" ? "All" : STRATEGIES[f].label} ${n}</button>`;
    }).join("");
    $("open-filters").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { active = b.dataset.f; draw(); }));
  };
  draw();
}

function renderLatest(rows) {
  collapsible({ button: $("latest-more"), total: Math.min(rows.length, 25), limit: 5, noun: "results", label: `Show last ${Math.min(rows.length, 25)}`, draw: (n) => { $("latest").innerHTML = settledTable(rows.slice(0, n)); } });
}

// ---------- AI reads ----------
function readCard(r) {
  const raw = r.ai_prob - r.market_prob;
  const delta = Math.abs(raw) < 0.005 ? 0 : raw;
  const pts = Math.abs(delta * 100).toFixed(0);
  const verdict = delta === 0 ? "Agrees with the market" : `${delta > 0 ? "Likes" : "Fades"} ${esc(r.home)} by ${pts} ${pts === "1" ? "pt" : "pts"}`;
  return `<article class="read">
    <div class="read-head"><h3>${esc(r.matchup)}</h3><span class="muted">${et(r.commence_time)}</span></div>
    <div class="probs"><span>${esc(r.home)}: AI <b>${plainPct(r.ai_prob)}</b> · market ${plainPct(r.market_prob)}</span><b class="${cls(delta)}">${verdict}</b></div>
    <div class="bar"><span class="m" style="left:${r.market_prob * 100}%"></span><span class="a" style="left:${r.ai_prob * 100}%"></span></div>
    <p>${esc(r.summary)}</p>
  </article>`;
}

function renderReads(reads) {
  // Games where the AI disagrees with the market come first
  const sorted = [...reads].sort((a, b) => Math.abs(b.ai_prob - b.market_prob) - Math.abs(a.ai_prob - a.market_prob));
  if (!sorted.length) {
    $("reads").innerHTML = `<p class="muted">No upcoming games yet.</p>`;
    return;
  }
  collapsible({ button: $("reads-more"), total: sorted.length, limit: 3, noun: "games", draw: (n) => { $("reads").innerHTML = sorted.slice(0, n).map(readCard).join(""); } });
}

// ---------- Portfolio detail sheet ----------
let sheetChart = null;
let openedFromPage = false;

function openSheet(s) {
  const meta = STRATEGIES[s];
  const r = statsFor(s);
  const open = DATA.today.filter((b) => b.strategy === s);
  const settled = DATA.settled.filter((b) => b.strategy === s);
  const decided = settled.filter((b) => b.result === "win" || b.result === "loss");
  const winRate = decided.length ? decided.filter((b) => b.result === "win").length / decided.length : null;
  const best = settled.reduce((m, b) => (b.profit_units > (m ?? -Infinity) ? b.profit_units : m), null);
  const avgDec = settled.length ? settled.reduce((t, b) => t + 1 + winUnits(b.price_american), 0) / settled.length : null;
  const avgOdds = avgDec == null ? "–" : avgDec >= 2 ? `+${Math.round((avgDec - 1) * 100)}` : `${Math.round(-100 / (avgDec - 1))}`;

  let accuracy = "";
  if (s === "ai_analyst") {
    const a = (DATA.ai_vs_market || [])[0];
    accuracy = a
      ? `<p class="note">Accuracy vs the market on ${a.games} finished games: AI error ${a.ai_brier.toFixed(4)}, market ${a.market_brier.toFixed(4)} (lower is better). ${a.games < 100 ? "Too early to call." : a.ai_brier < a.market_brier ? "The AI is ahead." : "The market is ahead."}</p>`
      : `<p class="note">Once games finish, this compares how accurate the AI's win probabilities are against the market's.</p>`;
  }

  $("sheet-body").innerHTML = `
    <div class="sheet-top" style="--c:var(--c-${s})">
      <div><h2 id="sheet-title">${dot(s)}${meta.label}</h2><p>${meta.desc}</p></div>
      <button class="close" id="sheet-close" aria-label="Close">✕</button>
    </div>
    <div class="kpis">
      <div class="kpi"><span>Profit</span><b class="${cls(r.units)}">${usd(r.units ?? 0)}</b></div>
      <div class="kpi"><span>Record</span><b>${r.wins ?? 0}-${r.losses ?? 0}${r.pushes ? `-${r.pushes}` : ""}</b></div>
      <div class="kpi"><span>Win rate</span><b>${winRate == null ? "–" : plainPct(winRate)}</b></div>
      <div class="kpi"><span>ROI</span><b class="${cls(r.roi)}">${pct(r.roi)}</b></div>
      <div class="kpi"><span>CLV</span><b class="${cls(r.avg_clv)}">${pct(r.avg_clv)}</b></div>
      <div class="kpi"><span>Open bets</span><b>${open.length}</b></div>
      <div class="kpi"><span>Avg odds</span><b>${avgOdds}</b></div>
      <div class="kpi"><span>Best win</span><b class="${cls(best)}">${best == null ? "–" : usd(best)}</b></div>
    </div>
    <section><h2>How it bets</h2><p class="note" style="font-size:14px">${meta.rules}</p>${accuracy}</section>
    <section><h2>Profit over time</h2><div class="panel chart-panel"><canvas id="sheet-chart"></canvas><p class="empty" id="sheet-chart-empty" hidden>Fills in once the first games finish.</p></div></section>
    <section><h2>Open bets</h2><div class="panel table-wrap"><table>${openTable(open, { showPortfolio: false })}</table></div></section>
    <section><h2>Settled bets</h2><div class="panel table-wrap"><table>${settledTable(settled, { showPortfolio: false })}</table></div></section>`;

  $("sheet").hidden = false;
  $("sheet-backdrop").hidden = false;
  document.body.classList.add("locked");
  $("sheet").scrollTop = 0;
  if (sheetChart) sheetChart.destroy();
  sheetChart = profitChart($("sheet-chart"), [s]);
  if (!sheetChart) {
    $("sheet-chart-empty").hidden = false;
    $("sheet-chart").parentElement.style.height = "100px";
  }
  $("sheet-close").onclick = closeSheet;
  $("sheet-close").focus();
}

function hideSheet() {
  $("sheet").hidden = true;
  $("sheet-backdrop").hidden = true;
  document.body.classList.remove("locked");
}

function closeSheet() {
  if (openedFromPage) {
    openedFromPage = false;
    history.back();  // fires popstate -> route()
  } else {
    history.replaceState(null, "", location.pathname + location.search);
    route();
  }
}

function route() {
  const s = location.hash.slice(1);
  if (DATA && STRATEGIES[s]) openSheet(s);
  else hideSheet();
}

async function main() {
  $("stake-note").textContent = `$${STAKE} paper bets`;
  try {
    DATA = await fetch(`data.json?t=${Date.now()}`).then((r) => r.json());
  } catch (e) {
    $("updated").textContent = "Couldn't load data";
    console.error(e);
    return;
  }
  $("updated").textContent = `Updated ${et(DATA.generated_at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} ET`;
  renderRail(DATA.today);
  renderCards();
  renderMainChart();
  renderOpen(DATA.today);
  renderReads(DATA.ai_reads);
  renderLatest(DATA.settled);

  window.addEventListener("hashchange", route);
  $("sheet-backdrop").addEventListener("click", closeSheet);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("sheet").hidden) closeSheet(); });
  route();
}
main();
