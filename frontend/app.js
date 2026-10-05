let BASE_LNG = 80.126215505921;
let BASE_LAT = 13.046272448534;
let map;
let baseMarker = null;
let droneMarkers = {};
let flightTrails = {};
let incidentMarkers = {};
let obstacleMarkers = [];
let zoneLayer = null;
let gridLineLayers = [];
let currentDronesData = {};

// Initialize Leaflet Map
function initMap() {
  map = L.map("map", { zoomControl: true }).setView([BASE_LAT, BASE_LNG], 10);

  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; OSM'
  }).addTo(map);

  const baseIcon = L.divIcon({
    className: "base-helipad",
    html: `<div style="background:#3b82f6;color:white;font-weight:900;width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;border:3px solid white;box-shadow:0 0 20px #3b82f6; font-size: 18px;">H</div>`,
    iconSize: [40, 40],
    iconAnchor: [20, 20]
  });
  baseMarker = L.marker([BASE_LAT, BASE_LNG], { icon: baseIcon, zIndexOffset: 1000 }).addTo(map)
    .bindPopup("DroneX Coastal Base Station");

  // Click-to-add dynamic obstacle
  map.on("click", (e) => {
    const payload = { type: "add_obstacle", lat: e.latlng.lat, lng: e.latlng.lng };
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(payload));
    }
  });
}

// Custom Quadcopter SVG generator
function createDroneSVG(id, type, isScanning) {
  const color = type === "Scanner" ? "#00e5ff" : "#ffea00";
  const idPart = id.split("-")[1] || id;
  const parsedId = Number.parseInt(idPart, 10);
  const numId = Number.isNaN(parsedId) ? idPart : parsedId;
  const pulseHtml = isScanning ? '<div class="radar-pulse-ring"></div>' : '';

  return L.divIcon({
    className: "drone-marker-container",
    html: `
      ${pulseHtml}
      <svg width="28" height="28" viewBox="0 0 40 40">
        <circle cx="10" cy="10" r="5" fill="none" stroke="${color}" stroke-width="2"/>
        <circle cx="30" cy="10" r="5" fill="none" stroke="${color}" stroke-width="2"/>
        <circle cx="10" cy="30" r="5" fill="none" stroke="${color}" stroke-width="2"/>
        <circle cx="30" cy="30" r="5" fill="none" stroke="${color}" stroke-width="2"/>
        <line x1="10" y1="10" x2="30" y2="30" stroke="${color}" stroke-width="2"/>
        <line x1="30" y1="10" x2="10" y2="30" stroke="${color}" stroke-width="2"/>
        <circle cx="20" cy="20" r="8" fill="#1e293b" stroke="${color}" stroke-width="2"/>
        <text x="20" y="24" text-anchor="middle" fill="#f8fafc" font-size="11" font-family="monospace" font-weight="bold">${numId}</text>
      </svg>
    `,
    iconSize: [28, 28],
    iconAnchor: [14, 14]
  });
}

function isPointInPolygon(lat, lng, polygon) {
  const vertices = polygon[0][0] === polygon[polygon.length - 1][0]
    && polygon[0][1] === polygon[polygon.length - 1][1]
    ? polygon.slice(0, -1)
    : polygon;
  let inside = false;

  for (let i = 0, j = vertices.length - 1; i < vertices.length; j = i++) {
    const [latI, lngI] = vertices[i];
    const [latJ, lngJ] = vertices[j];
    if ((latI > lat) !== (latJ > lat) && lng < ((lngJ - lngI) * (lat - latI)) / (latJ - latI) + lngI) {
      inside = !inside;
    }
  }
  return inside;
}

function getVerticalPolygonSegments(polygon, longitude) {
  const vertices = polygon[0][0] === polygon[polygon.length - 1][0]
    && polygon[0][1] === polygon[polygon.length - 1][1]
    ? polygon.slice(0, -1)
    : polygon;
  const intersections = [];

  for (let i = 0; i < vertices.length; i++) {
    const [lat1, lng1] = vertices[i];
    const [lat2, lng2] = vertices[(i + 1) % vertices.length];
    if (Math.abs(lng2 - lng1) < 1e-12) continue;

    const fraction = (longitude - lng1) / (lng2 - lng1);
    if (fraction >= -1e-10 && fraction <= 1 + 1e-10) {
      intersections.push(lat1 + fraction * (lat2 - lat1));
    }
  }

  const uniqueLatitudes = intersections.sort((a, b) => a - b).filter((latitude, index, sorted) => (
    index === 0 || Math.abs(latitude - sorted[index - 1]) > 1e-10
  ));
  const segments = [];

  for (let i = 0; i + 1 < uniqueLatitudes.length; i++) {
    const startLat = uniqueLatitudes[i];
    const endLat = uniqueLatitudes[i + 1];
    if (isPointInPolygon((startLat + endLat) / 2, longitude, polygon)) {
      segments.push([[startLat, longitude], [endLat, longitude]]);
    }
  }
  return segments;
}

