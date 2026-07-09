(function () {
  "use strict";

  const tbody = document.getElementById("events-body");
  const status = document.getElementById("status");
  const btnClear = document.getElementById("btn-clear");
  const counts = {
    activate: document.getElementById("cnt-activate"),
    heartbeat: document.getElementById("cnt-heartbeat"),
    metrics: document.getElementById("cnt-metrics"),
    commands: document.getElementById("cnt-commands"),
    total: document.getElementById("cnt-total"),
    errors: document.getElementById("cnt-errors"),
  };

  function bucket(path) {
    if (path.indexOf("/activate") !== -1) return "activate";
    if (path.indexOf("/heartbeat") !== -1) return "heartbeat";
    if (path.indexOf("/metrics") !== -1) return "metrics";
    if (path.indexOf("/commands") !== -1) return "commands";
    return null;
  }

  function statusClass(status, note) {
    if (note === "MOCK") return "status-mock";
    if (note === "auth_error" || note === "rate_limited") return "status-warn";
    if (note === "network_error" || note === "http_error") return "status-err";
    if (status && status >= 200 && status < 300) return "status-ok";
    if (status && status >= 400) return "status-err";
    if (note === "pending") return "status-pending";
    return "";
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (m) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m];
    });
  }

  function prettyBody(body) {
    if (!body) return '<span class="muted">—</span>';
    try {
      return JSON.stringify(JSON.parse(body), null, 2);
    } catch (_) {
      return body;
    }
  }

  function render(events) {
    if (!events || events.length === 0) {
      tbody.innerHTML = '<tr class="empty"><td colspan="7" class="muted">Sin eventos aún. Activá el agente o esperá el próximo push.</td></tr>';
    } else {
      tbody.innerHTML = events.map(function (e) {
        const t = new Date(e.ts);
        const time = isNaN(t.getTime())
          ? "—"
          : t.toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
        const cls = statusClass(e.status, e.note);
        const statusCell = e.status == null ? "—" : String(e.status);
        const msCell = e.duration_ms == null ? "—" : String(e.duration_ms);
        const noteLabel = e.note && e.note !== "ok" && e.note !== "MOCK"
          ? ' <span class="log-note">(' + escapeHtml(e.note) + ')</span>'
          : "";
        return (
          '<tr class="' + cls + '">' +
            '<td class="mono">' + time + '</td>' +
            '<td><span class="method method-' + escapeHtml(e.method) + '">' + escapeHtml(e.method) + '</span></td>' +
            '<td class="mono">' + escapeHtml(e.path) + '</td>' +
            '<td>' + statusCell + noteLabel + '</td>' +
            '<td>' + msCell + '</td>' +
            '<td>' + escapeHtml(e.mode) + '</td>' +
            '<td><pre class="log-body">' + escapeHtml(prettyBody(e.body)) + '</pre></td>' +
          '</tr>'
        );
      }).join("");
    }

    const c = { activate: 0, heartbeat: 0, metrics: 0, commands: 0, total: 0, errors: 0 };
    (events || []).forEach(function (e) {
      if (e.note === "pending") return;
      c.total++;
      const b = bucket(e.path);
      if (b) c[b]++;
      if (e.note !== "ok" && e.note !== "MOCK") c.errors++;
    });
    Object.keys(counts).forEach(function (k) {
      if (counts[k]) counts[k].textContent = c[k] || 0;
    });
  }

  async function poll() {
    try {
      const r = await fetch("/api/local/push-log", { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const d = await r.json();
      render(d.events);
      status.textContent = "Conectado · " + (d.events ? d.events.length : 0) + " eventos";
      status.className = "small log-status log-status-ok";
    } catch (e) {
      status.textContent = "Desconectado · " + e.message;
      status.className = "small log-status log-status-err";
    }
  }

  btnClear.addEventListener("click", async function () {
    if (!confirm("¿Limpiar el registro de eventos?")) return;
    try {
      await fetch("/api/local/push-log", { method: "DELETE" });
    } catch (_) {}
    poll();
  });

  poll();
  setInterval(poll, 1000);
})();
