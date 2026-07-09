(function () {
  "use strict";

  const img = document.getElementById("preview");
  const canvas = document.getElementById("overlay");
  const ctx = canvas.getContext("2d");
  const status = document.getElementById("status");
  const diag = document.getElementById("diag");
  const stats = {
    people: document.getElementById("stat-people"),
    queueStatus: document.getElementById("stat-status"),
    fps: document.getElementById("stat-fps"),
    infer: document.getElementById("stat-infer"),
    model: document.getElementById("stat-model"),
    polys: document.getElementById("stat-polys"),
  };

  const POLY_FILL = "rgba(79, 70, 229, 0.15)";
  const POLY_STROKE = "#4f46e5";

  let polys = [];
  const init = window.__INITIAL_ROI__ || {};
  if (init && Array.isArray(init.polygons)) {
    polys = init.polygons.map(function (p) {
      return p.map(function (pt) { return [pt.x, pt.y]; });
    });
  }

  function fitCanvas() {
    const r = img.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(r.width));
    canvas.height = Math.max(1, Math.round(r.height));
    draw();
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!polys.length) return;
    polys.forEach(function (poly) {
      if (poly.length < 3) return;
      ctx.fillStyle = POLY_FILL;
      ctx.strokeStyle = POLY_STROKE;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(poly[0][0] * canvas.width, poly[0][1] * canvas.height);
      for (let i = 1; i < poly.length; i++) {
        ctx.lineTo(poly[i][0] * canvas.width, poly[i][1] * canvas.height);
      }
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      for (let i = 0; i < poly.length; i++) {
        ctx.beginPath();
        ctx.arc(poly[i][0] * canvas.width, poly[i][1] * canvas.height, 4, 0, Math.PI * 2);
        ctx.fillStyle = "#fff";
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = POLY_STROKE;
        ctx.stroke();
      }
    });
  }

  if (img.complete) fitCanvas();
  else img.addEventListener("load", fitCanvas);
  window.addEventListener("resize", fitCanvas);

  function fmtTime(iso) {
    try {
      return new Date(iso).toLocaleTimeString("es-PE", {
        hour: "2-digit", minute: "2-digit", second: "2-digit",
      });
    } catch (_) {
      return iso;
    }
  }

  async function poll() {
    try {
      const r = await fetch("/api/local/agent-status", { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const d = await r.json();
      stats.people.textContent = d.people;
      stats.queueStatus.textContent = d.queue_status;
      stats.fps.textContent = d.fps.toFixed(1);
      stats.infer.textContent = d.infer_ms.toFixed(1) + " ms";
      stats.model.textContent = d.model_loaded ? "yolov8n" : "—";
      stats.polys.textContent = d.polygons_used;
      if (d.pipeline_running) {
        status.textContent = "● Pipeline activo";
        status.className = "small log-status log-status-ok";
      } else {
        status.textContent = "● Pipeline detenido";
        status.className = "small log-status log-status-err";
      }
      diag.textContent = "Última actualización: " + fmtTime(d.last_updated);
    } catch (e) {
      status.textContent = "● Desconectado";
      status.className = "small log-status log-status-err";
      diag.textContent = e.message;
    }
  }

  poll();
  setInterval(poll, 1000);
})();
