const CATEGORY_ORDER = ["rf", "pa", "supply", "cooling", "control"];
const CATEGORY_LABELS = {
  rf: "RF",
  pa: "PA / Drive",
  supply: "Supplies",
  cooling: "Cooling",
  control: "Control",
};

const CHART_COLORS = [
  "#3b82f6",
  "#22d3ee",
  "#f59e0b",
  "#22c55e",
  "#a78bfa",
  "#fb7185",
  "#38bdf8",
  "#94a3b8",
  "#eab308",
  "#f97316",
];

const CHART_PROFILES = {
  nautel: [
    ["fwd_pwr_w", "Forward power"],
    ["rfl_pwr_w", "Reflected power"],
    ["vswr", "VSWR"],
    ["heatsink_temp_c", "Heatsink temperature"],
    ["pa_volts_v", "PA volts"],
    ["pa_current_1_a", "PA 1 current"],
    ["plus48_v", "+48V (LVPS)"],
    ["fan1_rpm", "Fan 1 RPM"],
  ],
  flexiva: [
    ["fwd_pwr_w", "Forward power"],
    ["rfl_pwr_w", "Reflected power"],
    ["vswr", "VSWR"],
    ["ipa_power_w", "IPA power"],
    ["heatsink_temp_c", "Front / heatsink temp"],
    ["front_temp_c", "Front temperature"],
    ["board_temp_c", "Board temperature"],
  ],
  aat: [
    ["fwd_pwr_w", "Forward power"],
    ["rfl_pwr_w", "Reflected power"],
    ["vswr", "VSWR"],
    ["heatsink_temp_c", "Heatsink temperature"],
    ["ambient_temp_c", "Ambient temperature"],
    ["pa_volts_v", "DC Voltage 1"],
    ["pa_current_1_a", "AC Current 1"],
    ["cur2_a", "AC Current 2"],
    ["cur3_a", "AC Current 3"],
  ],
  crown: [
    ["fwd_pwr_w", "Forward power"],
    ["rfl_pwr_w", "Reflected power"],
    ["vswr", "VSWR"],
    ["heatsink_temp_c", "Heatsink temperature"],
    ["ambient_temp_c", "Ambient temperature"],
    ["pa_volts_v", "Voltage 1"],
    ["volt2", "Voltage 2"],
    ["pa_current_1_a", "Current 1"],
    ["cur2", "Current 2"],
  ],
};

let knownAlertKeys = new Set();
let detailModel = "";

function fmtNum(value, digits = 1) {
  if (value == null || Number.isNaN(value)) return "—";
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtPower(w) {
  if (w == null) return "—";
  if (Math.abs(w) >= 1000) return `${fmtNum(w / 1000, 2)} kW`;
  return `${fmtNum(w, 1)} W`;
}

function fmtMeter(value, unit) {
  if (value == null) return "—";
  if (unit === "W") return fmtPower(value);
  if (unit === "rpm") return `${fmtNum(value, 0)} rpm`;
  if (unit === "°C") return `${fmtNum(value, 1)} °C`;
  if (unit === "V") return `${fmtNum(value, 2)} V`;
  if (unit === "A") return `${fmtNum(value, 2)} A`;
  if (unit === "%") return `${fmtNum(value, 2)} %`;
  if (!unit) return fmtNum(value, Number.isInteger(value) ? 0 : 2);
  return `${fmtNum(value, 2)} ${unit}`;
}

function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function statusBadge(status) {
  return `<span class="badge badge-${status}">${status}</span>`;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function modelFamily(model) {
  const m = String(model || "").toLowerCase();
  if (m.includes("flexiva") || m.includes("fax") || m.includes("gatesair")) return "flexiva";
  if (m.includes("aat") || m.includes("american")) return "aat";
  if (m.includes("crown") || m.includes("ecreso") || m.includes("audemat") || m.includes("fmngip")) {
    return "crown";
  }
  return "nautel";
}

function chartProfileFor(model) {
  return CHART_PROFILES[modelFamily(model)] || CHART_PROFILES.nautel;
}

async function fetchJson(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text();
    let detail = text || res.statusText;
    try {
      const parsed = JSON.parse(text);
      if (parsed?.detail) detail = typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
    } catch (_err) {
      /* keep raw text */
    }
    throw new Error(detail);
  }
  return res.json();
}

function showToast(title, body, isAlert = false) {
  const el = document.getElementById("toast");
  if (!el) return;
  document.getElementById("toast-title").textContent = title;
  document.getElementById("toast-body").textContent = body;
  el.classList.toggle("alert", isAlert);
  el.classList.add("visible");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => el.classList.remove("visible"), 5000);
}

function updateTestEmailButton(alerts) {
  const btn = document.getElementById("test-email-btn");
  if (!btn) return;
  const ready = !!alerts?.email_ready;
  btn.disabled = !ready;
  btn.title = ready
    ? "Send a test email"
    : alerts?.email_reason || "Email not configured";
}

async function ackAlert(key) {
  const data = await fetchJson("/api/alerts/ack", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  });
  renderAlerts(data.alerts);
  showToast("Acknowledged", key);
}

async function snoozeAlert(key, minutes = 60) {
  const data = await fetchJson("/api/alerts/snooze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, minutes }),
  });
  renderAlerts(data.alerts);
  showToast("Snoozed", `${key} for ${minutes}m`);
}

async function sendTestEmail() {
  try {
    const data = await fetchJson("/api/alerts/test", { method: "POST" });
    renderAlerts(data.alerts);
    showToast("Test email", "Sent successfully");
  } catch (err) {
    showToast("Test email failed", err.message || String(err), true);
  }
}

function renderAlertEvents(alerts) {
  const list = document.getElementById("alert-events");
  if (!list) return;
  const events = alerts?.recent_events || [];
  if (!events.length) {
    list.innerHTML = `<li class="empty">No recent events</li>`;
    return;
  }
  list.innerHTML = events
    .slice()
    .reverse()
    .map(
      (ev) => `
      <li>
        <span class="event-kind">${escapeHtml(ev.kind || "")}</span>
        <span>${escapeHtml(ev.message || "")}</span>
        <span class="event-time">${escapeHtml(fmtTime(ev.timestamp))}</span>
      </li>`
    )
    .join("");
}

