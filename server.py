import socket
import json
import math
import time
import random

HOST = "0.0.0.0"
PORT = 5555
TICK = 30

DAMAGE = 50
MAX_SHOT_DIST = 250.0
PLAYER_RADIUS = 1.6
EYE_HEIGHT = 1.6
TARGET_CENTER_HEIGHT = 1.2
PLAYER_TIMEOUT = 5.0

MAP_SEED = 1234
ARENA_HALF = 80.0

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind((HOST, PORT))
sock.settimeout(0.01)

clients = {}
players = {}
next_id = 1


# --------------------------------------------------
# MAP GENERATION
# --------------------------------------------------

def block(x, y, z, w, h, d, tex, c=None):
    b = {
        "x": float(x),
        "y": float(y),
        "z": float(z),
        "w": float(w),
        "h": float(h),
        "d": float(d),
        "t": int(tex),
    }

    if c is not None:
        b["c"] = [int(c[0]), int(c[1]), int(c[2])]

    return b


def rand_color():
    return [
        random.randint(120, 240),
        random.randint(120, 240),
        random.randint(120, 240),
    ]


def generate_map():
    random.seed(MAP_SEED)

    blocks = []
    half = ARENA_HALF

    # Outer walls
    wall_h = 7.0
    wall_t = 2.0

    blocks.append(block(0, wall_h / 2, -half, half * 2 + wall_t * 2, wall_h, wall_t, 1))
    blocks.append(block(0, wall_h / 2, half, half * 2 + wall_t * 2, wall_h, wall_t, 1))
    blocks.append(block(-half, wall_h / 2, 0, wall_t, wall_h, half * 2, 1))
    blocks.append(block(half, wall_h / 2, 0, wall_t, wall_h, half * 2, 1))

    # Corner pillars
    for sx in [-half, half]:
        for sz in [-half, half]:
            blocks.append(block(sx, (wall_h + 2) / 2, sz, 6, wall_h + 2, 6, 2))

    # Central tower
    blocks.append(block(0, 5, 0, 16, 10, 16, 2))
    blocks.append(block(0, 10.75, 0, 12, 1.5, 12, 1))
    blocks.append(block(0, 15, 0, 8, 8, 8, 1))
    blocks.append(block(0, 20.5, 0, 10, 1.5, 10, 2))

    # Corner buildings
    corners = [
        (-42, -42),
        (42, -42),
        (-42, 42),
        (42, 42),
    ]

    for cx, cz in corners:
        w = random.uniform(12, 18)
        h = random.uniform(10, 18)
        d = random.uniform(12, 18)

        blocks.append(block(cx, h / 2, cz, w, h, d, 1, rand_color()))
        blocks.append(block(cx, h + 0.75, cz, w + 2, 1.5, d + 2, 2))

        # Small side annex
        ax = cx + random.choice([-1, 1]) * (w / 2 + 5)
        az = cz + random.choice([-1, 1]) * 5

        aw = random.uniform(5, 8)
        ah = random.uniform(4, 7)
        ad = random.uniform(5, 8)

        blocks.append(block(ax, ah / 2, az, aw, ah, ad, 2))

    # Mid cover walls
    cover_positions = [
        (-25, 0),
        (25, 0),
        (0, -25),
        (0, 25),
    ]

    for cx, cz in cover_positions:
        blocks.append(block(cx, 1.5, cz, 8, 3, 2, 1))

    # Crates
    for _ in range(24):
        x = random.uniform(-70, 70)
        z = random.uniform(-70, 70)

        # Keep central tower area clearer
        if abs(x) < 14 and abs(z) < 14:
            continue

        s = random.uniform(1.6, 3.4)

        blocks.append(
            block(
                x,
                s / 2,
                z,
                s,
                s,
                s,
                random.choice([1, 2]),
                rand_color(),
            )
        )

    # Roads / paths
    # These are thin and do not block bullets because h < 0.5
    blocks.append(block(0, 0.05, 0, 10, 0.1, half * 2 - 6, 2, [80, 85, 95]))
    blocks.append(block(0, 0.05, 0, half * 2 - 6, 0.1, 10, 2, [80, 85, 95]))

    # Spawn pads
    spawn_pads = [
        (-65, -65),
        (65, 65),
        (-65, 65),
        (65, -65),
    ]

    for sx, sz in spawn_pads:
        blocks.append(block(sx, 0.1, sz, 8, 0.2, 8, 0, [100, 180, 100]))

    return {
        "arena_half": ARENA_HALF,
        "blocks": blocks,
    }


map_data = generate_map()

print("Server map generated")
print("Map block count:", len(map_data["blocks"]))


# --------------------------------------------------
# MAP COLLISION / SPAWN HELPERS
# --------------------------------------------------

def is_blocked(x, z, radius=1.2):
    for b in map_data["blocks"]:
        h = float(b.get("h", 0))

        # Ignore thin roads/pads
        if h < 0.5:
            continue

        min_x = b["x"] - b["w"] / 2 - radius
        max_x = b["x"] + b["w"] / 2 + radius

        min_z = b["z"] - b["d"] / 2 - radius
        max_z = b["z"] + b["d"] / 2 + radius

        if min_x <= x <= max_x and min_z <= z <= max_z:
            bottom = b["y"] - h / 2
            top = b["y"] + h / 2

            # Player body roughly from ground to height 2
            if bottom < 2.0 and top > 0.0:
                return True

    return False


