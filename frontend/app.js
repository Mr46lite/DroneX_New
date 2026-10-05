// DroneX Swarm System - Advanced SAR (Chennai Sector)

const BASE_STATION = { x: 80.2550, y: 13.0600 }; 

const map = L.map('map').setView([BASE_STATION.y, BASE_STATION.x], 12);

// Standard Dark Map Tile Layer
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '© OpenStreetMap contributors © CARTO',
    maxZoom: 17
}).addTo(map);

// Inject Custom Styles for 2D Icons & UI
const styleSheet = document.createElement("style");
styleSheet.innerText = `
    @keyframes radarPulse {
        0% { transform: translate(-50%, -50%) scale(0.3); opacity: 0.8; }
        100% { transform: translate(-50%, -50%) scale(2.0); opacity: 0; }
    }
    .radar-pulse-ring {
        position: absolute; top: 50%; left: 50%; width: 50px; height: 50px;
        border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 50%; background: rgba(56, 189, 248, 0.05);
        pointer-events: none; animation: radarPulse 2s infinite cubic-bezier(0.215, 0.61, 0.355, 1);
    }
    .base-station-darkred {
        background-color: #450a0a !important; color: #fca5a5 !important;
        border: 2px solid #ef4444 !important; box-shadow: 0 0 15px rgba(239, 68, 68, 0.8) !important;
        border-radius: 50%; display: flex; align-items: center; justify-content: center;
        font-weight: bold; font-size: 14px;
    }
    .person-pin-icon {
        font-size: 10px; text-align: center;
        background: #ef4444; border: 2px solid #ffffff; color: white;
        border-radius: 50%; width: 12px !important; height: 12px !important;
        box-shadow: 0 0 10px rgba(239, 68, 68, 0.8);
    }
    .obstacle-icon {
        background: #f97316; border: 2px solid #ea580c; border-radius: 50%;
        width: 16px !important; height: 16px !important; box-shadow: 0 0 10px rgba(249, 115, 22, 0.6);
    }
    #left-side-panel {
        position: absolute; top: 10px; left: 10px; bottom: 10px; width: 280px;
        z-index: 1000; background: rgba(15, 23, 42, 0.92); border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 8px; backdrop-filter: blur(8px); display: flex; flex-direction: column;
        padding: 12px; color: #fff; font-family: sans-serif;
    }
    #right-side-panel {
        position: absolute; top: 10px; right: 10px; width: 280px;
        z-index: 1000; background: rgba(15, 23, 42, 0.92); border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 8px; backdrop-filter: blur(8px); padding: 12px; color: #fff; font-family: sans-serif;
    }
    .panel-widget { background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 10px; margin-bottom: 10px; }
    .widget-title { font-size: 11px; font-weight: bold; color: #38bdf8; text-transform: uppercase; margin-bottom: 6px; }
    .legend-item { display: flex; align-items: center; gap: 8px; font-size: 11px; margin-bottom: 6px; }
    .color-box { width: 14px; height: 14px; border-radius: 3px; flex-shrink: 0; }
    .bat-bar-bg { width: 100%; height: 6px; background: rgba(255, 255, 255, 0.15); border-radius: 3px; overflow: hidden; margin-top: 4px; }
    .bat-bar-fill { height: 100%; transition: width 0.3s ease; }
`;
document.head.appendChild(styleSheet);

// Layout Panels
document.body.insertAdjacentHTML('beforeend', `
    <div id="left-side-panel">
        <div class="panel-widget">
            <div class="widget-title">⛅ Weather & Comms</div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:4px; font-size:11px; color:#cbd5e1;">
                <div>Wind: 12 km/h NE</div><div>Visibility: 10 km</div>
                <div>Condition: Clear</div><div>Temp: 29°C</div>
            </div>
        </div>
        <div class="widget-title">🔋 Fleet Battery & Status</div>
        <div id="drone-list-left" style="flex:1; overflow-y:auto;"></div>
    </div>
    <div id="right-side-panel">
        <div class="panel-widget">
            <div class="widget-title">⚠️ Dynamic Obstacles</div>
            <div style="font-size: 11px; color: #cbd5e1; margin-bottom: 8px;">Click map to spawn an obstacle.</div>
            <button id="clear-obs-btn" style="width:100%; padding: 6px; background: #dc2626; color: white; border: none; border-radius: 4px; font-size: 11px; font-weight: bold; cursor: pointer;">Clear All</button>
        </div>
        <div class="panel-widget">
            <div class="widget-title">MAP Sector Division</div>
            <div class="legend-item"><div class="color-box" style="background: rgba(14, 165, 233, 0.7); border: 1px solid #0ea5e9;"></div><div>Grid 1 (West Slice)</div></div>
            <div class="legend-item"><div class="color-box" style="background: rgba(56, 189, 248, 0.7); border: 1px solid #38bdf8;"></div><div>Grid 2 (Central Slice)</div></div>
            <div class="legend-item"><div class="color-box" style="background: rgba(2, 132, 199, 0.7); border: 1px solid #0284c7;"></div><div>Grid 3 (East Slice)</div></div>
            <div class="legend-item"><div class="color-box" style="background: rgba(3, 105, 161, 0.7); border: 1px solid #0369a1;"></div><div>Grid 4 (Coastline Slice)</div></div>
        </div>
    </div>
`);

