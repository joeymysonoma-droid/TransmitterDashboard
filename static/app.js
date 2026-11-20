const CATEGORY_ORDER = ["rf", "pa", "supply", "cooling", "control"];
const CATEGORY_LABELS = {
  rf: "RF",
  pa: "PA / Drive",
  supply: "Supplies",
  cooling: "Cooling",
  control: "Control",
};

let knownAlertKeys = new Set();

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
  if (unit === "%") return `${fmtNum(value, 1)} %`;
  if (!unit) return fmtNum(value, 3);
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

async function fetchJson(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
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

function renderAlerts(alerts) {
  const banner = document.getElementById("alert-banner");
  const list = document.getElementById("alert-list");
  if (!banner || !list) return;

  const active = alerts?.active || [];
  const nextKeys = new Set(active.map((a) => a.key));
  for (const item of active) {
    if (!knownAlertKeys.has(item.key)) {
      showToast("Alert", item.message, true);
    }
  }
  knownAlertKeys = nextKeys;

  if (!active.length) {
    banner.classList.remove("visible");
    list.innerHTML = "";
    return;
  }

  banner.classList.add("visible");
  list.innerHTML = active
    .map((a) => `<li>${escapeHtml(a.message)}</li>`)
    .join("");
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

function renderFleet(data) {
  renderSummary(data.summary);
  renderAlerts(data.alerts);
  const grid = document.getElementById("fleet");
  if (!grid) return;

  if (!data.transmitters?.length) {
    grid.innerHTML = `<p class="empty">No transmitters configured.</p>`;
    return;
  }

  grid.innerHTML = data.transmitters
    .map((tx) => {
      const alarmClass = tx.active_alarm_count ? "alarm-count" : "alarm-count zero";
      const err = tx.error
        ? `<div class="error-text">${escapeHtml(tx.error)}</div>`
        : "";
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
    })
    .join("");
}

async function loadFleet() {
  const data = await fetchJson("/api/transmitters");
  renderFleet(data);
  const updated = document.getElementById("updated");
  if (updated) updated.textContent = `Updated ${fmtTime(new Date().toISOString())}`;
}

async function pollFleet() {
  const data = await fetchJson("/api/poll", { method: "POST" });
  renderFleet(data);
  const updated = document.getElementById("updated");
  if (updated) updated.textContent = `Updated ${fmtTime(new Date().toISOString())}`;
}

function renderDetailMeters(tx) {
  const root = document.getElementById("meters");
  if (!root) return;

  const meters = (tx.meters || []).filter((m) => m.key !== "rf_state" && m.key !== "local_remote");
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
  const charts = [
    ["chart-fwd", "fwd_pwr_w", "#3b82f6"],
    ["chart-rfl", "rfl_pwr_w", "#22d3ee"],
    ["chart-vswr", "vswr", "#f59e0b"],
    ["chart-temp", "heatsink_temp_c", "#22c55e"],
    ["chart-pa-v", "pa_volts_v", "#a78bfa"],
    ["chart-pa-i", "pa_current_1_a", "#fb7185"],
    ["chart-48v", "plus48_v", "#38bdf8"],
    ["chart-fan", "fan1_rpm", "#94a3b8"],
  ];
  for (const [id, key, color] of charts) {
    const canvas = document.getElementById(id);
    if (canvas) drawChart(canvas, data.points, key, color);
  }
}

function txIdFromPath() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[0] === "tx" ? decodeURIComponent(parts[1] || "") : "";
}

async function initFleetPage() {
  document.getElementById("refresh-btn")?.addEventListener("click", () => {
    pollFleet().catch(console.error);
  });
  await loadFleet();
  setInterval(() => loadFleet().catch(console.error), 15000);
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
    await loadHistory(txId, range);
  });

  const tx = await fetchJson(`/api/transmitters/${encodeURIComponent(txId)}`);
  renderDetail(tx);
  await loadHistory(txId, range);
  setInterval(async () => {
    const latest = await fetchJson(`/api/transmitters/${encodeURIComponent(txId)}`);
    renderDetail(latest);
    await loadHistory(txId, range);
  }, 15000);
}

document.addEventListener("DOMContentLoaded", () => {
  if (document.body.dataset.page === "fleet") initFleetPage().catch(console.error);
  if (document.body.dataset.page === "detail") initDetailPage().catch(console.error);
});