function updateUI(data) {
  // 1. Mission Clock & Coverage
  document.getElementById("mission-time").innerText = `Mission T+${String(data.time_step).padStart(3, '0')} | 0.8s Tick`;
  document.getElementById("coverage-val").innerText = `${data.coverage}%`;
  document.getElementById("coverage-fill").style.width = `${data.coverage}%`;

  if (data.base_station) {
    BASE_LNG = data.base_station.x;
    BASE_LAT = data.base_station.y;
    if (baseMarker) baseMarker.setLatLng([BASE_LAT, BASE_LNG]);
  }

  // 2. Zone Polygon Boundary
  if (!zoneLayer && data.zone_polygon) {
    zoneLayer = L.polygon(data.zone_polygon, {
      color: "#f87171",
      weight: 2,
      dashArray: "6, 6",
      fillOpacity: 0.05
    }).addTo(map);
  }

  gridLineLayers.forEach(layer => map.removeLayer(layer));
  gridLineLayers = [];
  if (data.grid_lines && data.zone_polygon) {
    data.grid_lines.forEach(longitude => {
      getVerticalPolygonSegments(data.zone_polygon, longitude).forEach(segment => {
        gridLineLayers.push(L.polyline(segment, {
          color: "#38bdf8",
          weight: 1,
          opacity: 0.8,
          dashArray: "5, 5",
          interactive: false
        }).addTo(map));
      });
    });
  }

  // 3. Environmental Drawer Details
  if (data.weather) {
    document.getElementById("env-risk").innerText = data.weather.risk_level;
    document.getElementById("env-wind").innerText = `${data.weather.wind_speed} km/h`;
    document.getElementById("env-vis").innerText = `${data.weather.visibility} km`;
    document.getElementById("env-rain").innerText = `${data.weather.rain_intensity}%`;
    document.getElementById("env-factor").innerText = `${data.weather.factor}x`;
  }

  // 4. Incident Queue
  const incContainer = document.getElementById("incident-list");
  if (data.incidents && data.incidents.length > 0) {
    incContainer.innerHTML = data.incidents.map(inc => `
      <div class="incident-card">
        <div class="inc-header">
          <span>${inc.id} (${inc.type})</span>
          <span class="badge ${inc.severity === 'Critical' ? 'badge-critical' : 'badge-high'}">${inc.severity}</span>
        </div>
        <div>Affected: ${inc.people_affected} | Score: <strong>${inc.priority_score}</strong></div>
        <div style="color: #94a3b8; font-size: 0.7rem; margin-top:2px;">Status: ${inc.status} ${inc.assigned_supplier ? '→ ' + inc.assigned_supplier : ''}</div>
      </div>
    `).join("");

    // Place Incident Markers
    data.incidents.forEach(inc => {
      if (!incidentMarkers[inc.id]) {
        const pinIcon = L.divIcon({
          html: `<div style="background:#ef4444;width:14px;height:14px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 12px #ef4444, 0 0 4px #ef4444; animation: radar-ping 1.5s infinite;"></div>`,
          iconSize: [14, 14],
          iconAnchor: [7, 7]
        });
        incidentMarkers[inc.id] = L.marker([inc.y, inc.x], { icon: pinIcon }).addTo(map)
          .bindPopup(`<strong>${inc.id}</strong>: ${inc.type}<br>Score: ${inc.priority_score}`);
      } else {
        incidentMarkers[inc.id].setLatLng([inc.y, inc.x]);
      }
    });
  } else {
    incContainer.innerHTML = `<div class="empty-state">No incidents detected in sector.</div>`;
  }

  // 5. Dynamic Obstacles
  if (data.obstacles) {
    obstacleMarkers.forEach(m => map.removeLayer(m));
    obstacleMarkers = [];
    data.obstacles.forEach(obs => {
      const circle = L.circle([obs.lat, obs.lng], {
        radius: 2000,
        color: "#fb923c",
        fillColor: "#fb923c",
        fillOpacity: 0.3
      }).addTo(map);
      obstacleMarkers.push(circle);
    });
  }

  // 6. Fleet Telemetry, Markers & Flight Trails
  const droneListElem = document.getElementById("drone-list");
  let droneListHtml = "";

  data.drones.forEach(d => {
    const previousDrone = currentDronesData[d.id];
    const startedScanning = previousDrone?.status === "Redeploying" && d.status === "Scanning";
    const idleSupplier = d.type === "Supplier" && (d.status === "Idle" || d.status === "Landed - Idle");
    const droneLat = idleSupplier ? BASE_LAT : d.y;
    const droneLng = idleSupplier ? BASE_LNG : d.x;
    currentDronesData[d.id] = { ...d, x: droneLng, y: droneLat };

    const isScanning = d.status === "Scanning";

    // Update / Render Marker
    if (!droneMarkers[d.id]) {
      droneMarkers[d.id] = L.marker([droneLat, droneLng], {
        icon: createDroneSVG(d.id, d.type, isScanning)
      }).addTo(map).on("click", () => openInspector(d.id));

      flightTrails[d.id] = L.polyline([], {
        color: d.type === "Scanner" ? "#00e5ff" : "#ffea00",
        weight: 1.5,
        opacity: 0.5
      }).addTo(map);
    } else {
      droneMarkers[d.id].setLatLng([droneLat, droneLng]);
      droneMarkers[d.id].setIcon(createDroneSVG(d.id, d.type, isScanning));
    }

    // Append to breadcrumb trail (capped at 60 historic points)
    const trail = flightTrails[d.id];
    if (startedScanning || idleSupplier) trail.setLatLngs([]);
    trail.addLatLng([droneLat, droneLng]);
    const latLngs = trail.getLatLngs();
    if (latLngs.length > 60) latLngs.shift();
    trail.setLatLngs(latLngs);

    // Build sidebar card
    droneListHtml += `
      <div class="drone-card ${d.type.toLowerCase()}" onclick="openInspector('${d.id}')">
        <div class="drone-card-header">
          <span>${d.id} [${d.type}]</span>
          <span>${d.battery}%</span>
        </div>
        <div class="drone-card-sub">
          <span>${d.status}</span>
          <span>${d.z}m | ${d.velocity}m/s</span>
        </div>
        <div class="bat-bar">
          <div class="bat-fill" style="width: ${d.battery}%; background: ${d.battery <= 20 ? '#ef4444' : '#22c55e'};"></div>
        </div>
      </div>
    `;
  });
  droneListElem.innerHTML = droneListHtml;

  // 7. Operations Console Log
  if (data.alerts) {
    const termBody = document.getElementById("terminal-body");
    termBody.innerHTML = data.alerts.map(msg => {
      let cls = "log-sys";
      if (msg.includes("[CRIT]")) cls = "log-crit";
      else if (msg.includes("[AI]")) cls = "log-ai";
      else if (msg.includes("[WEATHER]")) cls = "log-weather";
      else if (msg.includes("[ALERT]")) cls = "log-alert";
      return `<div class="${cls}">${msg}</div>`;
    }).join("");
  }
}