function renderAlerts(alerts) {
  const banner = document.getElementById("alert-banner");
  const list = document.getElementById("alert-list");
  if (!banner || !list) return;

  updateTestEmailButton(alerts);
  renderAlertEvents(alerts);

  const active = alerts?.active || [];
  const nextKeys = new Set(active.map((a) => a.key));
  for (const item of active) {
    if (!knownAlertKeys.has(item.key)) {
      showToast("Alert", item.message, true);
    }
  }
  knownAlertKeys = nextKeys;

  const eventsEl = document.getElementById("alert-events");
  const hasEvents = !!eventsEl && (alerts?.recent_events || []).length > 0;
  if (!active.length && !hasEvents) {
    banner.classList.remove("visible");
    list.innerHTML = "";
    return;
  }

  banner.classList.add("visible");
  if (!active.length) {
    list.innerHTML = `<li class="empty">No active alerts</li>`;
    return;
  }

  list.innerHTML = active
    .map(
      (a) => `
      <li class="alert-row">
        <span class="alert-msg">${escapeHtml(a.message)}</span>
        <span class="alert-actions">
          <button type="button" data-ack="${escapeHtml(a.key)}">Ack</button>
          <button type="button" data-snooze="${escapeHtml(a.key)}">Snooze 1h</button>
        </span>
      </li>`
    )
    .join("");

  list.querySelectorAll("[data-ack]").forEach((btn) => {
    btn.addEventListener("click", () => {
      ackAlert(btn.getAttribute("data-ack")).catch((err) =>
        showToast("Ack failed", err.message || String(err), true)
      );
    });
  });
  list.querySelectorAll("[data-snooze]").forEach((btn) => {
    btn.addEventListener("click", () => {
      snoozeAlert(btn.getAttribute("data-snooze"), 60).catch((err) =>
        showToast("Snooze failed", err.message || String(err), true)
      );
    });
  });
}

function renderSummary(summary) {
  const el = document.getElementById("summary");
  if (!el || !summary) return;
  el.innerHTML = [
    ["Total", summary.total],
    ["Online", summary.online],
    ["Degraded", summary.degraded],
    ["Offline", summary.offline],
    ["TX Alarms", summary.active_alarms],
  ]
    .map(
      ([label, value]) => `
      <div class="summary-card">
        <div class="label">${label}</div>
        <div class="value">${value}</div>
      </div>`
    )
    .join("");
}

function renderFleetCard(tx, wall) {
  const alarmClass = tx.active_alarm_count ? "alarm-count" : "alarm-count zero";
  const err = tx.error
    ? `<div class="error-text">${escapeHtml(tx.error)}</div>`
    : "";
  if (wall) {
    return `
      <article class="tx-card wall-card status-${escapeHtml(tx.status)}">
        <div class="tx-card-top">
          <div>
            <h2>${escapeHtml(tx.name)}</h2>
            <div class="tx-meta">${escapeHtml(tx.model.toUpperCase())}
              ${tx.location ? " · " + escapeHtml(tx.location) : ""}
            </div>
          </div>
          ${statusBadge(tx.status)}
        </div>
        <dl class="meters wall-meters">
          <div class="meter"><dt>Forward</dt><dd>${fmtPower(tx.fwd_pwr_w)}</dd></div>
          <div class="meter"><dt>VSWR</dt><dd>${fmtNum(tx.vswr, 3)}</dd></div>
          <div class="meter"><dt>Temp</dt><dd>${tx.heatsink_temp_c == null ? "—" : fmtNum(tx.heatsink_temp_c, 1) + " °C"}</dd></div>
          <div class="meter"><dt>RF</dt><dd>${escapeHtml(tx.rf_state_label)}</dd></div>
        </dl>
        <div class="tx-footer">
          <span class="${alarmClass}">${tx.active_alarm_count} alarm${tx.active_alarm_count === 1 ? "" : "s"}</span>
          <span>${escapeHtml(tx.host || "")}</span>
        </div>
      </article>`;
  }

  return `
    <article class="tx-card">
      <div class="tx-card-top">
        <div>
          <h2><a class="tx-name-btn" href="/tx/${encodeURIComponent(tx.tx_id)}">${escapeHtml(tx.name)}</a></h2>
          <div class="tx-meta">${escapeHtml(tx.model.toUpperCase())}
            ${tx.host ? " · " + escapeHtml(tx.host) : ""}
            ${tx.location ? " · " + escapeHtml(tx.location) : ""}
          </div>
        </div>
        ${statusBadge(tx.status)}
      </div>
      <dl class="meters">
        <div class="meter"><dt>Forward</dt><dd>${fmtPower(tx.fwd_pwr_w)}</dd></div>
        <div class="meter"><dt>Reflected</dt><dd>${fmtPower(tx.rfl_pwr_w)}</dd></div>
        <div class="meter"><dt>VSWR</dt><dd>${fmtNum(tx.vswr, 3)}</dd></div>
        <div class="meter"><dt>PA V</dt><dd>${tx.pa_volts_v == null ? "—" : fmtNum(tx.pa_volts_v, 1) + " V"}</dd></div>
        <div class="meter"><dt>Temp</dt><dd>${tx.heatsink_temp_c == null ? "—" : fmtNum(tx.heatsink_temp_c, 1) + " °C"}</dd></div>
        <div class="meter"><dt>RF</dt><dd>${escapeHtml(tx.rf_state_label)}</dd></div>
      </dl>
      ${err}
      <div class="tx-footer">
        <span class="${alarmClass}">${tx.active_alarm_count} alarm${tx.active_alarm_count === 1 ? "" : "s"}</span>
        <span>${fmtTime(tx.timestamp)}</span>
      </div>
    </article>`;
}

function renderFleet(data, wall = false) {
  renderSummary(data.summary);
  renderAlerts(data.alerts);
  const grid = document.getElementById("fleet");
  if (!grid) return;

  if (!data.transmitters?.length) {
    grid.innerHTML = `<p class="empty">No transmitters configured.</p>`;
    return;
  }

  grid.innerHTML = data.transmitters.map((tx) => renderFleetCard(tx, wall)).join("");
}