def spawn_point():
    for _ in range(40):
        x = random.uniform(-ARENA_HALF + 6, ARENA_HALF - 6)
        z = random.uniform(-ARENA_HALF + 6, ARENA_HALF - 6)

        if not is_blocked(x, z):
            return x, 0.0, z

    # Fallback spawn
    return 0.0, 0.0, ARENA_HALF - 10.0


# --------------------------------------------------
# RAY / HIT HELPERS
# --------------------------------------------------

def normalize(v):
    x, y, z = v
    length = math.sqrt(x * x + y * y + z * z)

    if length < 0.0001:
        return 0.0, 0.0, 1.0

    return x / length, y / length, z / length


def ray_hits_sphere(
    ox, oy, oz,
    dx, dy, dz,
    tx, ty, tz,
    radius=PLAYER_RADIUS,
    max_dist=MAX_SHOT_DIST
):
    rx = tx - ox
    ry = ty - oy
    rz = tz - oz

    projection = rx * dx + ry * dy + rz * dz

    if projection < 0 or projection > max_dist:
        return False, float("inf")

    closest_x = ox + dx * projection
    closest_y = oy + dy * projection
    closest_z = oz + dz * projection

    dist2 = (tx - closest_x) ** 2 + (ty - closest_y) ** 2 + (tz - closest_z) ** 2

    return dist2 <= radius * radius, projection


def ray_hits_aabb(ox, oy, oz, dx, dy, dz, b, max_dist):
    min_x = b["x"] - b["w"] / 2
    max_x = b["x"] + b["w"] / 2

    min_y = b["y"] - b["h"] / 2
    max_y = b["y"] + b["h"] / 2

    min_z = b["z"] - b["d"] / 2
    max_z = b["z"] + b["d"] / 2

    tmin = 0.0
    tmax = max_dist

    # X axis
    if abs(dx) < 0.000001:
        if ox < min_x or ox > max_x:
            return False, float("inf")
    else:
        t1 = (min_x - ox) / dx
        t2 = (max_x - ox) / dx

        if t1 > t2:
            t1, t2 = t2, t1

        tmin = max(tmin, t1)
        tmax = min(tmax, t2)

        if tmin > tmax:
            return False, float("inf")

    # Y axis
    if abs(dy) < 0.000001:
        if oy < min_y or oy > max_y:
            return False, float("inf")
    else:
        t1 = (min_y - oy) / dy
        t2 = (max_y - oy) / dy

        if t1 > t2:
            t1, t2 = t2, t1

        tmin = max(tmin, t1)
        tmax = min(tmax, t2)

        if tmin > tmax:
            return False, float("inf")

    # Z axis
    if abs(dz) < 0.000001:
        if oz < min_z or oz > max_z:
            return False, float("inf")
    else:
        t1 = (min_z - oz) / dz
        t2 = (max_z - oz) / dz

        if t1 > t2:
            t1, t2 = t2, t1

        tmin = max(tmin, t1)
        tmax = min(tmax, t2)

        if tmin > tmax:
            return False, float("inf")

    if tmin < 0:
        return False, float("inf")

    return True, tmin


# --------------------------------------------------
# NETWORK HELPERS
# --------------------------------------------------

def send_msg(msg, addr):
    try:
        sock.sendto(json.dumps(msg).encode(), addr)
    except Exception as e:
        print("Send error:", e)


def broadcast(msg):
    for addr in list(clients.keys()):
        send_msg(msg, addr)


def send_map(addr):
    msg = {"type": "map"}
    msg.update(map_data)
    send_msg(msg, addr)


# --------------------------------------------------
# SERVER LOOP
# --------------------------------------------------

last_state_time = 0

print("3D Brick Sniper server running")
print(f"Listening on {HOST}:{PORT}")

