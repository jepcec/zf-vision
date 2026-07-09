(function () {
  "use strict";

  const img = document.getElementById("preview");
  const canvas = document.getElementById("roi");
  const ctx = canvas.getContext("2d");
  const list = document.getElementById("poly-list");
  const btnUndo = document.getElementById("btn-undo");
  const btnClear = document.getElementById("btn-clear");
  const btnSave = document.getElementById("btn-save");
  const btnFinish = document.getElementById("btn-finish");
  const form = document.getElementById("roi-form");
  const input = document.getElementById("polygons-input");

  const SNAP_RADIUS = 14;
  const SNAP_RADIUS_SQ = SNAP_RADIUS * SNAP_RADIUS;
  const VERTEX_RADIUS = 5;
  const VERTEX_HOVER_RADIUS = 8;
  const COLORS = ["#4f46e5", "#059669", "#d97706", "#e11d48", "#7c3aed"];

  /** @type {{x:number,y:number}[][]} */
  let polygons = [];
  let current = null;
  /** @type {{sourceIdx:number, vertIdx:number}|null} */
  let dragging = null;
  let suppressNextClick = false;
  let isHoveringFirst = false;
  let dragMoved = false;

  function fitCanvas() {
    const r = img.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(r.width));
    canvas.height = Math.max(1, Math.round(r.height));
    draw();
  }

  function pxToNorm(p) {
    return { x: +(p.x / canvas.width).toFixed(4), y: +(p.y / canvas.height).toFixed(4) };
  }

  function distSq(a, b) {
    const dx = a.x - b.x, dy = a.y - b.y;
    return dx * dx + dy * dy;
  }

  function eventPos(e) {
    const r = canvas.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    polygons.forEach((poly, idx) =>
      drawPoly(poly, COLORS[idx % COLORS.length], true, false, false)
    );
    if (current && current.length > 0) {
      drawPoly(current, "#4f46e5", current.length >= 3, isHoveringFirst, true);
    }
  }

  function drawPoly(poly, color, closed, highlightFirst, isCurrent) {
    if (poly.length === 0) return;
    ctx.strokeStyle = color;
    ctx.fillStyle = color + "22";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(poly[0].x, poly[0].y);
    for (let i = 1; i < poly.length; i++) ctx.lineTo(poly[i].x, poly[i].y);
    if (closed && poly.length >= 3) {
      ctx.closePath();
      ctx.fill();
    }
    ctx.stroke();
    for (let i = 0; i < poly.length; i++) {
      const isFirst = i === 0;
      const big = isFirst && highlightFirst;
      const r = big ? VERTEX_HOVER_RADIUS : VERTEX_RADIUS;
      ctx.beginPath();
      ctx.arc(poly[i].x, poly[i].y, r, 0, Math.PI * 2);
      ctx.fillStyle = big ? color : "#fff";
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = color;
      ctx.stroke();
    }
    if (isCurrent && highlightFirst && poly.length >= 3) {
      ctx.beginPath();
      ctx.arc(poly[0].x, poly[0].y, SNAP_RADIUS, 0, Math.PI * 2);
      ctx.strokeStyle = color + "66";
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 4]);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }

  function hitVertex(poly, x, y) {
    for (let i = 0; i < poly.length; i++) {
      if (distSq({ x, y }, poly[i]) <= SNAP_RADIUS_SQ) return i;
    }
    return -1;
  }

  function finishCurrent() {
    if (current && current.length >= 3) {
      polygons.push(current);
    }
    current = null;
    isHoveringFirst = false;
    refreshList();
    draw();
  }

  canvas.addEventListener("click", function (e) {
    if (dragging) return;
    if (suppressNextClick) { suppressNextClick = false; return; }
    if (dragMoved) { dragMoved = false; return; }

    const p = eventPos(e);

    if (current && current.length >= 3 && distSq(p, current[0]) <= SNAP_RADIUS_SQ) {
      finishCurrent();
      return;
    }

    if (!current) current = [];
    current.push(p);
    draw();
  });

  canvas.addEventListener("dblclick", function (e) {
    e.preventDefault();
    if (current && current.length >= 3) {
      suppressNextClick = true;
      finishCurrent();
    }
  });

  canvas.addEventListener("mousedown", function (e) {
    const p = eventPos(e);
    const sources = current ? [...polygons, current] : polygons;
    for (let i = 0; i < sources.length; i++) {
      const idx = hitVertex(sources[i], p.x, p.y);
      if (idx !== -1) {
        dragging = { sourceIdx: i, vertIdx: idx };
        dragMoved = false;
        return;
      }
    }
  });

  canvas.addEventListener("mousemove", function (e) {
    if (dragging) {
      const p = eventPos(e);
      const inCurrent = dragging.sourceIdx === polygons.length;
      const arr = inCurrent ? current : polygons[dragging.sourceIdx];
      if (arr) {
        arr[dragging.vertIdx] = p;
        dragMoved = true;
        draw();
      }
      return;
    }
    const p = eventPos(e);
    const wasHovering = isHoveringFirst;
    isHoveringFirst = !!(current && current.length >= 3 && distSq(p, current[0]) <= SNAP_RADIUS_SQ);
    if (isHoveringFirst !== wasHovering) draw();
  });

  window.addEventListener("mouseup", function () {
    dragging = null;
  });

  canvas.addEventListener("mouseleave", function () {
    dragging = null;
    if (isHoveringFirst) { isHoveringFirst = false; draw(); }
  });

  window.addEventListener("keydown", function (e) {
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
    if (e.key === "Enter" && current && current.length >= 3) {
      e.preventDefault();
      finishCurrent();
    } else if (e.key === "Escape" && current) {
      e.preventDefault();
      current = null;
      isHoveringFirst = false;
      draw();
      refreshList();
    }
  });

  function refreshList() {
    list.innerHTML = "";
    if (polygons.length === 0) {
      const li = document.createElement("li");
      li.className = "muted";
      li.id = "poly-empty";
      li.textContent = "Aún no hay polígonos.";
      list.appendChild(li);
    } else {
      polygons.forEach(function (_, i) {
        const li = document.createElement("li");
        const left = document.createElement("span");
        left.textContent = "Polígono " + (i + 1) + " · " + polygons[i].length + " puntos";
        const right = document.createElement("button");
        right.type = "button";
        right.textContent = "Borrar";
        right.addEventListener("click", function () {
          polygons.splice(i, 1);
          refreshList();
          draw();
          updateSave();
        });
        li.appendChild(left);
        li.appendChild(right);
        list.appendChild(li);
      });
    }
    updateSave();
  }

  function updateSave() {
    btnSave.disabled = polygons.length === 0;
    if (btnFinish) btnFinish.disabled = !(current && current.length >= 3);
  }

  btnUndo.addEventListener("click", function () {
    if (current && current.length > 0) current.pop();
    else if (polygons.length > 0) polygons.pop();
    isHoveringFirst = false;
    draw();
    refreshList();
  });

  btnClear.addEventListener("click", function () {
    if (!confirm("¿Borrar todos los polígonos?")) return;
    polygons = [];
    current = null;
    isHoveringFirst = false;
    draw();
    refreshList();
  });

  if (btnFinish) {
    btnFinish.addEventListener("click", function () {
      if (current && current.length >= 3) finishCurrent();
    });
  }

  form.addEventListener("submit", function () {
    const norm = polygons.map(function (poly) {
      return poly.map(pxToNorm);
    });
    input.value = JSON.stringify(norm);
  });

  refreshList();
  if (img.complete) fitCanvas();
  else img.addEventListener("load", fitCanvas);
  window.addEventListener("resize", fitCanvas);
})();