async function loadFleet(wall = false) {
  const data = await fetchJson("/api/transmitters");
  renderFleet(data, wall);
  const updated = document.getElementById("updated");
  if (updated) updated.textContent = `Updated ${fmtTime(new Date().toISOString())}`;
}

async function pollFleet() {
  const data = await fetchJson("/api/poll", { method: "POST" });
  renderFleet(data, false);
  const updated = document.getElementById("updated");
  if (updated) updated.textContent = `Updated ${fmtTime(new Date().toISOString())}`;
}

function renderDetailMeters(tx) {
  const root = document.getElementById("meters");
  if (!root) return;

  const meters = (tx.meters || []).filter(
    (m) => !["rf_state", "local_remote", "tx_on", "remote_enable"].includes(m.key)
  );
  if (!meters.length) {
    root.innerHTML = `
      <dl class="meter-row">
        <div class="meter-big"><dt>Forward Power</dt><dd>${fmtPower(tx.fwd_pwr_w)}</dd></div>
        <div class="meter-big"><dt>Reflected Power</dt><dd>${fmtPower(tx.rfl_pwr_w)}</dd></div>
        <div class="meter-big"><dt>VSWR</dt><dd>${fmtNum(tx.vswr, 3)}</dd></div>
        <div class="meter-big"><dt>Heatsink</dt><dd>${tx.heatsink_temp_c == null ? "—" : fmtNum(tx.heatsink_temp_c, 1) + " °C"}</dd></div>
        <div class="meter-big"><dt>RF State</dt><dd>${escapeHtml(tx.rf_state_label)}</dd></div>
        <div class="meter-big"><dt>Control</dt><dd>${escapeHtml(tx.local_remote_label)}</dd></div>
      </dl>`;
    return;
  }

  const byCat = {};
  for (const meter of meters) {
    (byCat[meter.category] ||= []).push(meter);
  }

  const controlBits = `
    <div class="meter-group">
      <h3>Control</h3>
      <dl class="meter-row">
        <div class="meter-big"><dt>RF State</dt><dd>${escapeHtml(tx.rf_state_label)}</dd></div>
        <div class="meter-big"><dt>Local/Remote</dt><dd>${escapeHtml(tx.local_remote_label)}</dd></div>
      </dl>
    </div>`;

  root.innerHTML =
    CATEGORY_ORDER.filter((cat) => byCat[cat]?.length)
      .map((cat) => {
        const items = byCat[cat]
          .map(
            (m) => `
            <div class="meter-big">
              <dt>${escapeHtml(m.label)}</dt>
              <dd>${fmtMeter(m.value, m.unit)}</dd>
            </div>`
          )
          .join("");
        return `
          <div class="meter-group">
            <h3>${CATEGORY_LABELS[cat] || cat}</h3>
            <dl class="meter-row">${items}</dl>
          </div>`;
      })
      .join("") + controlBits;
}

function renderDetail(tx) {
  detailModel = tx.model || "";
  document.getElementById("tx-name").textContent = tx.name;
  document.getElementById("tx-status").innerHTML = statusBadge(tx.status);
  document.getElementById("tx-meta").textContent = [
    tx.model.toUpperCase(),
    tx.host || "no host",
    tx.location,
    tx.local_remote_label,
  ]
    .filter(Boolean)
    .join(" · ");

  renderDetailMeters(tx);

  const alarmList = document.getElementById("alarms");
  if (!tx.alarms?.length) {
    alarmList.innerHTML = `<li class="empty">No alarm OIDs returned</li>`;
  } else {
    alarmList.innerHTML = tx.alarms
      .map(
        (a) =>
          `<li class="${a.active ? "active" : ""}"><span>${escapeHtml(a.label)}</span><span>${a.active ? "ACTIVE" : "clear"}</span></li>`
      )
      .join("");
  }

  const err = document.getElementById("tx-error");
  if (tx.error) {
    err.textContent = tx.error;
    err.hidden = false;
  } else {
    err.hidden = true;
  }

  const aui = document.getElementById("aui-link");
  if (tx.aui_url) {
    aui.href = tx.aui_url;
    aui.textContent = tx.aui_label || "Open AUI";
    aui.hidden = false;
  } else {
    aui.hidden = true;
  }
}

