const COLORS = {unscanned:"#64748b", scanned:"#22c55e", blocked:"#ef4444", survivor_found:"#f59e0b"};
const $ = id => document.getElementById(id);
const map = L.map("map").setView([12.9725, 77.5925], 15);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom: 19, attribution: "&copy; OpenStreetMap contributors"}).addTo(map);
const zoneL = {}, droneL = {}, routeL = {};
let ws, lastPending = "", zoneIds = [];

function send(o) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(o)); }

function render(s) {
  $("tick").textContent = "Tick " + s.tick;
  const c = $("comms"); const out = s.comms === "blackout";
  c.textContent = out ? "COMMS BLACKOUT" : "COMMS NORMAL"; c.className = "pill " + (out ? "bad" : "ok");
  zoneIds = s.zones.map(z => z.id);

  s.zones.forEach(z => {
    const col = COLORS[z.status] || "#64748b";
    if (!zoneL[z.id]) zoneL[z.id] = L.rectangle([[z.lat - 0.0025, z.lng - 0.0025], [z.lat + 0.0025, z.lng + 0.0025]], {weight: 1.5}).addTo(map).bindTooltip(z.id, {permanent: true, direction: "center", className: "zt"});
    zoneL[z.id].setStyle({color: col, fillColor: col, fillOpacity: z.status === "unscanned" ? .12 : .4});
    zoneL[z.id].setTooltipContent(z.id + (z.aided ? " ✚" : ""));
  });

  s.drones.forEach(d => {
    const col = d.type === "scanner" ? "#38bdf8" : "#facc15";
    if (!droneL[d.id]) {
      droneL[d.id] = L.circleMarker([d.lat, d.lng], {radius: 8, color: "#fff", weight: 2, fillOpacity: 1}).addTo(map);
      routeL[d.id] = L.polyline([], {color: col, weight: 2, dashArray: "4 6"}).addTo(map);
    }
    const off = d.type === "supplier" && d.status === "idle" ? (+d.id.slice(1) - 4) * 0.0003 : 0;
    droneL[d.id].setLatLng([d.lat, d.lng + off]).setStyle({fillColor: d.status === "grounded" ? "#6b7280" : col}).bindTooltip(d.id);
    routeL[d.id].setLatLngs([[d.lat, d.lng], ...d.route]);
  });

  $("fleet").innerHTML = s.drones.map(d => `<div class="card"><b>${d.id}</b> ${d.type} · ${d.status}${d.target ? " → " + d.target : ""}
    <div class="bar"><i style="width:${d.battery}%;background:${d.battery <= 20 ? "#ef4444" : "#22c55e"}"></i></div><small>${d.battery}%</small></div>`).join("");

  const sig = JSON.stringify(s.pending);
  if (sig !== lastPending) {
    lastPending = sig;
    $("pending").innerHTML = s.pending.length ? s.pending.map(p => `<div class="card"><b>${p.id}</b> ${p.drone_id} → ${p.target_zone}<br><small>${p.reason}</small><br>
      ${p.queued ? '<small class="warn">Queued – will run when comms return</small>' : `<button class="go" onclick="send({type:'approve',id:'${p.id}'})">Approve</button>
      <select id="sel-${p.id}">${zoneIds.map(z => `<option ${z === p.target_zone ? "selected" : ""}>${z}</option>`).join("")}</select>
      <button onclick="send({type:'override',id:'${p.id}',target_zone:$('sel-${p.id}').value})">Override</button>`}</div>`).join("")
      : '<p class="muted">No pending proposals.</p>';
  }

  $("log").innerHTML = s.log.map(l => `<div class="${/BLOCKED|blackout|low battery/i.test(l) ? "crit" : /rerout|SURVIVOR/.test(l) ? "warn" : ""}">${l}</div>`).join("");
}

function connect() {
  ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  ws.onopen = () => $("conn").classList.add("on");
  ws.onmessage = e => render(JSON.parse(e.data));
  ws.onclose = () => { $("conn").classList.remove("on"); setTimeout(connect, 2000); };
}
$("blackout").onclick = () => send({type: "trigger", event: "blackout"});
$("reset").onclick = () => fetch("/reset", {method: "POST"});
connect();