// Inspector View
function openInspector(droneId) {
  const d = currentDronesData[droneId];
  if (!d) return;

  document.getElementById("insp-id").innerText = `${d.id} Telemetry Profile`;
  const grid = document.getElementById("insp-grid");
  grid.innerHTML = `
    <div><strong>Role:</strong> ${d.type}</div>
    <div><strong>Network:</strong> ${d.net}</div>
    <div><strong>Status:</strong> ${d.status}</div>
    <div><strong>Altitude:</strong> ${d.z} m</div>
    <div><strong>Velocity:</strong> ${d.velocity} m/s</div>
    <div><strong>Battery:</strong> ${d.battery}%</div>
    <div><strong>Work Done:</strong> ${d.work_pct}%</div>
    <div><strong>Est. Uptime:</strong> ${d.remaining_uptime_s}s</div>
    <div><strong>Est. ETA:</strong> ${d.eta_s}s</div>
  `;
  document.getElementById("inspector-modal").style.display = "block";
}

function closeInspector() {
  document.getElementById("inspector-modal").style.display = "none";
}

// Weather drawer toggling
document.getElementById("weather-tab").onclick = () => {
  document.getElementById("weather-drawer").classList.toggle("open");
};

function setWeather(preset) {
  const payload = { type: "set_weather", preset: preset };
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(payload));
  }
}

// --- WebSocket Client & Standalone Parity Engine ---
let socket = null;

function connectWebSocket() {
  const dot = document.getElementById("conn-dot");
  socket = new WebSocket(`ws://${window.location.host}/ws`);

  socket.onopen = () => {
    dot.classList.add("connected");
  };

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    updateUI(data);
  };

  socket.onclose = () => {
    dot.classList.remove("connected");
    setTimeout(connectWebSocket, 3000);
  };

  socket.onerror = () => {
    socket.close();
  };
}

// Initialize Application
window.onload = () => {
  initMap();
  connectWebSocket();
};