function drawChart(canvas, points, key, color) {
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const values = points
    .map((p) => ({ t: new Date(p.timestamp).getTime(), v: p[key] }))
    .filter((p) => p.v != null && !Number.isNaN(p.v));

  ctx.fillStyle = "#1a2332";
  ctx.fillRect(0, 0, width, height);

  if (values.length < 2) {
    ctx.fillStyle = "#8b9cb3";
    ctx.font = "13px Segoe UI, sans-serif";
    ctx.fillText("Not enough history yet", 16, height / 2);
    return;
  }

  const pad = { top: 16, right: 12, bottom: 28, left: 48 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const tMin = values[0].t;
  const tMax = values[values.length - 1].t;
  let vMin = Math.min(...values.map((p) => p.v));
  let vMax = Math.max(...values.map((p) => p.v));
  if (vMin === vMax) {
    vMin -= 1;
    vMax += 1;
  }
  const span = vMax - vMin;
  vMin -= span * 0.08;
  vMax += span * 0.08;

  const xOf = (t) => pad.left + ((t - tMin) / (tMax - tMin || 1)) * plotW;
  const yOf = (v) => pad.top + (1 - (v - vMin) / (vMax - vMin || 1)) * plotH;

  ctx.strokeStyle = "#2d3a4f";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (plotH * i) / 4;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(width - pad.right, y);
    ctx.stroke();
    const val = vMax - ((vMax - vMin) * i) / 4;
    ctx.fillStyle = "#8b9cb3";
    ctx.font = "11px Segoe UI, sans-serif";
    ctx.fillText(fmtNum(val, val >= 100 ? 0 : 2), 6, y + 4);
  }

  ctx.beginPath();
  values.forEach((p, i) => {
    const x = xOf(p.t);
    const y = yOf(p.v);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.fillStyle = "#8b9cb3";
  ctx.font = "11px Segoe UI, sans-serif";
  ctx.fillText(new Date(tMin).toLocaleString(), pad.left, height - 8);
  const endLabel = new Date(tMax).toLocaleString();
  ctx.fillText(endLabel, width - pad.right - ctx.measureText(endLabel).width, height - 8);
}

function seriesHasData(points, key) {
  return points.some((p) => p[key] != null && !Number.isNaN(Number(p[key])));
}

function updateCsvLink(txId, range) {
  const link = document.getElementById("csv-link");
  if (!link) return;
  const safeRange = range === "30d" ? "30d" : range;
  link.href = `/api/transmitters/${encodeURIComponent(txId)}/history.csv?range=${safeRange}`;
  link.download = `${txId}-history-${safeRange}.csv`;
}

async function loadHistory(txId, range) {
  updateCsvLink(txId, range);
  const data = await fetchJson(
    `/api/transmitters/${encodeURIComponent(txId)}/history?range=${range}`
  );
  const grid = document.getElementById("chart-grid");
  if (!grid) return;

  const profile = chartProfileFor(detailModel);
  const seen = new Set();
  const charts = [];
  for (const [key, label] of profile) {
    if (seen.has(key)) continue;
    seen.add(key);
    if (!seriesHasData(data.points || [], key)) continue;
    charts.push([key, label]);
  }

  if (!charts.length) {
    grid.innerHTML = `<p class="empty">No chartable history for this range yet.</p>`;
    return;
  }

  grid.innerHTML = charts
    .map(
      ([key, label], idx) => `
      <div class="chart-wrap">
        <p class="sub" style="margin-bottom:0.35rem">${escapeHtml(label)}</p>
        <canvas id="chart-${escapeHtml(key)}" height="180" data-key="${escapeHtml(key)}" data-color="${CHART_COLORS[idx % CHART_COLORS.length]}"></canvas>
      </div>`
    )
    .join("");

  for (const [key] of charts) {
    const canvas = document.getElementById(`chart-${key}`);
    if (!canvas) continue;
    drawChart(canvas, data.points, key, canvas.dataset.color || "#3b82f6");
  }
}

function txIdFromPath() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[0] === "tx" ? decodeURIComponent(parts[1] || "") : "";
}

function field(label, name, value, type = "text", attrs = "") {
  return `
    <label class="form-field">
      <span>${escapeHtml(label)}</span>
      <input name="${escapeHtml(name)}" type="${escapeHtml(type)}" value="${escapeHtml(value ?? "")}" ${attrs}>
    </label>`;
}

function checkbox(label, name, checked) {
  return `
    <label class="form-field checkbox">
      <input name="${escapeHtml(name)}" type="checkbox" ${checked ? "checked" : ""}>
      <span>${escapeHtml(label)}</span>
    </label>`;
}

function renderGlobalForm(cfg) {
  const root = document.getElementById("global-form");
  if (!root) return;
  root.innerHTML = [
    field("Poll interval (s)", "poll_interval_seconds", cfg.poll_interval_seconds, "number", "min=5"),
    field("History retention (days)", "history_retention_days", cfg.history_retention_days, "number", "min=1"),
    field("History min interval (s)", "history_min_interval_seconds", cfg.history_min_interval_seconds, "number", "min=5"),
    field("HTTP host", "http_host", cfg.http_host),
    field("HTTP port", "http_port", cfg.http_port, "number", "min=1 max=65535"),
    field("SNMP timeout (s)", "snmp_timeout_seconds", cfg.snmp_timeout_seconds, "number", "min=1 step=0.5"),
    field("SNMP retries", "snmp_retries", cfg.snmp_retries, "number", "min=0"),
  ].join("");
}

function renderAlertsForm(alerts) {
  const root = document.getElementById("alerts-form");
  if (!root) return;
  const a = alerts || {};
  root.innerHTML = [
    checkbox("Email enabled", "email_enabled", !!a.email_enabled),
    field("SMTP host", "smtp_host", a.smtp_host || ""),
    field("SMTP port", "smtp_port", a.smtp_port ?? 587, "number"),
    field("SMTP username", "smtp_username", a.smtp_username || ""),
    field("SMTP password", "smtp_password", a.smtp_password || "", "password"),
    checkbox("SMTP TLS", "smtp_tls", a.smtp_tls !== false),
    field("Email from", "email_from", a.email_from || ""),
    field("Email to (comma-separated)", "email_to", (a.email_to || []).join(", ")),
    field("Cooldown (minutes)", "cooldown_minutes", a.cooldown_minutes ?? 30, "number", "min=1"),
    field("Unreachable polls", "unreachable_polls", a.unreachable_polls ?? 3, "number", "min=1"),
    checkbox("Alert on unreachable", "on_unreachable", a.on_unreachable !== false),
    checkbox("Alert on RF off", "on_rf_off", a.on_rf_off !== false),
    checkbox("Alert on TX alarms", "on_tx_alarms", a.on_tx_alarms !== false),
    field("VSWR threshold", "vswr", a.vswr ?? "", "number", "step=0.01"),
    field("Reflected W threshold", "reflected_w", a.reflected_w ?? "", "number", "step=0.1"),
    field("Heatsink °C threshold", "heatsink_c", a.heatsink_c ?? "", "number", "step=0.1"),
    field("Forward min W", "forward_min_w", a.forward_min_w ?? "", "number", "step=0.1"),
    checkbox("Skip unconfigured hosts", "skip_unconfigured", a.skip_unconfigured !== false),
  ].join("");
}

function renderControlsForm(controls) {
  const root = document.getElementById("controls-form");
  if (!root) return;
  const c = controls || {};
  root.innerHTML = [
    checkbox("Enable RF controls", "controls_enabled", !!c.enabled),
    field("Controls password", "controls_password", c.password || "", "password"),
  ].join("");
}

function emptyTx() {
  return {
    id: "",
    name: "",
    model: "vs300",
    host: "",
    snmp_community: "public",
    snmp_port: 161,
    http_port: 80,
    http_username: "",
    http_password: "",
    location: "",
    alerts: {},
  };
}

function renderTxEditor(transmitters) {
  const root = document.getElementById("tx-editor");
  if (!root) return;
  root.innerHTML = transmitters
    .map((tx, idx) => {
      const overrides = tx.alerts || {};
      return `
      <article class="tx-edit-card" data-idx="${idx}">
        <div class="tx-edit-top">
          <h3>Transmitter ${idx + 1}</h3>
          <button type="button" class="danger" data-remove="${idx}">Remove</button>
        </div>
        <div class="form-grid">
          ${field("ID", `tx.${idx}.id`, tx.id || "")}
          ${field("Name", `tx.${idx}.name`, tx.name || "")}
          <label class="form-field">
            <span>Model</span>
            <select name="tx.${idx}.model">
              ${["vs300", "vx", "aat", "flexiva", "crown"]
                .map(
                  (m) =>
                    `<option value="${m}" ${String(tx.model || "").toLowerCase() === m ? "selected" : ""}>${m}</option>`
                )
                .join("")}
            </select>
          </label>
          ${field("Host", `tx.${idx}.host`, tx.host || "")}
          ${field("Location", `tx.${idx}.location`, tx.location || "")}
          ${field("SNMP community", `tx.${idx}.snmp_community`, tx.snmp_community || "public")}
          ${field("SNMP port", `tx.${idx}.snmp_port`, tx.snmp_port ?? 161, "number")}
          ${field("HTTP port", `tx.${idx}.http_port`, tx.http_port ?? 80, "number")}
          ${field("HTTP username", `tx.${idx}.http_username`, tx.http_username || "")}
          ${field("HTTP password", `tx.${idx}.http_password`, tx.http_password || "", "password")}
          ${field("Alert forward min W", `tx.${idx}.alerts.forward_min_w`, overrides.forward_min_w ?? "", "number", "step=0.1")}
          ${field("Alert reflected W", `tx.${idx}.alerts.reflected_w`, overrides.reflected_w ?? "", "number", "step=0.1")}
          ${field("Alert VSWR", `tx.${idx}.alerts.vswr`, overrides.vswr ?? "", "number", "step=0.01")}
          ${field("Alert heatsink °C", `tx.${idx}.alerts.heatsink_c`, overrides.heatsink_c ?? "", "number", "step=0.1")}
        </div>
      </article>`;
    })
    .join("");

  root.querySelectorAll("[data-remove]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.getAttribute("data-remove"));
      const cfg = collectConfigFromForm();
      cfg.transmitters.splice(idx, 1);
      if (!cfg.transmitters.length) cfg.transmitters.push(emptyTx());
      renderTxEditor(cfg.transmitters);
    });
  });
}

