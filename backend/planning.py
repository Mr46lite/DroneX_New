"""Path planning: Boustrophedon sweep order and A* routing over the zone grid."""
import heapq
import itertools
import math

BASE_POS = (12.9675, 77.5875)
NEIGHBOR_RADIUS = 0.008   # zones this close are linked (grid neighbours, diagonals included)
START_RADIUS = 0.009      # how far from a node a mid-air drone can join the graph
CLEARANCE = 0.002         # a leg may not pass closer than this to a blocked zone


def get_distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def _dist_point_segment(p, a, b):
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return get_distance(p, a)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length2))
    return get_distance(p, (ax + t * dx, ay + t * dy))


def segment_clear(a, b, blocked_positions):
    """True if the straight leg a->b stays clear of every blocked zone.
    A blocked zone the leg already starts inside of is ignored (the drone is there)."""
    for p in blocked_positions:
        if get_distance(a, p) <= CLEARANCE:
            continue
        if _dist_point_segment(p, a, b) < CLEARANCE:
            return False
    return True


def route_is_clear(start, waypoints, blocked_positions):
    prev = start
    for w in waypoints:
        if not segment_clear(prev, w, blocked_positions):
            return False
        prev = w
    return True


def boustrophedon_path(zones):
    """Lawnmower sweep order: row by row, flipping direction on every row."""
    rows = {}
    for z in zones:
        rows.setdefault(round(z["lat"], 6), []).append(z)
    path = []
    for i, lat in enumerate(sorted(rows)):
        row = sorted(rows[lat], key=lambda z: z["lng"], reverse=(i % 2 == 1))
        path.extend(z["id"] for z in row)
    return path


def _nodes(zones):
    nodes = {z["id"]: (z["lat"], z["lng"]) for z in zones}
    nodes["BASE"] = BASE_POS
    return nodes


def a_star_route(start, target, blocked_ids, all_zones):
    """A* over the zone grid.

    start:  (lat, lng) position or a node id (e.g. "Z3", "BASE")
    target: node id, or a (lat, lng) that is snapped to the nearest node
    Returns a list of (lat, lng) waypoints ending at the target, or None when the
    target is blocked or unreachable. Blocked zones are never used as waypoints and
    legs never fly over them.
    """
    nodes = _nodes(all_zones)
    blocked = set(blocked_ids)
    blocked_pos = [nodes[b] for b in blocked if b in nodes]

    if isinstance(target, str):
        if target not in nodes:
            return None
        target_id = target
    else:
        target_id = min(nodes, key=lambda n: get_distance(target, nodes[n]))
    if target_id in blocked:
        return None
    target_pos = nodes[target_id]
    start_pos = nodes[start] if isinstance(start, str) else tuple(start)

    def neighbours(node):
        if node == "START":
            cands = [(get_distance(start_pos, p), n) for n, p in nodes.items() if n not in blocked]
            near = [(d, n) for d, n in cands
                    if d <= START_RADIUS and segment_clear(start_pos, nodes[n], blocked_pos)]
            return near or ([min(cands)] if cands else [])
        a = nodes[node]
        out = []
        for n, p in nodes.items():
            if n == node or n in blocked:
                continue
            d = get_distance(a, p)
            if d <= NEIGHBOR_RADIUS and segment_clear(a, p, blocked_pos):
                out.append((d, n))
        return out

    counter = itertools.count()
    frontier = [(get_distance(start_pos, target_pos), next(counter), 0.0, "START", ["START"])]
    best = {"START": 0.0}
    while frontier:
        _, _, g, cur, path = heapq.heappop(frontier)
        if cur == target_id:
            wps = [nodes[n] for n in path[1:]]
            while len(wps) > 1 and get_distance(wps[0], start_pos) < 1e-9:
                wps.pop(0)
            return wps
        if g > best.get(cur, math.inf):
            continue
        for d, n in neighbours(cur):
            ng = g + d
            if ng < best.get(n, math.inf):
                best[n] = ng
                heapq.heappush(
                    frontier,
                    (ng + get_distance(nodes[n], target_pos), next(counter), ng, n, path + [n]),
                )
    return None