const baseIcon = L.divIcon({ className: 'base-station-darkred', html: 'H', iconSize: [36, 36] });
L.marker([BASE_STATION.y, BASE_STATION.x], { icon: baseIcon, zIndexOffset: 2000 }).addTo(map);

// 4 Equal Vertical Slices strictly fitted to the Chennai Coast
const ZONES = [
    { id: 'Z1', polygon: [[13.02, 80.200], [13.10, 80.200], [13.10, 80.225], [13.02, 80.225]], color: '#0ea5e9' },
    { id: 'Z2', polygon: [[13.02, 80.225], [13.10, 80.225], [13.10, 80.250], [13.02, 80.250]], color: '#38bdf8' },
    { id: 'Z3', polygon: [[13.02, 80.250], [13.10, 80.250], [13.09, 80.270], [13.03, 80.270]], color: '#0284c7' },
    { id: 'Z4', polygon: [[13.03, 80.270], [13.09, 80.270], [13.08, 80.285], [13.05, 80.285]], color: '#0369a1' } 
];

ZONES.forEach((z) => {
    L.polygon(z.polygon, { color: z.color, weight: 2, fillOpacity: 0.15 }).addTo(map);
});

const obstacles = [];
const obstacleMarkers = [];

map.on('click', function (e) {
    const obs = { x: e.latlng.lng, y: e.latlng.lat, radius: 0.012 };
    obstacles.push(obs);
    const marker = L.marker([obs.y, obs.x], { icon: L.divIcon({ className: 'obstacle-icon' }) }).addTo(map);
    obstacleMarkers.push(marker);
});

document.getElementById('clear-obs-btn').addEventListener('click', () => {
    obstacleMarkers.forEach(m => map.removeLayer(m));
    obstacleMarkers.length = 0; obstacles.length = 0;
});

function isPointInPolygon(point, vs) {
    let x = point[0], y = point[1], inside = false;
    for (let i = 0, j = vs.length - 1; i < vs.length; j = i++) {
        let xi = vs[i][0], yi = vs[i][1], xj = vs[j][0], yj = vs[j][1];
        let intersect = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
        if (intersect) inside = !inside;
    }
    return inside;
}

// Boustrophedon (Lawnmower) Generator
function generateGridWaypoints(polygon) {
    const lats = polygon.map(p => p[0]);
    const lngs = polygon.map(p => p[1]);
    const minLat = Math.min(...lats) + 0.002;
    const maxLat = Math.max(...lats) - 0.002;
    const minLng = Math.min(...lngs) + 0.002;
    const maxLng = Math.max(...lngs) - 0.002;

    const wps = [];
    const step = 0.003; 
    let reverse = false;

    for (let lat = minLat; lat <= maxLat; lat += step) {
        let row = [];
        for (let lng = minLng; lng <= maxLng; lng += step) {
            if (isPointInPolygon([lat, lng], polygon)) { row.push({ x: lng, y: lat }); }
        }
        if (row.length > 0) {
            if (reverse) row.reverse();
            wps.push(...row);
            reverse = !reverse;
        }
    }
    return wps;
}

const zoneWaypoints = ZONES.map(z => generateGridWaypoints(z.polygon));

let survivors = [
    { id: 'S1', x: 80.215, y: 13.080, detected: false, served: false, assigned: false, marker: null },
    { id: 'S2', x: 80.280, y: 13.065, detected: false, served: false, assigned: false, marker: null }
];

let drones = [
    { id: 'Scanner 1', label: '1', type: 'Scanner', bat: 100, x: BASE_STATION.x, y: BASE_STATION.y, assignedZone: 0, wpIdx: 0, state: 'DEPLOYING' },
    { id: 'Scanner 2', label: '2', type: 'Scanner', bat: 100, x: BASE_STATION.x, y: BASE_STATION.y, assignedZone: 1, wpIdx: 0, state: 'DEPLOYING' },
    { id: 'Scanner 3', label: '3', type: 'Scanner', bat: 100, x: BASE_STATION.x, y: BASE_STATION.y, assignedZone: 2, wpIdx: 0, state: 'DEPLOYING' },
    { id: 'Scanner 4', label: '4', type: 'Scanner', bat: 100, x: BASE_STATION.x, y: BASE_STATION.y, assignedZone: 3, wpIdx: 0, state: 'DEPLOYING' },
    { id: 'Supplier 5', label: '5', type: 'Supplier', bat: 100, x: BASE_STATION.x, y: BASE_STATION.y, state: 'IDLE', targetSurv: null },
    { id: 'Supplier 6', label: '6', type: 'Supplier', bat: 100, x: BASE_STATION.x, y: BASE_STATION.y, state: 'IDLE', targetSurv: null }
];
const markers = {};