function readInput(name, root = document) {
  const el = root.querySelector(`[name="${name}"]`);
  if (!el) return undefined;
  if (el.type === "checkbox") return el.checked;
  return el.value;
}

function optFloat(value) {
  if (value == null || String(value).trim() === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function collectConfigFromForm() {
  const transmitters = [];
  document.querySelectorAll(".tx-edit-card[data-idx]").forEach((card) => {
    const idx = card.getAttribute("data-idx");
    const alerts = {};
    const fwd = optFloat(readInput(`tx.${idx}.alerts.forward_min_w`, card));
    const rfl = optFloat(readInput(`tx.${idx}.alerts.reflected_w`, card));
    const vswr = optFloat(readInput(`tx.${idx}.alerts.vswr`, card));
    const heat = optFloat(readInput(`tx.${idx}.alerts.heatsink_c`, card));
    if (fwd != null) alerts.forward_min_w = fwd;
    if (rfl != null) alerts.reflected_w = rfl;
    if (vswr != null) alerts.vswr = vswr;
    if (heat != null) alerts.heatsink_c = heat;
    transmitters.push({
      id: String(readInput(`tx.${idx}.id`, card) || "").trim(),
      name: String(readInput(`tx.${idx}.name`, card) || "").trim(),
      model: String(readInput(`tx.${idx}.model`, card) || "vs300").trim(),
      host: String(readInput(`tx.${idx}.host`, card) || "").trim(),
      location: String(readInput(`tx.${idx}.location`, card) || "").trim(),
      snmp_community: String(readInput(`tx.${idx}.snmp_community`, card) || "public"),
      snmp_port: Number(readInput(`tx.${idx}.snmp_port`, card) || 161),
      http_port: Number(readInput(`tx.${idx}.http_port`, card) || 80),
      http_username: String(readInput(`tx.${idx}.http_username`, card) || ""),
      http_password: String(readInput(`tx.${idx}.http_password`, card) || ""),
      alerts,
    });
  });

  const emailToRaw = String(readInput("email_to") || "");
  return {
    poll_interval_seconds: Number(readInput("poll_interval_seconds") || 30),
    history_retention_days: Number(readInput("history_retention_days") || 90),
    history_min_interval_seconds: Number(readInput("history_min_interval_seconds") || 60),
    http_host: String(readInput("http_host") || "0.0.0.0"),
    http_port: Number(readInput("http_port") || 8090),
    snmp_timeout_seconds: Number(readInput("snmp_timeout_seconds") || 5),
    snmp_retries: Number(readInput("snmp_retries") || 2),
    alerts: {
      email_enabled: !!readInput("email_enabled"),
      smtp_host: String(readInput("smtp_host") || ""),
      smtp_port: Number(readInput("smtp_port") || 587),
      smtp_username: String(readInput("smtp_username") || ""),
      smtp_password: String(readInput("smtp_password") || ""),
      smtp_tls: !!readInput("smtp_tls"),
      email_from: String(readInput("email_from") || ""),
      email_to: emailToRaw
        .split(/[,;]/)
        .map((s) => s.trim())
        .filter(Boolean),
      cooldown_minutes: Number(readInput("cooldown_minutes") || 30),
      unreachable_polls: Number(readInput("unreachable_polls") || 3),
      on_unreachable: !!readInput("on_unreachable"),
      on_rf_off: !!readInput("on_rf_off"),
      on_tx_alarms: !!readInput("on_tx_alarms"),
      vswr: optFloat(readInput("vswr")),
      reflected_w: optFloat(readInput("reflected_w")),
      heatsink_c: optFloat(readInput("heatsink_c")),
      forward_min_w: optFloat(readInput("forward_min_w")),
      skip_unconfigured: !!readInput("skip_unconfigured"),
    },
    controls: {
      enabled: !!readInput("controls_enabled"),
      password: String(readInput("controls_password") || ""),
    },
    transmitters,
    stl_devices: collectStlFromForm(),
  };
}

function setSettingsStatus(message, isError = false) {
  const el = document.getElementById("settings-status");
  if (!el) return;
  el.hidden = !message;
  el.textContent = message || "";
  el.classList.toggle("error", isError);
}

async function loadSettings() {
  const cfg = await fetchJson("/api/config");
  renderGlobalForm(cfg);
  renderAlertsForm(cfg.alerts || {});
  renderControlsForm(cfg.controls || {});
  renderTxEditor(cfg.transmitters?.length ? cfg.transmitters : [emptyTx()]);
  renderStlEditor(cfg.stl_devices || []);
  const alerts = await fetchJson("/api/alerts");
  updateTestEmailButton(alerts);
}

async function saveSettings() {
  const payload = collectConfigFromForm();
  try {
    const result = await fetchJson("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setSettingsStatus("Saved. Poller reloaded with new config.");
    showToast("Config saved", "Transmitter list reloaded");
    renderGlobalForm(result.config);
    renderAlertsForm(result.config.alerts || {});
    renderControlsForm(result.config.controls || {});
    renderTxEditor(result.config.transmitters || []);
    renderStlEditor(result.config.stl_devices || []);
  } catch (err) {
    setSettingsStatus(err.message || String(err), true);
    showToast("Save failed", err.message || String(err), true);
  }
}

function tickWallClock() {
  const el = document.getElementById("wall-clock");
  if (!el) return;
  el.textContent = new Date().toLocaleString();
}

async function initFleetPage() {
  document.getElementById("refresh-btn")?.addEventListener("click", () => {
    pollFleet().catch(console.error);
  });
  document.getElementById("test-email-btn")?.addEventListener("click", () => {
    sendTestEmail().catch(console.error);
  });
  await loadFleet(false);
  setInterval(() => loadFleet(false).catch(console.error), 15000);
}

async function initWallPage() {
  tickWallClock();
  setInterval(tickWallClock, 1000);
  await loadFleet(true);
  setInterval(() => loadFleet(true).catch(console.error), 10000);
}

function modelFamilyForControls(model) {
  const m = String(model || "").toLowerCase();
  if (m.includes("flexiva") || m.includes("fax") || m.includes("gatesair")) return "flexiva";
  if (m.includes("aat") || m.includes("american")) return "aat";
  if (m.includes("crown") || m.includes("ecreso") || m.includes("audemat") || m.includes("fmngip")) {
    return "crown";
  }
  if (m.startsWith("vx")) return "vx";
  return "vs300";
}

async function setupRfControls(tx) {
  const panel = document.getElementById("rf-controls");
  const onBtn = document.getElementById("rf-on-btn");
  const offBtn = document.getElementById("rf-off-btn");
  const note = document.getElementById("rf-controls-note");
  const statusEl = document.getElementById("rf-controls-status");
  if (!panel || !onBtn || !offBtn) return;

  let status;
  try {
    status = await fetchJson("/api/controls/status");
  } catch (err) {
    panel.hidden = true;
    return;
  }

  const family = modelFamilyForControls(tx.model);
  const actions = status.supported_actions_by_model?.[family] || [];
  const enabled = !!status.enabled;
  const experimental = (status.experimental || []).includes(family);

  if (!enabled || !actions.length) {
    panel.hidden = true;
    return;
  }

  panel.hidden = false;
  if (note) {
    note.textContent = experimental
      ? "Experimental vendor write path. Confirm carefully — do not use until ready to validate live."
      : "Controls are gated. Confirm carefully — this affects on-air RF.";
  }
  if (statusEl) {
    statusEl.textContent = status.password_configured
      ? "Password required for each command."
      : "Set a controls password in Settings before using RF buttons.";
  }

  const busy = (flag) => {
    onBtn.disabled = flag || !actions.includes("rf_on") || !status.password_configured;
    offBtn.disabled = flag || !actions.includes("rf_off") || !status.password_configured;
  };
  busy(false);

  const run = async (action) => {
    const label = action === "rf_on" ? "RF ON" : "RF OFF";
    if (!window.confirm(`Confirm ${label} on ${tx.name}?`)) return;
    const password = window.prompt("Controls password:");
    if (password == null) return;
    busy(true);
    if (statusEl) statusEl.textContent = `Sending ${label}…`;
    try {
      const result = await fetchJson(
        `/api/transmitters/${encodeURIComponent(tx.tx_id)}/control`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action, password }),
        }
      );
      showToast(label, result.message || "Command sent");
      if (result.reading) renderDetail(result.reading);
      if (statusEl) statusEl.textContent = result.message || "Done";
    } catch (err) {
      showToast(`${label} failed`, err.message || String(err), true);
      if (statusEl) statusEl.textContent = err.message || String(err);
    } finally {
      busy(false);
    }
  };

  onBtn.onclick = () => run("rf_on").catch(console.error);
  offBtn.onclick = () => run("rf_off").catch(console.error);
}

