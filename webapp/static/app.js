(() => {
  const tg = window.Telegram && window.Telegram.WebApp;
  const initData = (tg && tg.initData) || "";
  if (tg) { tg.ready(); tg.expand(); }
  let settings = {};

  const $ = (s) => document.querySelector(s);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v) => (v === null || v === undefined || v === "" ? "–" : Number(v).toFixed(Number(v) > 500 ? 2 : Number(v) > 20 ? 3 : 5));  // gold/indices 2, JPY/silver 3, FX 5
  // Times from the API are UTC. Shown in the display_tz setting (else the phone's zone) with a friendly day near
  // now (owner request 2026-10-15): "Today, Thu 15 Oct 10:00", "Yesterday, ...", "Monday, 12 Oct 22:00",
  // "Last week Monday, 5 Oct 22:00"; further away "Mon 28 Sep 22:00" (year added when not this year).
  const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const fmtParts = (d, tz) => new Intl.DateTimeFormat("en-GB", { timeZone: tz, year: "numeric", month: "numeric",
    day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(d);
  const parts = (d) => {  // wall-clock parts of d in the display zone (unknown zone -> the phone's zone)
    let p;
    try { p = fmtParts(d, settings.display_tz || undefined); } catch (e) { p = fmtParts(d, undefined); }
    const g = (t) => Number(p.find((x) => x.type === t).value);
    return { y: g("year"), m: g("month"), d: g("day"), hh: String(g("hour")).padStart(2, "0"), mm: String(g("minute")).padStart(2, "0") };
  };
  const dayNo = (q) => Date.UTC(q.y, q.m - 1, q.d) / 86400000;  // calendar day number of wall-clock parts
  const dt = (v) => {
    if (!v) return "–";
    const s = String(v).replace(" ", "T");
    const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z");
    if (isNaN(d)) return String(v).slice(0, 16);
    const x = parts(d), n = parts(new Date());
    const dx = dayNo(x), dn = dayNo(n), wd = (k) => (new Date(k * 86400000).getUTCDay() + 6) % 7;  // Monday = 0
    const diff = dx - dn, weeks = Math.floor((dx - wd(dx) - (dn - wd(dn))) / 7);
    const name = DAYS[new Date(dx * 86400000).getUTCDay()];
    const yr = x.y !== n.y ? ` ${x.y}` : "";
    const date = `${x.d} ${MON[x.m - 1]}${yr} ${x.hh}:${x.mm}`;
    if (diff === 0) return `Today, ${name.slice(0, 3)} ${date}`;
    if (diff === -1) return `Yesterday, ${name.slice(0, 3)} ${date}`;
    if (diff === 1) return `Tomorrow, ${name.slice(0, 3)} ${date}`;
    if (weeks === 0) return `${name}, ${date}`;
    if (weeks === -1) return `Last week ${name}, ${date}`;
    if (weeks === 1) return `Next week ${name}, ${date}`;
    return `${name.slice(0, 3)} ${date}`;
  };
  // Which D/W/M candle a stored candle start is, the way a chart labels it: candles open at 17:00 New York, so the
  // D candle that opens Tue 22:00 WAT is Wednesday's (owner 2026-10-15: "it said tap on Tuesday ... I can't see").
  const nyParts = (d) => {
    const p = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", year: "numeric", month: "numeric",
      day: "numeric", hour: "2-digit", hourCycle: "h23" }).formatToParts(d);
    const g = (t) => Number(p.find((x) => x.type === t).value);
    return { y: g("year"), m: g("month"), d: g("day"), h: g("hour") };
  };
  const candleDay = (v, tf) => {
    if (!v) return "–";
    const s = String(v).replace(" ", "T");
    const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z");
    if (isNaN(d)) return String(v).slice(0, 10);
    const q = nyParts(d);
    let k = Date.UTC(q.y, q.m - 1, q.d) / 86400000 + (q.h >= 17 ? 1 : 0);  // trading day number
    const n = nyParts(new Date()), today = Date.UTC(n.y, n.m - 1, n.d) / 86400000 + (n.h >= 17 ? 1 : 0);
    const day = new Date(k * 86400000);
    if (tf === "M") return `${MON[day.getUTCMonth()]} ${day.getUTCFullYear()} (MN1 candle)`;
    if (tf === "W") { k += (8 - day.getUTCDay()) % 7; }  // weekly candle: the Monday it trades from
    const w = new Date(k * 86400000), name = DAYS[w.getUTCDay()];
    const yr = w.getUTCFullYear() !== new Date(today * 86400000).getUTCFullYear() ? ` ${w.getUTCFullYear()}` : "";
    const date = `${w.getUTCDate()} ${MON[w.getUTCMonth()]}${yr}`;
    if (tf === "W") return `week of Mon ${date} (W1 candle)`;
    const wd = (x) => (new Date(x * 86400000).getUTCDay() + 6) % 7, diff = k - today;
    const weeks = Math.floor((k - wd(k) - (today - wd(today))) / 7);
    const rel = diff === 0 ? `Today, ${name.slice(0, 3)}` : diff === -1 ? `Yesterday, ${name.slice(0, 3)}`
      : weeks === 0 ? `${name},` : weeks === -1 ? `Last week ${name},` : name.slice(0, 3);
    return `${rel} ${date} (D1 candle)`;
  };
  // continuation breaks 'level@YYYY-MM-DD HH:MM;...' (candle start, UTC) -> "0.92999 · H4 close Today, Thu 15 Oct 14:00"
  // 'level@time[@n@first]': one candle that cleared n V's (A's) is one break
  const contBreaks = (r) => String(r.cont_breaks || "").split(";").filter((x) => x.includes("@")).map((x) => {
    const [lv, t, n, first] = x.split("@");
    const many = Number(n) > 1 ? ` (cleared ${n}: ${num(first)} → ${num(lv)})` : "";
    if (r.story === "D") {
      const d = new Date(t.replace(" ", "T") + "Z"); d.setUTCHours(d.getUTCHours() + 4);
      return `${num(lv)}${many} · H4 close ${dt(d.toISOString())}`;
    }
    return `${num(lv)}${many} · ${r.story === "W" ? "D1" : "W1"} close ${candleDay(t, r.story === "W" ? "D" : "W")}`;
  });
  const KIND = { A: "A", V: "V", OC: "OC (open-close)", sweep: "sweep of previous candle", align: "alignment swing" };
  const kl = (r) => r.level_kind === "flip" ? `${KIND[r.level_src] || "KL"} · flipped` : (KIND[r.level_kind] || r.level_kind || "");

  const dur = (s) => {
    if (s === null || s === undefined) return "–";
    const a = Math.abs(s);
    const t = a < 120 ? `${Math.round(a)}s` : a < 7200 ? `${Math.round(a / 60)}m` : `${(a / 3600).toFixed(1)}h`;
    return s < 0 ? `-${t}` : t;
  };

  function msg(text, err) {
    const m = $("#msg");
    if (!text) { m.hidden = true; return; }
    m.hidden = false; m.textContent = text; m.className = "msg" + (err ? " err" : "");
  }

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      ...opts,
      headers: { "Content-Type": "application/json", "X-Telegram-Init-Data": initData, ...(opts.headers || {}) },
    });
    if (!res.ok) {
      let d = res.statusText;
      try { d = (await res.json()).detail || d; } catch (_) {}
      throw new Error(`${res.status}: ${typeof d === "string" ? d : JSON.stringify(d)}`);
    }
    return res.json();
  }

  const field = (k, v) => `<div><span>${esc(k)}</span>${esc(v)}</div>`;
  const empty = (t) => `<div class="empty">${esc(t)}</div>`;

  // ---------------- Bias
  // Standing bias (slk/standing.py): stays after a target, ends on a confirmed opposite story or an invalidation
  function renderState(st) {
    const pf = $("#f-pair").value, sf = $("#f-story").value;
    const rows = (st || []).filter((b) => (!pf || b.pair === pf) && (!sf || b.story === sf));
    $("#bias-state").innerHTML = rows.length ? `
      <div class="card summary">
        <div class="top"><span class="title">Current bias</span><span class="tag">${esc(rows.filter((b) => b.side).length)} pairs/TFs</span></div>
        ${rows.map((b) => `<div class="bias-row"><span><b>${esc(b.pair)}</b> · ${esc(b.chain || b.story)}</span>
          <span class="${esc(b.side || "")}">${esc(b.bias)}</span>
          <span class="muted">${b.side ? `since ${esc(candleDay(b.since, "D").replace(" (D1 candle)", ""))}${b.stories > 1 ? ` · ${esc(b.stories)} stories` : ""} · ${esc(b.state)}` : esc(b.state)}</span></div>`).join("")}
        <div class="muted">A bias stays after its target is reached (Kevin: "we are still bearish ... price is not ready to buy yet"). It changes only when a story the other way confirms, or a close back through the level invalidates it.</div>
      </div>` : "";
  }

  async function loadBias() {
    const q = new URLSearchParams({ pair: $("#f-pair").value, story: $("#f-story").value, status: $("#f-status").value });
    const [rows, st] = await Promise.all([api(`/api/bias?${q}`), api("/api/bias/state").catch(() => null)]);
    renderState(st);
    const sel = $("#f-pair");
    const known = new Set([...sel.options].map((o) => o.value));
    const pairs = new Set([...(settings.pairs || "").split(",").filter(Boolean), ...rows.map((r) => r.pair)]);
    [...pairs].sort().forEach((p) => { if (!known.has(p)) sel.add(new Option(p, p)); });
    $("#bias-list").innerHTML = rows.length ? rows.map((r) => `
      <div class="card">
        <div class="top"><span class="title"><span class="${esc(r.side)}">${esc(r.side)}</span> · ${esc(r.pair)} · ${esc(r.chain || r.story)}</span>
          <span>${Number(r.no_trade) ? `<span class="tag notrade" title="${esc(r.no_trade_reason || "")}">NO_TRADE</span> ` : ""}<span class="tag">${esc(r.status)}</span></span></div>
        ${Number(r.no_trade) ? `<div class="muted">No trade: ${esc(r.no_trade_reason || "filter")}</div>` : ""}
        ${(r.trend === "up" || r.trend === "down") && (r.side === "BUY") !== (r.trend === "up") ? `<div class="muted">↩ Pullback: against the ${esc({ D: "D1", W: "W1", M: "MN1" }[r.story] || r.story)} structure (${esc(r.trend === "up" ? "bullish" : "bearish")}), a retracement inside it, not a bias change</div>` : ""}
        <div class="grid">
          ${field("Level", `${num(r.level)} ${kl(r)}`)}${field("Point B", num(r.point_b))}
          ${r.level_candle ? field("KL candle", candleDay(r.level_candle, r.story)) : ""}
          ${field("Target", num(r.target))}${field("Invalid", num(r.invalidation))}
          ${field("Tap candle", candleDay(r.tap_time, r.story))}${field("Confirm", dt(r.confirm_time))}
          ${field("Rule", r.rule || "standard")}${field("Updated", dt(r.updated_at))}
          ${r.breakout_time ? field("Breakout (open)", dt(r.breakout_time)) : ""}
          ${r.next_day == null ? "" : field("Next Day Rule", Number(r.next_day) ? "✅ next day" : "⚠ same day")}
        </div>${contBreaks(r).length ? `<div class="muted">Continuation breaks (after point B):<br>${contBreaks(r).map(esc).join("<br>")}</div>` : ""}${Number(r.retrace) ? `<div class="muted">⚠ Retrace: closed back beyond point B on the breakout day</div>` : ""}${r.end_reason ? `<div class="muted">Ended: ${esc(r.end_reason)}</div>` : ""}${r.line_end ? `<div class="muted">Story line ended after the target: ${esc(candleDay(r.line_end, r.story))} closed back through the level</div>` : (r.status === "TARGET_HIT" ? `<div class="muted">After the target: watching for the next break (continues) or a close back through the level (ends)</div>` : "")}</div>`).join("") : empty("No stories");
  }

  // ---------------- Entries (+ paper results of filled signals: slk.entry.paper_track, not broker trades)
  const OUTCOME = { TP1_HIT: "win", TP2_HIT: "win", SL_HIT: "loss", EXPIRED: "exp", TRIGGERED: "open", CANCELLED: "off", MISSED: "off" };
  const rr = (v) => (v === null || v === undefined || v === "" ? "–" : `${Number(v) > 0 ? "+" : ""}${Number(Number(v).toFixed(2))}R`);
  const rcls = (v) => (v === null || v === undefined ? "" : Number(v) > 0 ? "good" : Number(v) < 0 ? "bad" : "");
  const pct = (v) => (v === null || v === undefined ? "–" : `${v}%`);

  function renderSummary(s) {
    const m = (k, n) => { const x = (s.by_model || {})[k] || {}; return `${n}: ${x.closed || 0} closed · ${x.wins || 0}W/${x.losses || 0}L · ${rr(x.total_r)}`; };
    $("#entries-summary").innerHTML = `
      <div class="card summary">
        <div class="top"><span class="title">${esc(s.label || "Paper results (signals)")}</span><span class="tag">${esc(s.open || 0)} open</span></div>
        <div class="stats">
          <div><b>${esc(s.closed)}</b><span>closed</span></div>
          <div><b class="good">${esc(s.wins)}</b><span>wins</span></div>
          <div><b class="bad">${esc(s.losses)}</b><span>losses</span></div>
          <div><b>${esc(pct(s.win_pct))}</b><span>win%</span></div>
          <div><b class="${rcls(s.total_r)}">${esc(rr(s.total_r))}</b><span>total R</span></div>
        </div>
        <div class="muted">${esc(m("continuation", "Continuation"))}<br>${esc(m("qmr", "QMR"))}</div>
        <div class="muted">Bot signals tracked on closed H1 candles, not broker trades (those are under Orders). Win = TP1 reached, loss = stop before TP1${s.expired ? `, ${esc(s.expired)} expired` : ""}. R = exit at TP1; holding for TP2: ${esc(rr(s.total_r_tp2))} over ${esc(s.closed_tp2 || 0)} trades.</div>
      </div>`;
  }

  async function loadEntries() {
    const q = new URLSearchParams({ status: $("#f-estatus").value });
    const [rows, summary] = await Promise.all([api(`/api/entries?${q}`), api("/api/entries/summary").catch(() => null)]);
    if (summary) renderSummary(summary); else $("#entries-summary").innerHTML = "";
    const canApprove = settings.auto_trade === "confirm" && settings.kill_switch !== "on";
    $("#entries-list").innerHTML = rows.length ? rows.map((r) => `
      <div class="card">
        <div class="top"><span class="title">${esc(r.pair)} ${esc(r.tf || "")} <span class="${esc(r.side)}">${esc(r.side)}</span> ${esc(r.model === "qmr" ? "QMR" : "Continuation")}</span>
          <span class="tag ${esc(OUTCOME[r.status] || "")}">${esc(r.status)}</span></div>
        <div class="grid">
          ${field("Entry", num(r.entry))}${field("Stop", num(r.stop))}
          ${field("TP1", num(r.tp1))}${field("TP2", num(r.tp2))}
          ${field("Bias #", r.bias_id)}${field("Created", dt(r.created_at))}${field("Alerted", dt(r.alerted_at))}
          ${r.filled_at ? field("Filled", dt(r.filled_at)) : ""}
          ${r.result_r !== null && r.result_r !== undefined ? `<div><span>R (TP1 exit)</span><b class="${rcls(r.result_r)}">${esc(rr(r.result_r))}</b></div>` : ""}
          ${r.result_r_tp2 !== null && r.result_r_tp2 !== undefined ? `<div><span>R (TP2 hold)</span><b class="${rcls(r.result_r_tp2)}">${esc(rr(r.result_r_tp2))}</b></div>` : ""}
          ${r.hit_price !== null && r.hit_price !== undefined ? field("Hit price", num(r.hit_price)) : ""}
          ${r.closed_at ? field("Closed", dt(r.closed_at)) : ""}
        </div>
        ${OUTCOME[r.status] && r.filled_at ? `<div class="muted">Paper result (signal), not a broker trade</div>` : ""}
        ${r.status === "PENDING" && canApprove ? `<button class="approve" data-id="${esc(r.id)}">Confirm trade</button>` : ""}
      </div>`).join("") : empty("No entries");
  }

  async function approve(id, btn) {
    const ok = await new Promise((resolve) =>
      tg && tg.showConfirm ? tg.showConfirm(`Approve entry #${id}? The trader job will place it.`, resolve) : resolve(confirm(`Approve entry #${id}?`)));
    if (!ok) return;
    btn.disabled = true;
    try {
      await api(`/api/entries/${id}/approve`, { method: "POST" });
      if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
      msg(`Entry #${id} approved`);
      await loadEntries();
    } catch (e) { msg(e.message, true); btn.disabled = false; }
  }

  // ---------------- Orders
  async function loadOrders() {
    const rows = await api("/api/orders");
    $("#orders-list").innerHTML = rows.length ? rows.map((r) => {
      const pnl = r.pnl === null || r.pnl === undefined ? "–" : Number(r.pnl).toFixed(2);
      return `<div class="card">
        <div class="top"><span class="title">#${esc(r.id)} · entry ${esc(r.entry_id)}</span><span class="tag">${esc(r.status)}</span></div>
        <div class="grid">
          ${field("Volume", r.volume)}${field("Position", r.ctrader_position_id ?? "–")}
          ${field("Opened", dt(r.opened_at))}${field("Closed", dt(r.closed_at))}
          <div><span>PnL</span><b class="${r.pnl > 0 ? "good" : r.pnl < 0 ? "bad" : ""}">${esc(pnl)}</b></div>
          ${field("Client id", r.client_order_id)}
        </div></div>`;
    }).join("") : empty("No orders");
  }

  // ---------------- Settings (form built from /api/settings/schema = slk/settings.py)
  let schema = null;
  const fid = (n) => `s-${n}`;
  const csv = (v) => String(v || "").split(/[,\s;]+/).map((x) => x.trim().toUpperCase()).filter(Boolean);
  const ladder = (v) => Object.fromEntries(String(v || "").split(";").filter((p) => p.includes("="))
    .map((p) => { const [k, tfs] = p.split("="); return [k.trim(), tfs.trim()]; }));

  function renderField(s, v) {
    const id = fid(s.name);
    const label = s.name.replace(/_/g, " ");
    let input;
    if (s.type === "bool") {
      return `<label class="row"><span>${esc(label)}</span><input type="checkbox" id="${id}" class="switch" ${v === "on" ? "checked" : ""}></label>
        <p class="hint">${esc(s.help)}</p>`;
    }
    if (s.type === "choice") {
      input = `<select id="${id}">${s.choices.map((c) => `<option ${c === v ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>`;
    } else if (s.type === "int" || s.type === "float") {
      const step = s.type === "int" ? 1 : s.max <= 5 ? 0.1 : 1;
      input = `<input type="number" id="${id}" value="${esc(v)}" min="${s.min}" max="${s.max}" step="${step}" inputmode="decimal">`;
    } else if (s.type === "multi" || s.type === "pairs") {
      const on = new Set(csv(v));
      const chips = s.choices.map((c) => `<label><input type="checkbox" class="${id}-c" value="${esc(c)}" ${on.has(String(c).toUpperCase()) ? "checked" : ""}> ${esc(c)}</label>`).join("");
      const extra = s.type === "pairs" ? `<input type="text" id="${id}-x" placeholder="other symbols, comma separated" autocapitalize="characters" value="${esc([...on].filter((x) => !s.choices.map((c) => String(c).toUpperCase()).includes(x)).join(","))}">` : "";
      return `<div class="col"><span>${esc(label)}</span><div class="chips">${chips}</div>${extra}</div><p class="hint">${esc(s.help)}</p>`;
    } else if (s.type === "ladder") {
      const l = ladder(v);
      input = ["D", "W", "M"].map((k) => `<label class="row"><span>${k}</span><input type="text" id="${id}-${k}" value="${esc(l[k] || "")}" autocapitalize="characters"></label>`).join("");
      return `<div class="col"><span>${esc(label)}</span>${input}</div><p class="hint">${esc(s.help)}</p>`;
    } else {
      input = `<input type="text" id="${id}" value="${esc(v)}">`;
    }
    return `<label class="row"><span>${esc(label)}</span>${input}</label><p class="hint">${esc(s.help)}</p>`;
  }

  function readField(s) {
    const id = fid(s.name);
    if (s.type === "bool") return $(`#${id}`).checked ? "on" : "off";
    if (s.type === "multi" || s.type === "pairs") {
      const v = [...document.querySelectorAll(`.${id}-c:checked`)].map((c) => c.value);
      if (s.type === "pairs") v.push(...csv($(`#${id}-x`).value));
      return v.join(",");
    }
    if (s.type === "ladder") return ["D", "W", "M"].map((k) => `${k}=${$(`#${id}-${k}`).value.trim()}`).filter((x) => !x.endsWith("=")).join(";");
    return String($(`#${id}`).value).trim();
  }

  async function loadSettings() {
    if (!schema) schema = await api("/api/settings/schema");
    settings = await api("/api/settings");
    $("#settings-fields").innerHTML = schema.groups.map((g) => `
      <fieldset class="card form"><legend>${esc(g)}</legend>
        ${schema.settings.filter((s) => s.group === g).map((s) => renderField(s, settings[s.name])).join("")}
      </fieldset>`).join("");
  }

  async function saveSettings(ev) {
    ev.preventDefault();
    const body = Object.fromEntries(schema.settings.map((s) => [s.name, readField(s)]));
    try {
      settings = await api("/api/settings", { method: "POST", body: JSON.stringify(body) });
      await loadSettings();
      if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
      msg("Settings saved. The live runner uses them from its next hourly run.");
    } catch (e) { msg(e.message, true); }
  }

  // ---------------- Status
  async function loadRuns() {
    const rows = await api("/api/runs");
    $("#runs-list").innerHTML = rows.length ? rows.map((r) => {
      const okc = r.ok === null || r.ok === undefined ? "" : r.ok ? "good" : "bad";
      const late = r.delay_s !== null && r.delay_s > 300 ? "late" : "";
      return `<div class="card">
        <div class="top"><span class="title">${esc(r.job)}</span>
          <span class="tag ${okc}">${r.ok === null || r.ok === undefined ? "running" : r.ok ? "ok" : "failed"}</span></div>
        <div class="grid">
          ${field("Planned", dt(r.planned_at))}${field("Started", dt(r.started_at))}
          <div><span>Delay</span><b class="${late}">${esc(dur(r.delay_s))}</b></div>
          ${field("Took", dur(r.duration_s))}
        </div>
        ${r.note ? `<div class="hint" style="margin-top:6px">${esc(r.note)}</div>` : ""}
      </div>`;
    }).join("") : empty("No runs yet");
  }

  // ---------------- Tabs
  const loaders = { bias: loadBias, entries: loadEntries, orders: loadOrders, settings: loadSettings, status: loadRuns };
  let current = "bias";
  async function show(tab) {
    current = tab;
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
    document.querySelectorAll("main section").forEach((s) => { s.hidden = s.id !== tab; });
    msg("");
    try { await loaders[tab](); } catch (e) { msg(e.message, true); }
  }

  document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
  ["#f-pair", "#f-story", "#f-status"].forEach((s) => $(s).addEventListener("change", () => show("bias")));
  $("#f-estatus").addEventListener("change", () => show("entries"));
  $("#entries-list").addEventListener("click", (e) => {
    const b = e.target.closest("button.approve");
    if (b) approve(b.dataset.id, b);
  });
  $("#settings-form").addEventListener("submit", saveSettings);

  if (!initData) {
    msg("Open this page from the Telegram bot (Mini App). Direct browser access is not allowed.", true);
    return;
  }
  loadSettings().catch(() => {}).finally(() => show(current));
})();
