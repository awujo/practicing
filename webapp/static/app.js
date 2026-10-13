(() => {
  const tg = window.Telegram && window.Telegram.WebApp;
  const initData = (tg && tg.initData) || "";
  if (tg) { tg.ready(); tg.expand(); }
  let settings = {};

  const $ = (s) => document.querySelector(s);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v) => (v === null || v === undefined || v === "" ? "–" : Number(v).toFixed(Number(v) > 50 ? 3 : 5));
  const dt = (v) => (v ? String(v).replace("T", " ").slice(0, 16) : "–");
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
  async function loadBias() {
    const q = new URLSearchParams({ pair: $("#f-pair").value, story: $("#f-story").value, status: $("#f-status").value });
    const rows = await api(`/api/bias?${q}`);
    const sel = $("#f-pair");
    const known = new Set([...sel.options].map((o) => o.value));
    const pairs = new Set([...(settings.pairs || "").split(",").filter(Boolean), ...rows.map((r) => r.pair)]);
    [...pairs].sort().forEach((p) => { if (!known.has(p)) sel.add(new Option(p, p)); });
    $("#bias-list").innerHTML = rows.length ? rows.map((r) => `
      <div class="card">
        <div class="top"><span class="title">${esc(r.pair)} · ${esc(r.story)} <span class="${esc(r.side)}">${esc(r.side)}</span></span>
          <span>${Number(r.no_trade) ? `<span class="tag notrade" title="${esc(r.no_trade_reason || "")}">NO_TRADE</span> ` : ""}<span class="tag">${esc(r.status)}</span></span></div>
        ${Number(r.no_trade) ? `<div class="muted">No trade: ${esc(r.no_trade_reason || "filter")}</div>` : ""}
        <div class="grid">
          ${field("Level", `${num(r.level)} ${r.level_kind || ""}`)}${field("Point B", num(r.point_b))}
          ${field("Target", num(r.target))}${field("Invalid", num(r.invalidation))}
          ${field("Tap", dt(r.tap_time))}${field("Confirm", dt(r.confirm_time))}
          ${field("Updated", dt(r.updated_at))}
        </div></div>`).join("") : empty("No stories");
  }

  // ---------------- Entries
  async function loadEntries() {
    const q = new URLSearchParams({ status: $("#f-estatus").value });
    const rows = await api(`/api/entries?${q}`);
    const canApprove = settings.auto_trade === "confirm" && settings.kill_switch !== "on";
    $("#entries-list").innerHTML = rows.length ? rows.map((r) => `
      <div class="card">
        <div class="top"><span class="title">${esc(r.pair)} ${esc(r.tf || "")} <span class="${esc(r.side)}">${esc(r.side)}</span></span>
          <span class="tag">${esc(r.status)}</span></div>
        <div class="grid">
          ${field("Entry", num(r.entry))}${field("Stop", num(r.stop))}
          ${field("TP1", num(r.tp1))}${field("TP2", num(r.tp2))}
          ${field("Bias #", r.bias_id)}${field("Created", dt(r.created_at))}${field("Alerted", dt(r.alerted_at))}
        </div>
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
      const chips = s.choices.map((c) => `<label><input type="checkbox" class="${id}-c" value="${esc(c)}" ${on.has(c) ? "checked" : ""}> ${esc(c)}</label>`).join("");
      const extra = s.type === "pairs" ? `<input type="text" id="${id}-x" placeholder="other symbols, comma separated" autocapitalize="characters" value="${esc([...on].filter((x) => !s.choices.includes(x)).join(","))}">` : "";
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