async function initDetailPage() {
  const txId = txIdFromPath();
  if (!txId) return;

  let range = "24h";
  const tabs = document.querySelectorAll(".range-tabs button");
  tabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      range = btn.dataset.range;
      tabs.forEach((b) => b.classList.toggle("active", b === btn));
      loadHistory(txId, range).catch(console.error);
    });
  });

  document.getElementById("refresh-btn")?.addEventListener("click", async () => {
    const tx = await fetchJson(`/api/transmitters/${encodeURIComponent(txId)}/poll`, {
      method: "POST",
    });
    renderDetail(tx);
    await setupRfControls(tx);
    await loadHistory(txId, range);
  });

  const tx = await fetchJson(`/api/transmitters/${encodeURIComponent(txId)}`);
  renderDetail(tx);
  await setupRfControls(tx);
  await loadHistory(txId, range);
  setInterval(async () => {
    const latest = await fetchJson(`/api/transmitters/${encodeURIComponent(txId)}`);
    renderDetail(latest);
    await loadHistory(txId, range);
  }, 15000);
}

async function initSettingsPage() {
  document.getElementById("save-config-btn")?.addEventListener("click", () => {
    saveSettings().catch(console.error);
  });
  document.getElementById("add-tx-btn")?.addEventListener("click", () => {
    const cfg = collectConfigFromForm();
    cfg.transmitters.push(emptyTx());
    renderTxEditor(cfg.transmitters);
  });
  document.getElementById("add-stl-btn")?.addEventListener("click", () => {
    const devices = collectStlFromForm();
    devices.push(emptyStl());
    renderStlEditor(devices);
  });
  document.getElementById("test-email-btn")?.addEventListener("click", () => {
    sendTestEmail().catch(console.error);
  });
  await loadSettings();
}