// Accurate 2D Quadcopter SVG Icon with Numbers
function createQuadcopterIcon(drone) {
    const isScanner = drone.type === 'Scanner';
    const color = isScanner ? '#38bdf8' : '#facc15';
    // Transparent pulse ONLY for scanners sweeping/deploying
    const ring = (isScanner && (drone.state === 'SWEEPING' || drone.state === 'DEPLOYING')) ? `<div class="radar-pulse-ring"></div>` : '';

    const svgIcon = `
        <div style="position:relative; width:44px; height:44px; display:flex; justify-content:center; align-items:center;">
            ${ring}
            <svg width="40" height="40" viewBox="0 0 100 100" style="position:absolute; z-index:10;">
                <ellipse cx="22" cy="22" rx="16" ry="6" fill="#64748b" transform="rotate(-45 22 22)"/>
                <ellipse cx="78" cy="22" rx="16" ry="6" fill="#64748b" transform="rotate(45 78 22)"/>
                <ellipse cx="22" cy="78" rx="16" ry="6" fill="#64748b" transform="rotate(45 22 78)"/>
                <ellipse cx="78" cy="78" rx="16" ry="6" fill="#64748b" transform="rotate(-45 78 78)"/>
                <circle cx="22" cy="22" r="8" fill="#334155"/>
                <circle cx="78" cy="22" r="8" fill="#334155"/>
                <circle cx="22" cy="78" r="8" fill="#334155"/>
                <circle cx="78" cy="78" r="8" fill="#334155"/>
                <path d="M 22 22 L 78 78 M 78 22 L 22 78" stroke="#cbd5e1" stroke-width="8" stroke-linecap="round"/>
                <circle cx="50" cy="50" r="22" fill="${color}" stroke="#ffffff" stroke-width="3"/>
                <text x="50" y="55" font-size="20" font-weight="bold" fill="#0f172a" text-anchor="middle" dominant-baseline="middle">${drone.label}</text>
            </svg>
        </div>
    `;
    return L.divIcon({ className: 'custom-quadcopter-icon', html: svgIcon, iconSize: [44, 44], iconAnchor: [22, 22] });
}

function getAvoidanceVector(drone, target, speed) {
    let dx = target.x - drone.x, dy = target.y - drone.y;
    let dist = Math.hypot(dx, dy);
    if (dist === 0) return { dx: 0, dy: 0, dist: 0 };

    let stepX = (dx / dist) * speed;
    let stepY = (dy / dist) * speed;

    for (const obs of obstacles) {
        const obsDist = Math.hypot(obs.x - drone.x, obs.y - drone.y);
        if (obsDist < obs.radius * 1.2) {
            let severity = Math.pow(1.0 - (obsDist / (obs.radius * 1.2)), 2); 
            const perpX = -(obs.y - drone.y), perpY = obs.x - drone.x;
            const perpDist = Math.hypot(perpX, perpY) || 1;
            
            stepX = (stepX * (1 - severity)) + ((perpX / perpDist) * speed * severity * 0.5);
            stepY = (stepY * (1 - severity)) + ((perpY / perpDist) * speed * severity * 0.5);
            break; 
        }
    }
    return { dx: stepX, dy: stepY, dist };
}

function assignSuppliers() {
    survivors.forEach(surv => {
        if (!surv.detected || surv.served || surv.assigned) return;
        const supplier = drones.find(d => d.type === 'Supplier' && d.state === 'IDLE');
        if (!supplier) return;
        supplier.x = BASE_STATION.x; supplier.y = BASE_STATION.y;
        supplier.state = 'DELIVERING';
        supplier.targetSurv = surv;
        surv.assigned = true;
    });
}