try:
    while True:
        try:
            data, addr = sock.recvfrom(65535)
            msg = json.loads(data.decode())
            mtype = msg.get("type")

            if mtype == "join":
                if addr in clients:
                    pid = clients[addr]

                    if pid in players:
                        players[pid]["last_seen"] = time.time()
                        p = players[pid]

                        send_msg(
                            {
                                "type": "welcome",
                                "id": pid,
                                "x": p["x"],
                                "y": p["y"],
                                "z": p["z"],
                            },
                            addr,
                        )

                        send_map(addr)
                    else:
                        clients.pop(addr, None)

                else:
                    pid = next_id
                    next_id += 1

                    x, y, z = spawn_point()

                    clients[addr] = pid
                    players[pid] = {
                        "addr": addr,
                        "x": x,
                        "y": y,
                        "z": z,
                        "yaw": 0.0,
                        "health": 100,
                        "last_seen": time.time(),
                    }

                    print(f"Player {pid} joined from {addr}")

                    send_msg(
                        {
                            "type": "welcome",
                            "id": pid,
                            "x": x,
                            "y": y,
                            "z": z,
                        },
                        addr,
                    )

                    send_map(addr)

            elif mtype == "get_map":
                send_map(addr)

            elif mtype == "state":
                pid = msg.get("id")

                if clients.get(addr) == pid and pid in players:
                    players[pid]["x"] = float(msg.get("x", players[pid]["x"]))
                    players[pid]["y"] = float(msg.get("y", players[pid]["y"]))
                    players[pid]["z"] = float(msg.get("z", players[pid]["z"]))
                    players[pid]["yaw"] = float(msg.get("yaw", players[pid]["yaw"]))
                    players[pid]["last_seen"] = time.time()

            elif mtype == "shoot":
                pid = msg.get("id")

                if clients.get(addr) == pid and pid in players:
                    shooter = players[pid]

                    shooter["x"] = float(msg.get("x", shooter["x"]))
                    shooter["y"] = float(msg.get("y", shooter["y"]))
                    shooter["z"] = float(msg.get("z", shooter["z"]))
                    shooter["yaw"] = float(msg.get("yaw", shooter["yaw"]))
                    shooter["last_seen"] = time.time()

                    direction = normalize(msg.get("dir", [0.0, 0.0, 1.0]))

                    ox = shooter["x"]
                    oy = shooter["y"] + EYE_HEIGHT
                    oz = shooter["z"]

                    dx, dy, dz = direction

                    # Find closest player hit
                    best_id = None
                    best_player_dist = float("inf")

                    for target_id, target in players.items():
                        if target_id == pid:
                            continue

                        if target["health"] <= 0:
                            continue

                        tx = target["x"]
                        ty = target["y"] + TARGET_CENTER_HEIGHT
                        tz = target["z"]

                        hit, distance = ray_hits_sphere(
                            ox, oy, oz,
                            dx, dy, dz,
                            tx, ty, tz,
                        )

                        if hit and distance < best_player_dist:
                            best_player_dist = distance
                            best_id = target_id

                    # Find closest map wall/object hit
                    best_wall_dist = float("inf")

                    for b in map_data["blocks"]:
                        # Ignore thin roads/pads
                        if float(b.get("h", 0)) < 0.5:
                            continue

                        hit, distance = ray_hits_aabb(
                            ox, oy, oz,
                            dx, dy, dz,
                            b,
                            MAX_SHOT_DIST,
                        )

                        if hit and distance < best_wall_dist:
                            best_wall_dist = distance

                    hit_player = best_id is not None and best_player_dist <= best_wall_dist + 0.05

                    if not hit_player:
                        best_id = None

                    killed = False
                    respawn_x = None
                    respawn_y = None
                    respawn_z = None

                    if hit_player:
                        players[best_id]["health"] -= DAMAGE

                        if players[best_id]["health"] <= 0:
                            killed = True
                            players[best_id]["health"] = 100

                            respawn_x, respawn_y, respawn_z = spawn_point()

                            players[best_id]["x"] = respawn_x
                            players[best_id]["y"] = respawn_y
                            players[best_id]["z"] = respawn_z

                        print(f"Player {pid} shot player {best_id}, kill={killed}")

                    if hit_player:
                        shot_distance = best_player_dist
                    elif best_wall_dist < MAX_SHOT_DIST:
                        shot_distance = best_wall_dist
                    else:
                        shot_distance = MAX_SHOT_DIST

                    broadcast(
                        {
                            "type": "shot",
                            "shooter": pid,
                            "x": shooter["x"],
                            "y": shooter["y"],
                            "z": shooter["z"],
                            "yaw": shooter["yaw"],
                            "dir": [dx, dy, dz],
                            "hit": best_id,
                            "kill": killed,
                            "respawn_x": respawn_x,
                            "respawn_y": respawn_y,
                            "respawn_z": respawn_z,
                            "dist": shot_distance,
                        }
                    )

            elif mtype == "quit":
                pid = clients.pop(addr, None)

                if pid is not None and pid in players:
                    players.pop(pid, None)
                    print(f"Player {pid} left")

        except socket.timeout:
            pass

        except Exception as e:
            print("Server error:", e)

        now = time.time()

        stale_players = []

        for pid, p in players.items():
            if now - p.get("last_seen", now) > PLAYER_TIMEOUT:
                stale_players.append(pid)

        for pid in stale_players:
            p = players.pop(pid, None)

            if p:
                addr = p.get("addr")

                if addr and clients.get(addr) == pid:
                    clients.pop(addr, None)

                print(f"Player {pid} timed out")

        if now - last_state_time >= 1 / TICK:
            last_state_time = now

            state_players = []

            for pid, p in players.items():
                state_players.append(
                    {
                        "id": pid,
                        "x": p["x"],
                        "y": p["y"],
                        "z": p["z"],
                        "yaw": p["yaw"],
                        "health": p["health"],
                    }
                )

            broadcast(
                {
                    "type": "state",
                    "players": state_players,
                }
            )

except KeyboardInterrupt:
    print("\nServer stopped.")

finally:
    sock.close()