function emptyStl() {
  return {
    id: "",
    name: "",
    model: "hdlink",
    host: "",
    snmp_community: "public",
    snmp_port: 161,
    location: "",
    related_tx_id: "",
    http_password: "",
    alerts: {},
  };
}

function renderStlEditor(devices) {
  const root = document.getElementById("stl-editor");
  if (!root) return;
  const list = devices || [];
  if (!list.length) {
    root.innerHTML = `<p class="empty">No STL links configured.</p>`;
    return;
  }
  root.innerHTML = list
    .map((device, idx) => {
      const overrides = device.alerts || {};
      const model = String(device.model || "hdlink").toLowerCase();
      return `
      <article class="tx-edit-card" data-stl-idx="${idx}">
        <div class="tx-edit-top">
          <h3>STL ${idx + 1}</h3>
          <button type="button" class="danger" data-remove-stl="${idx}">Remove</button>
        </div>
        <div class="form-grid">
          ${field("ID", `stl.${idx}.id`, device.id || "")}
          ${field("Name", `stl.${idx}.name`, device.name || "")}
          <label class="form-field">
            <span>Model</span>
            <select name="stl.${idx}.model">
              <option value="hdlink" ${model === "hdlink" ? "selected" : ""}>HD Link</option>
              <option value="iplink" ${model === "iplink" ? "selected" : ""}>IP Link</option>
              <option value="comrex" ${model === "comrex" ? "selected" : ""}>Comrex</option>
              <option value="briclink" ${model === "briclink" ? "selected" : ""}>BRIC-Link</option>
              <option value="instream" ${model === "instream" ? "selected" : ""}>Instream</option>
            </select>
          </label>
          ${field("Host", `stl.${idx}.host`, device.host || "")}
          ${field("Location", `stl.${idx}.location`, device.location || "")}
          ${field("SNMP community", `stl.${idx}.snmp_community`, device.snmp_community || "", "password")}
          ${field("SNMP port", `stl.${idx}.snmp_port`, device.snmp_port ?? 161, "number")}
          ${field("Web password", `stl.${idx}.http_password`, device.http_password || "", "password")}
          ${field("Related transmitter id", `stl.${idx}.related_tx_id`, device.related_tx_id || "")}
          ${field("Error-rate threshold", `stl.${idx}.alerts.error_rate`, overrides.error_rate ?? "", "number", "step=0.01")}
        </div>
      </article>`;
    })
    .join("");

  root.querySelectorAll("[data-remove-stl]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.getAttribute("data-remove-stl"));
      const devicesNow = collectStlFromForm();
      devicesNow.splice(idx, 1);
      renderStlEditor(devicesNow);
    });
  });
}

function collectStlFromForm() {
  const devices = [];
  document.querySelectorAll("[data-stl-idx]").forEach((card) => {
    const idx = card.getAttribute("data-stl-idx");
    const alerts = {};
    const rate = optFloat(readInput(`stl.${idx}.alerts.error_rate`, card));
    if (rate != null) alerts.error_rate = rate;
    const id = String(readInput(`stl.${idx}.id`, card) || "").trim();
    if (!id) return;
    devices.push({
      id,
      name: String(readInput(`stl.${idx}.name`, card) || "").trim(),
      model: String(readInput(`stl.${idx}.model`, card) || "hdlink").trim(),
      host: String(readInput(`stl.${idx}.host`, card) || "").trim(),
      location: String(readInput(`stl.${idx}.location`, card) || "").trim(),
      snmp_community: String(readInput(`stl.${idx}.snmp_community`, card) || "public"),
      snmp_port: Number(readInput(`stl.${idx}.snmp_port`, card) || 161),
      http_password: String(readInput(`stl.${idx}.http_password`, card) || ""),
      related_tx_id: String(readInput(`stl.${idx}.related_tx_id`, card) || "").trim(),
      alerts,
    });
  });
  return devices;
}

function stlIdFromPath() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[0] === "stl" && parts[1] ? decodeURIComponent(parts[1]) : "";
}

function stlCardMeters(device) {
  return (device.meters || [])
    .filter((meter) => meter.value != null && meter.category !== "link" && meter.category !== "alarm")
    .slice(0, 4);
}

function renderStlCard(device) {
  const alarmClass = device.active_alarm_count ? "alarm-count" : "alarm-count zero";
  const meters = stlCardMeters(device)
    .map(
      (meter) => `
      <div class="meter">
        <dt>${escapeHtml(meter.label)}</dt>
        <dd>${fmtMeter(meter.value, meter.unit)}</dd>
      </div>`
    )
    .join("");
  const err = device.error
    ? `<div class="error-text">${escapeHtml(device.error)}</div>`
    : "";
  return `
    <article class="tx-card">
      <div class="tx-card-top">
        <div>
          <h2><a class="tx-name-btn" href="/stl/${encodeURIComponent(device.stl_id)}">${escapeHtml(device.name)}</a></h2>
          <div class="tx-meta">${escapeHtml(device.model_label || device.model)}
            ${device.location ? " · " + escapeHtml(device.location) : ""}
            ${device.host ? " · " + escapeHtml(device.host) : ""}
          </div>
        </div>
        ${statusBadge(device.status)}
      </div>
      <dl class="meters">
        <div class="meter"><dt>Link</dt><dd>${escapeHtml(device.link_label || device.link_state || "—")}</dd></div>
        ${meters}
      </dl>
      ${err}
      <div class="tx-footer">
        <span class="${alarmClass}">${device.active_alarm_count} alarm${device.active_alarm_count === 1 ? "" : "s"}</span>
        <span>${fmtTime(device.timestamp)}</span>
      </div>
    </article>`;
}

function renderStlSummary(summary) {
  const el = document.getElementById("summary");
  if (!el || !summary) return;
  el.innerHTML = [
    ["STL", summary.total],
    ["Online", summary.online],
    ["Degraded", summary.degraded],
    ["Offline", summary.offline],
    ["Alarms", summary.active_alarms],
  ]
    .map(
      ([label, value]) => `
      <div class="summary-card">
        <div class="label">${label}</div>
        <div class="value">${value}</div>
      </div>`
    )
    .join("");
}