function updateDronePositions() {
    const speed = 0.0006; 

    drones.forEach(drone => {
        if (drone.state === 'IDLE') return;

        if (drone.state === 'CHARGING') {
            drone.bat += 2.0; 
            if (drone.bat >= 100) {
                drone.bat = 100;
                drone.state = drone.type === 'Scanner' ? 'DEPLOYING' : 'IDLE';
            }
            return;
        }

        drone.bat = Math.max(0, drone.bat - 0.05);

        if (drone.bat <= 20 && drone.state !== 'RETURNING') {
            drone.state = 'RETURNING';
            if (drone.targetSurv) { drone.targetSurv.assigned = false; drone.targetSurv = null; } 
        }

        if (drone.state === 'RETURNING') {
            const move = getAvoidanceVector(drone, BASE_STATION, speed * 1.5);
            if (move.dist > 0.001) {
                drone.x += move.dx; drone.y += move.dy;
            } else {
                drone.state = 'CHARGING';
                drone.x = BASE_STATION.x; drone.y = BASE_STATION.y;
            }
        } 
        
        else if (drone.type === 'Scanner') {
            const wps = zoneWaypoints[drone.assignedZone];
            if (wps && drone.wpIdx < wps.length) {
                const target = wps[drone.wpIdx];
                const move = getAvoidanceVector(drone, target, speed);

                if (move.dist > 0.0008) {
                    let nx = drone.x + move.dx, ny = drone.y + move.dy;
                    if (drone.state === 'SWEEPING' && !isPointInPolygon([ny, nx], ZONES[drone.assignedZone].polygon)) {
                        nx = drone.x + (target.x - drone.x) / move.dist * speed;
                        ny = drone.y + (target.y - drone.y) / move.dist * speed;
                    }
                    drone.x = nx; drone.y = ny;
                } else {
                    if (drone.state === 'DEPLOYING') drone.state = 'SWEEPING';
                    drone.wpIdx++;
                }

                if (drone.state === 'SWEEPING') {
                    survivors.forEach(surv => {
                        if (!surv.detected && Math.hypot(surv.x - drone.x, surv.y - drone.y) < 0.015) {
                            surv.detected = true;
                            surv.marker = L.marker([surv.y, surv.x], { icon: L.divIcon({ className: 'person-pin-icon' }) }).addTo(map);
                        }
                    });
                }
            } else if (drone.state === 'SWEEPING') {
                drone.wpIdx = 0;
                wps.reverse(); 
            }
        } 
        
        else if (drone.type === 'Supplier' && drone.state === 'DELIVERING' && drone.targetSurv) {
            const move = getAvoidanceVector(drone, drone.targetSurv, speed * 1.2);
            if (move.dist > 0.001) {
                drone.x += move.dx; drone.y += move.dy;
            } else {
                drone.targetSurv.served = true;
                if (drone.targetSurv.marker) { map.removeLayer(drone.targetSurv.marker); drone.targetSurv.marker = null; }
                drone.targetSurv = null; 
                drone.state = 'RETURNING';
            }
        }
    });

    assignSuppliers();
    renderUI();
}

function renderUI() {
    let panelHTML = '';
    drones.forEach(drone => {
        let batColor = drone.bat > 50 ? '#4ade80' : (drone.bat > 20 ? '#facc15' : '#ef4444');
        let status = drone.state === 'CHARGING' ? 'Charging at Base' : drone.state;
        
        panelHTML += `
            <div style="margin-bottom: 8px; padding: 8px; background: rgba(30, 41, 59, 0.6); border-radius: 6px; border: 1px solid rgba(255,255,255,0.08);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 11px; font-weight: bold; color: #fff;">${drone.id}</span>
                    <span style="font-size: 10px; font-weight: bold; color: ${batColor};">${Math.round(drone.bat)}%</span>
                </div>
                <div style="font-size: 10px; color: #94a3b8; margin-top:2px;">Status: ${status}</div>
                <div class="bat-bar-bg"><div class="bat-bar-fill" style="width: ${drone.bat}%; background-color: ${batColor};"></div></div>
            </div>`;

        if (drone.state !== 'IDLE' && drone.state !== 'CHARGING') {
            if (!markers[drone.id]) {
                markers[drone.id] = L.marker([drone.y, drone.x], { icon: createQuadcopterIcon(drone) }).addTo(map);
            } else {
                markers[drone.id].setLatLng([drone.y, drone.x]);
                markers[drone.id].setIcon(createQuadcopterIcon(drone));
            }
        } else if (markers[drone.id]) {
            map.removeLayer(markers[drone.id]);
            delete markers[drone.id];
        }
    });

    const leftList = document.getElementById('drone-list-left');
    if (leftList) leftList.innerHTML = panelHTML;
}

// Continuous Civilian Spawner
setInterval(() => {
    const activeCivs = survivors.filter(s => !s.served);
    if (activeCivs.length < 3) {
        survivors.push({
            id: 'S' + Date.now(),
            x: 80.200 + (Math.random() * 0.08),
            y: 13.020 + (Math.random() * 0.08),
            detected: false, served: false, assigned: false, marker: null
        });
    }
}, 7000);

setInterval(updateDronePositions, 100);