function renderStlList(data) {
  renderStlSummary(data.summary);
  renderAlerts(data.alerts);
  const grid = document.getElementById("stl-fleet");
  if (!grid) return;
  if (!data.devices?.length) {
    grid.innerHTML = `<p class="empty">No STL links configured. Add one in Settings.</p>`;
    return;
  }
  grid.innerHTML = data.devices.map((device) => renderStlCard(device)).join("");
}

async function loadStlList() {
  const data = await fetchJson("/api/stl");
  renderStlList(data);
  const updated = document.getElementById("updated");
  if (updated) updated.textContent = `Updated ${fmtTime(new Date().toISOString())}`;
}

function renderStlDetail(device) {
  const title = document.getElementById("stl-title");
  if (title) title.textContent = device.name;
  const sub = document.getElementById("stl-subtitle");
  if (sub) {
    sub.textContent = [
      device.model_label || device.model,
      device.host,
      device.location,
      device.link_label || device.link_state,
    ]
      .filter(Boolean)
      .join(" · ");
  }
  const err = document.getElementById("stl-error");
  if (err) {
    err.hidden = !device.error;
    err.textContent = device.error || "";
  }
  const meters = document.getElementById("stl-meters");
  if (meters) {
    const items = (device.meters || [])
      .map(
        (meter) => `
        <div class="meter-big">
          <dt>${escapeHtml(meter.label)}</dt>
          <dd>${fmtMeter(meter.value, meter.unit)}</dd>
        </div>`
      )
      .join("");
    meters.innerHTML = `<dl class="meter-row">${items || "<p class='empty'>No meters.</p>"}</dl>`;
  }
  const alarms = document.getElementById("stl-alarms");
  if (alarms) {
    const active = (device.alarms || []).filter((alarm) => alarm.active);
    alarms.innerHTML = active.length
      ? active.map((alarm) => `<li>${escapeHtml(alarm.label)}</li>`).join("")
      : `<li class="empty">No active STL alarms.</li>`;
  }
}

function drawStlCharts(points, device) {
  const grid = document.getElementById("chart-grid");
  if (!grid) return;
  const numeric = (device.meters || []).filter(
    (meter) => typeof meter.value === "number" && meter.category !== "link" && meter.category !== "alarm"
  );
  const charts = numeric.filter((meter) => seriesHasData(points, meter.key));
  if (!charts.length) {
    grid.innerHTML = `<p class="empty">No numeric STL history for this range yet.</p>`;
    return;
  }
  grid.innerHTML = charts
    .map(
      (meter, idx) => `
      <div class="chart-wrap">
        <p class="sub" style="margin-bottom:0.35rem">${escapeHtml(meter.label)}</p>
        <canvas id="chart-${escapeHtml(meter.key)}" height="180" data-key="${escapeHtml(meter.key)}" data-color="${CHART_COLORS[idx % CHART_COLORS.length]}"></canvas>
      </div>`
    )
    .join("");
  for (const meter of charts) {
    const canvas = document.getElementById(`chart-${meter.key}`);
    if (!canvas) continue;
    drawChart(canvas, points, meter.key, canvas.dataset.color || "#3b82f6");
  }
}

async function loadStlHistory(stlId, range, device) {
  const data = await fetchJson(
    `/api/stl/${encodeURIComponent(stlId)}/history?range=${range}`
  );
  drawStlCharts(data.points || [], device);
}

async function initStlPage() {
  const stlId = stlIdFromPath();
  const list = document.getElementById("stl-fleet");
  const summary = document.getElementById("summary");
  const detail = document.getElementById("stl-detail");

  if (!stlId) {
    if (detail) detail.hidden = true;
    document.getElementById("refresh-btn")?.addEventListener("click", () => {
      fetchJson("/api/stl/poll", { method: "POST" })
        .then((data) => {
          renderStlList(data);
          const updated = document.getElementById("updated");
          if (updated) updated.textContent = `Updated ${fmtTime(new Date().toISOString())}`;
        })
        .catch((err) => showToast("Poll failed", err.message || String(err), true));
    });
    await loadStlList();
    setInterval(() => loadStlList().catch(console.error), 15000);
    return;
  }

  if (list) list.hidden = true;
  if (summary) summary.hidden = true;
  if (detail) detail.hidden = false;
  let range = "24h";
  let latest = null;
  document.querySelectorAll("#stl-range-tabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      range = btn.dataset.range;
      document.querySelectorAll("#stl-range-tabs button").forEach((item) => {
        item.classList.toggle("active", item === btn);
      });
      if (latest) loadStlHistory(stlId, range, latest).catch(console.error);
    });
  });
  const refresh = async () => {
    latest = await fetchJson(`/api/stl/${encodeURIComponent(stlId)}/poll`, { method: "POST" });
    renderStlDetail(latest);
    const alerts = await fetchJson("/api/alerts");
    renderAlerts(alerts);
    await loadStlHistory(stlId, range, latest);
    const updated = document.getElementById("updated");
    if (updated) updated.textContent = `Updated ${fmtTime(new Date().toISOString())}`;
  };
  document.getElementById("refresh-btn")?.addEventListener("click", () => {
    refresh().catch((err) => showToast("Poll failed", err.message || String(err), true));
  });
  latest = await fetchJson(`/api/stl/${encodeURIComponent(stlId)}`);
  renderStlDetail(latest);
  const alerts = await fetchJson("/api/alerts");
  renderAlerts(alerts);
  await loadStlHistory(stlId, range, latest);
  setInterval(() => {
    fetchJson(`/api/stl/${encodeURIComponent(stlId)}`)
      .then((device) => {
        latest = device;
        renderStlDetail(device);
        return fetchJson("/api/alerts");
      })
      .then((alerts) => renderAlerts(alerts))
      .catch(console.error);
  }, 15000);
}

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  if (page === "fleet") initFleetPage().catch(console.error);
  if (page === "wall") initWallPage().catch(console.error);
  if (page === "detail") initDetailPage().catch(console.error);
  if (page === "settings") initSettingsPage().catch(console.error);
  if (page === "stl") initStlPage().catch(console.error);
});
