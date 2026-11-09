from ursina import *
import socket
import json
import threading
import queue
import sys
import random
import os
import time as pytime
from pathlib import Path

SERVER_IP = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = 5555

EYE_HEIGHT = 1.6
SPEED = 10.0
SHOOT_COOLDOWN = 0.7

SCRIPT_DIR = Path(__file__).resolve().parent
TEXTURE_DIR = SCRIPT_DIR / "textures"
SETTINGS_FILE = SCRIPT_DIR / "settings.json"

RESOLUTIONS = [
    (1280, 720),
    (1600, 900),
    (1920, 1080),
    (2560, 1440),
]

DRAW_DISTANCES = [200, 400, 800, 1200]
CROSSHAIR_SIZES = [0.5, 1.0, 1.5, 2.0]

DEFAULT_SETTINGS = {
    "fov": 90,
    "sensitivity": 300,
    "resolution_index": 2,
    "fullscreen": False,
    "draw_index": 2,
    "crosshair_index": 1,
    "show_fps": False,
}


# --------------------------------------------------
# SETTINGS LOAD / SAVE
# --------------------------------------------------

def safe_int(value, default):
    try:
        return int(value)
    except Exception:
        return default


def load_settings():
    s = DEFAULT_SETTINGS.copy()

    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text())
            s.update(data)
        except Exception as e:
            print("Could not load settings:", e)

    s["fov"] = max(60, min(120, safe_int(s.get("fov", 90), 90)))
    s["sensitivity"] = max(50, min(800, safe_int(s.get("sensitivity", 300), 300)))
    s["resolution_index"] = max(
        0,
        min(
            len(RESOLUTIONS) - 1,
            safe_int(s.get("resolution_index", 2), 2),
        ),
    )
    s["fullscreen"] = bool(s.get("fullscreen", False))
    s["draw_index"] = max(
        0,
        min(
            len(DRAW_DISTANCES) - 1,
            safe_int(s.get("draw_index", 2), 2),
        ),
    )
    s["crosshair_index"] = max(
        0,
        min(
            len(CROSSHAIR_SIZES) - 1,
            safe_int(s.get("crosshair_index", 1), 1),
        ),
    )
    s["show_fps"] = bool(s.get("show_fps", False))

    return s


settings = load_settings()


def save_settings():
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=4))
    except Exception as e:
        print("Could not save settings:", e)


try:
    os.chdir(SCRIPT_DIR)
    print("Working directory set to:", SCRIPT_DIR)
except Exception as e:
    print("Could not change working directory:", e)


# --------------------------------------------------
# PLACEHOLDER TEXTURE GENERATOR
# --------------------------------------------------

def ensure_placeholder_textures():
    needed = ["ground.png", "brick.png", "metal.png"]

    if all((TEXTURE_DIR / name).exists() for name in needed):
        return

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("No textures found.")
        print("To auto-create placeholder textures, install Pillow:")
        print("python -m pip install pillow")
        return

    try:
        TEXTURE_DIR.mkdir(exist_ok=True)
        random.seed(4)

        ground_path = TEXTURE_DIR / "ground.png"
        if not ground_path.exists():
            img = Image.new("RGB", (64, 64), (86, 150, 86))
            d = ImageDraw.Draw(img)

            for _ in range(800):
                x = random.randint(0, 63)
                y = random.randint(0, 63)
                r = random.randint(40, 90)
                g = random.randint(110, 180)
                b = random.randint(40, 90)
                d.point((x, y), fill=(r, g, b))

            for x in range(0, 64, 8):
                d.line((x, 0, x, 63), fill=(70, 120, 70), width=1)

            for y in range(0, 64, 8):
                d.line((0, y, 63, y), fill=(70, 120, 70), width=1)

            img.save(ground_path)

        brick_path = TEXTURE_DIR / "brick.png"
        if not brick_path.exists():
            img = Image.new("RGB", (64, 64), (150, 60, 50))
            d = ImageDraw.Draw(img)

            for y in range(0, 64, 16):
                d.rectangle((0, y, 63, y + 2), fill=(85, 85, 85))

            for row, y in enumerate(range(0, 64, 16)):
                offset = 0 if row % 2 == 0 else 8

                for x in range(offset, 64, 16):
                    d.rectangle((x, y, x + 2, y + 16), fill=(85, 85, 85))

            img.save(brick_path)

        metal_path = TEXTURE_DIR / "metal.png"
        if not metal_path.exists():
            img = Image.new("RGB", (64, 64), (130, 135, 145))
            d = ImageDraw.Draw(img)

            for _ in range(500):
                x = random.randint(0, 63)
                y = random.randint(0, 63)
                v = random.randint(110, 160)
                d.point((x, y), fill=(v, v, v + 5))

            for x, y in [(8, 8), (56, 8), (8, 56), (56, 56)]:
                d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(80, 85, 95))

            img.save(metal_path)

        print("Created placeholder textures in:", TEXTURE_DIR)

    except Exception as e:
        print("Could not create placeholder textures:", e)


ensure_placeholder_textures()


def print_texture_debug():
    print("Texture folder:", TEXTURE_DIR)
    print("Texture folder exists:", TEXTURE_DIR.exists())

    if TEXTURE_DIR.exists():
        try:
            files = [p.name for p in TEXTURE_DIR.iterdir()]
            print("Files found in textures folder:", files)
        except Exception as e:
            print("Could not list textures folder:", e)
    else:
        print("Textures folder does not exist.")


print_texture_debug()


def get_texture(name):
    path = TEXTURE_DIR / name
    exists = path.exists()

    if exists:
        return f"textures/{name}"

    return None


# --------------------------------------------------
# NETWORK SETUP
# --------------------------------------------------

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
incoming = queue.Queue()


def receive_messages():
    sock.settimeout(0.2)

    while True:
        try:
            data, _ = sock.recvfrom(65535)
            incoming.put(json.loads(data.decode()))
        except socket.timeout:
            continue
        except Exception:
            break


threading.Thread(target=receive_messages, daemon=True).start()


def send_msg(msg):
    try:
        sock.sendto(json.dumps(msg).encode(), (SERVER_IP, PORT))
    except Exception:
        pass


# --------------------------------------------------
# GLOBAL STATE
# --------------------------------------------------

paused = False

pause_menu = None
settings_menu = None
settings_texts = {}

crosshair = None
fps_text = None

my_id = None
health = 100
cooldown = 0

last_join = 0
last_state = 0

remote_entities = {}

ground = None
map_entities = []
map_received = False
arena_half = 80.0
last_map_request = 0.0

display_apply_pending = False
display_apply_dirty = False


# --------------------------------------------------
# SERVER MAP BUILDING
# --------------------------------------------------

def clear_map():
    global map_entities

    for e in map_entities:
        try:
            destroy(e)
        except Exception:
            pass

    map_entities = []


def get_map_texture(tex_id):
    if tex_id == 0:
        return get_texture("ground.png") or "white_cube"

    if tex_id == 1:
        return get_texture("brick.png") or "white_cube"

    if tex_id == 2:
        return get_texture("metal.png") or "white_cube"

    return "white_cube"


def build_map_from_server(data):
    global map_received, arena_half, ground

    clear_map()

    map_received = True
    arena_half = float(data.get("arena_half", 80.0))

    if ground is not None:
        try:
            ground.scale = Vec3(arena_half * 3.5, 1, arena_half * 3.5)
            ground.position = Vec3(0, -0.5, 0)
            ground.texture_scale = (arena_half / 2, arena_half / 2)
        except Exception:
            pass

    for b in data.get("blocks", []):
        try:
            tex_id = int(b.get("t", 1))
            texture = get_map_texture(tex_id)

            c = b.get("c")

            if c is not None:
                block_color = color.rgb(int(c[0]), int(c[1]), int(c[2]))
            else:
                block_color = color.white

            e = Entity(
                model="cube",
                scale=(
                    float(b.get("w", 2)),
                    float(b.get("h", 2)),
                    float(b.get("d", 2)),
                ),
                position=(
                    float(b.get("x", 0)),
                    float(b.get("y", 0)),
                    float(b.get("z", 0)),
                ),
                texture=texture,
                color=block_color,
            )

            if tex_id in (0, 1, 2):
                try:
                    e.texture_scale = (2, 2)
                except Exception:
                    pass

            map_entities.append(e)

        except Exception as e:
            print("Could not build map block:", e)

    print("Built server map with", len(map_entities), "blocks")


# --------------------------------------------------
# MOUSE / MENU HELPERS
# --------------------------------------------------

def set_mouse_ui_mode():
    try:
        mouse.locked = False
        mouse.visible = True
    except Exception as e:
        print("Could not set UI mouse mode:", e)


def set_mouse_game_mode():
    try:
        mouse.locked = True
        mouse.visible = False
    except Exception as e:
        print("Could not set game mouse mode:", e)


def set_menu_enabled(menu, value):
    if menu is None:
        return

    try:
        menu.enabled = value
    except Exception:
        pass

    try:
        for child in menu.children:
            child.enabled = value
    except Exception:
        pass


def update_mouse_after_window_change():
    try:
        mouse.velocity = Vec2(0, 0)
    except Exception:
        pass

    try:
        if paused:
            set_mouse_ui_mode()
        else:
            set_mouse_game_mode()
    except Exception:
        pass


# --------------------------------------------------
# SETTINGS UI REFRESH STUB
# --------------------------------------------------

def refresh_settings_ui():
    pass


# --------------------------------------------------
# SETTINGS APPLY FUNCTIONS
# --------------------------------------------------

def apply_general_settings():
    try:
        camera.fov = settings["fov"]
    except Exception as e:
        print("Could not apply FOV:", e)

    try:
        camera.clip_plane_far = DRAW_DISTANCES[settings["draw_index"]]
    except Exception as e:
        print("Could not apply draw distance:", e)

    if crosshair is not None:
        try:
            crosshair.scale = 0.003 * CROSSHAIR_SIZES[settings["crosshair_index"]]
        except Exception:
            pass

    if fps_text is not None:
        try:
            fps_text.enabled = settings["show_fps"]
        except Exception:
            pass


def apply_resolution():
    w, h = RESOLUTIONS[settings["resolution_index"]]

    print(f"Trying to change resolution to {w}x{h}")

    try:
        window.size = Vec2(w, h)
        print("Resolution changed with window.size Vec2")
        return
    except Exception as e:
        print("window.size Vec2 failed:", e)

    try:
        window.size = (w, h)
        print("Resolution changed with window.size tuple")
        return
    except Exception as e:
        print("window.size tuple failed:", e)

    try:
        window.resolution = Vec2(w, h)
        print("Resolution changed with window.resolution Vec2")
        return
    except Exception as e:
        print("window.resolution Vec2 failed:", e)

    try:
        window.resolution = (w, h)
        print("Resolution changed with window.resolution tuple")
        return
    except Exception as e:
        print("window.resolution tuple failed:", e)

    print("Could not change resolution.")


def _display_step_1():
    try:
        window.fullscreen = False
    except Exception as e:
        print("Could not temporarily disable fullscreen:", e)

    apply_resolution()


def _display_step_2():
    global display_apply_pending, display_apply_dirty

    try:
        window.fullscreen = settings["fullscreen"]
    except Exception as e:
        print("Could not apply fullscreen:", e)

    try:
        window.center()
    except Exception:
        pass

    update_mouse_after_window_change()

    display_apply_pending = False

    if display_apply_dirty:
        display_apply_dirty = False
        apply_display_settings()


def apply_display_settings():
    global display_apply_pending, display_apply_dirty

    apply_general_settings()

    if display_apply_pending:
        display_apply_dirty = True
        return

    display_apply_pending = True

    try:
        invoke(_display_step_1, delay=0.05)
        invoke(_display_step_2, delay=0.30)
    except Exception:
        _display_step_1()
        _display_step_2()


# --------------------------------------------------
# SETTINGS CHANGE FUNCTIONS
# --------------------------------------------------

def change_fov(amount):
    settings["fov"] = max(60, min(120, settings["fov"] + amount))
    apply_general_settings()
    refresh_settings_ui()
    save_settings()


def change_sensitivity(amount):
    settings["sensitivity"] = max(50, min(800, settings["sensitivity"] + amount))
    apply_general_settings()
    refresh_settings_ui()
    save_settings()


def change_resolution(amount):
    settings["resolution_index"] = (settings["resolution_index"] + amount) % len(RESOLUTIONS)
    refresh_settings_ui()
    save_settings()
    apply_display_settings()


def toggle_fullscreen():
    settings["fullscreen"] = not settings["fullscreen"]
    refresh_settings_ui()
    save_settings()
    apply_display_settings()


def change_draw_distance(amount):
    settings["draw_index"] = (settings["draw_index"] + amount) % len(DRAW_DISTANCES)
    apply_general_settings()
    refresh_settings_ui()
    save_settings()


def change_crosshair_size(amount):
    settings["crosshair_index"] = (settings["crosshair_index"] + amount) % len(CROSSHAIR_SIZES)
    apply_general_settings()
    refresh_settings_ui()
    save_settings()


def toggle_show_fps():
    settings["show_fps"] = not settings["show_fps"]
    apply_general_settings()
    refresh_settings_ui()
    save_settings()


def reset_settings():
    settings.update(DEFAULT_SETTINGS.copy())
    refresh_settings_ui()
    save_settings()
    apply_display_settings()


# --------------------------------------------------
# PAUSE MENU FUNCTIONS
# --------------------------------------------------

def open_pause():
    global paused

    paused = True

    set_mouse_ui_mode()
    set_menu_enabled(pause_menu, True)
    set_menu_enabled(settings_menu, False)


def resume():
    global paused

    paused = False

    set_mouse_game_mode()
    set_menu_enabled(pause_menu, False)
    set_menu_enabled(settings_menu, False)

    try:
        invoke(update_mouse_after_window_change, delay=0.10)
    except Exception:
        update_mouse_after_window_change()


def open_settings_menu():
    set_mouse_ui_mode()
    set_menu_enabled(pause_menu, False)
    set_menu_enabled(settings_menu, True)
    refresh_settings_ui()


def open_pause_from_settings():
    set_mouse_ui_mode()
    set_menu_enabled(settings_menu, False)
    set_menu_enabled(pause_menu, True)


def quit_game():
    save_settings()

    try:
        application.quit()
    except Exception:
        pass


# --------------------------------------------------
# URSINA APP
# --------------------------------------------------

app = Ursina()

try:
    application.asset_folder = SCRIPT_DIR
    print("Ursina asset folder set to:", application.asset_folder)
except Exception as e:
    print("Could not set asset folder:", e)

window.title = "Brick Sniper 3D"
window.exit_button.visible = False
window.color = color.rgb(140, 190, 255)

camera.position = (0, EYE_HEIGHT, 0)
camera.rotation = (0, 0, 0)


# --------------------------------------------------
# WORLD
# --------------------------------------------------

Sky()

ground_tex = get_texture("ground.png")

ground = Entity(
    model="cube",
    scale=(300, 1, 300),
    position=(0, -0.5, 0),
    texture=ground_tex if ground_tex else "white_cube",
    color=color.white if ground_tex else color.rgb(110, 180, 110),
)

if ground_tex:
    try:
        ground.texture_scale = (80, 80)
    except Exception:
        pass

# No random client-side buildings.
# The server sends the real map.


# --------------------------------------------------
# FIRST PERSON GUN VIEWMODEL
# --------------------------------------------------

gun = Entity(
    parent=camera,
    model="cube",
    color=color.rgb(70, 70, 80),
    scale=(0.12, 0.12, 1.0),
    position=(0.35, -0.3, 0.9),
)

Entity(
    parent=gun,
    model="cube",
    color=color.rgb(35, 35, 40),
    scale=(0.06, 0.1, 0.35),
    position=(0, 0.08, -0.35),
)

crosshair = Entity(
    parent=camera.ui,
    model="quad",
    scale=0.003,
    color=color.white,
)

hud = Text(
    text="Connecting...",
    position=(-0.85, 0.45),
    scale=1,
)

fps_text = Text(
    text="",
    position=(0.40, 0.45),
    scale=1,
    enabled=False,
)

apply_display_settings()


# --------------------------------------------------
# BRICK RIG STYLE REMOTE PLAYER
# --------------------------------------------------

def create_brick_rig(pid):
    root = Entity()

    palette = [
        color.red,
        color.orange,
        color.cyan,
        color.magenta,
        color.lime,
        color.yellow,
    ]

    body_color = palette[pid % len(palette)]

    body_tex = get_texture("brick.png")
    metal_tex = get_texture("metal.png")

    Entity(
        parent=root,
        model="cube",
        scale=(2.4, 0.9, 3.6),
        position=(0, 1.0, 0),
        texture=body_tex if body_tex else "white_cube",
        color=body_color,
    )

    Entity(
        parent=root,
        model="cube",
        scale=(1.7, 0.8, 1.7),
        position=(0, 1.8, 0.2),
        texture=metal_tex if metal_tex else "white_cube",
        color=color.rgb(230, 230, 230),
    )

    Entity(
        parent=root,
        model="cube",
        scale=(0.25, 0.25, 2.6),
        position=(0, 2.15, -0.8),
        texture=metal_tex if metal_tex else "white_cube",
        color=color.rgb(35, 35, 40),
    )

    wheel_positions = [
        (-1.2, 1.4),
        (1.2, 1.4),
        (-1.2, -1.4),
        (1.2, -1.4),
    ]

    for wx, wz in wheel_positions:
        Entity(
            parent=root,
            model="cube",
            scale=(0.6, 0.8, 0.8),
            position=(wx, 0.5, wz),
            texture=metal_tex if metal_tex else "white_cube",
            color=color.rgb(25, 25, 25),
        )

    return root


# --------------------------------------------------
# TRACERS
# --------------------------------------------------

def make_tracer(origin, direction, length=80.0):
    direction = direction.normalized()

    try:
        length = float(length)
    except Exception:
        length = 80.0

    length = max(1.0, min(length, 200.0))

    tracer = Entity(
        model="cube",
        scale=(0.06, 0.06, length),
        position=origin + direction * (length / 2),
        color=color.rgba(255, 80, 80, 200),
    )

    tracer.look_at(origin + direction * length)
    destroy(tracer, delay=0.08)


# --------------------------------------------------
# SHOOTING
# --------------------------------------------------

def shoot():
    global cooldown

    if my_id is None:
        return

    if cooldown > 0:
        return

    if paused:
        return

    if not mouse.locked:
        return

    origin = camera.position
    direction = camera.forward.normalized()

    send_msg(
        {
            "type": "shoot",
            "id": my_id,
            "x": origin.x,
            "y": origin.y - EYE_HEIGHT,
            "z": origin.z,
            "yaw": camera.rotation_y,
            "dir": [direction.x, direction.y, direction.z],
        }
    )

    make_tracer(origin, direction, 100.0)

    cooldown = SHOOT_COOLDOWN


# --------------------------------------------------
# NETWORK PROCESSING
# --------------------------------------------------

def process_network():
    global my_id, health, map_received

    try:
        while True:
            msg = incoming.get_nowait()
            mtype = msg.get("type")

            if mtype == "welcome":
                my_id = msg.get("id")

                camera.position = Vec3(
                    msg.get("x", 0),
                    msg.get("y", 0) + EYE_HEIGHT,
                    msg.get("z", 0),
                )

                send_msg({"type": "get_map"})

            elif mtype == "map":
                build_map_from_server(msg)

            elif mtype == "state":
                if my_id is None:
                    continue

                seen = []

                for p in msg.get("players", []):
                    pid = p.get("id")

                    if pid == my_id:
                        health = p.get("health", health)
                        continue

                    seen.append(pid)

                    if pid not in remote_entities:
                        remote_entities[pid] = create_brick_rig(pid)

                    e = remote_entities[pid]

                    e.position = Vec3(
                        p.get("x", 0),
                        p.get("y", 0),
                        p.get("z", 0),
                    )

                    e.rotation_y = p.get("yaw", 0)

                for pid in list(remote_entities.keys()):
                    if pid not in seen:
                        destroy(remote_entities[pid])
                        del remote_entities[pid]

            elif mtype == "shot":
                if my_id is not None and msg.get("shooter") != my_id:
                    origin = Vec3(
                        msg.get("x", 0),
                        msg.get("y", 0) + EYE_HEIGHT,
                        msg.get("z", 0),
                    )

                    d = msg.get("dir", [0, 0, 1])
                    direction = Vec3(d[0], d[1], d[2]).normalized()

                    shot_length = msg.get("dist", 80)

                    make_tracer(origin, direction, shot_length)

                if (
                    my_id is not None
                    and msg.get("kill")
                    and msg.get("hit") == my_id
                ):
                    camera.position = Vec3(
                        msg.get("respawn_x", 0),
                        msg.get("respawn_y", 0) + EYE_HEIGHT,
                        msg.get("respawn_z", 0),
                    )

                    health = 100

    except queue.Empty:
        pass


# --------------------------------------------------
# PAUSE MENU UI
# --------------------------------------------------

pause_menu = Entity(parent=camera.ui)

pause_bg = Entity(
    parent=pause_menu,
    model="quad",
    scale=(100, 100),
    color=color.rgba(0, 0, 0, 150),
    z=10,
)

try:
    pause_bg.ignore = True
    pause_bg.collider = None
except Exception:
    pass

Text(
    text="Paused",
    parent=pause_menu,
    position=(0, 0.25),
    scale=2,
    origin=(0, 0),
    z=-10,
)

Button(
    text="Resume",
    parent=pause_menu,
    scale=(0.25, 0.08),
    position=(0, 0.10),
    z=-10,
    on_click=resume,
)

Button(
    text="Settings",
    parent=pause_menu,
    scale=(0.25, 0.08),
    position=(0, 0.0),
    z=-10,
    on_click=open_settings_menu,
)

Button(
    text="Quit",
    parent=pause_menu,
    scale=(0.25, 0.08),
    position=(0, -0.10),
    z=-10,
    on_click=quit_game,
)

set_menu_enabled(pause_menu, False)


# --------------------------------------------------
# SETTINGS MENU UI
# --------------------------------------------------

settings_menu = Entity(parent=camera.ui)

settings_bg = Entity(
    parent=settings_menu,
    model="quad",
    scale=(100, 100),
    color=color.rgba(0, 0, 0, 170),
    z=10,
)

try:
    settings_bg.ignore = True
    settings_bg.collider = None
except Exception:
    pass

Text(
    text="Settings",
    parent=settings_menu,
    position=(0, 0.35),
    scale=2,
    origin=(0, 0),
    z=-10,
)


def make_label(text_value, y):
    return Text(
        text=text_value,
        parent=settings_menu,
        position=(-0.35, y),
        scale=1,
        origin=(0, 0),
        z=-10,
    )


def make_value_text(y):
    return Text(
        text="",
        parent=settings_menu,
        position=(0.12, y),
        scale=1,
        origin=(0, 0),
        z=-10,
    )


def make_minus_plus(y, minus_func, plus_func):
    Button(
        text="-",
        parent=settings_menu,
        scale=(0.05, 0.06),
        position=(-0.02, y),
        z=-10,
        on_click=minus_func,
    )

    Button(
        text="+",
        parent=settings_menu,
        scale=(0.05, 0.06),
        position=(0.30, y),
        z=-10,
        on_click=plus_func,
    )


make_label("FOV", 0.22)
settings_texts["fov"] = make_value_text(0.22)
make_minus_plus(
    0.22,
    lambda: change_fov(-5),
    lambda: change_fov(5),
)

make_label("Sensitivity", 0.14)
settings_texts["sensitivity"] = make_value_text(0.14)
make_minus_plus(
    0.14,
    lambda: change_sensitivity(-25),
    lambda: change_sensitivity(25),
)

make_label("Resolution", 0.06)
settings_texts["resolution"] = make_value_text(0.06)
make_minus_plus(
    0.06,
    lambda: change_resolution(-1),
    lambda: change_resolution(1),
)

make_label("Fullscreen", -0.02)
settings_texts["fullscreen"] = Button(
    text="Off",
    parent=settings_menu,
    scale=(0.25, 0.06),
    position=(0.12, -0.02),
    z=-10,
    on_click=toggle_fullscreen,
)

make_label("Draw Distance", -0.10)
settings_texts["draw_distance"] = make_value_text(-0.10)
make_minus_plus(
    -0.10,
    lambda: change_draw_distance(-1),
    lambda: change_draw_distance(1),
)

make_label("Crosshair Size", -0.18)
settings_texts["crosshair_size"] = make_value_text(-0.18)
make_minus_plus(
    -0.18,
    lambda: change_crosshair_size(-1),
    lambda: change_crosshair_size(1),
)

make_label("Show FPS", -0.26)
settings_texts["show_fps"] = Button(
    text="Off",
    parent=settings_menu,
    scale=(0.25, 0.06),
    position=(0.12, -0.26),
    z=-10,
    on_click=toggle_show_fps,
)

Button(
    text="Reset Settings",
    parent=settings_menu,
    scale=(0.25, 0.08),
    position=(0, -0.34),
    z=-10,
    on_click=reset_settings,
)

Button(
    text="Back",
    parent=settings_menu,
    scale=(0.25, 0.08),
    position=(0, -0.42),
    z=-10,
    on_click=open_pause_from_settings,
)

set_menu_enabled(settings_menu, False)


# --------------------------------------------------
# REAL SETTINGS UI REFRESH
# --------------------------------------------------

def refresh_settings_ui():
    if not settings_texts:
        return

    w, h = RESOLUTIONS[settings["resolution_index"]]

    settings_texts["fov"].text = str(settings["fov"])
    settings_texts["sensitivity"].text = str(settings["sensitivity"])
    settings_texts["resolution"].text = f"{w}x{h}"
    settings_texts["fullscreen"].text = "On" if settings["fullscreen"] else "Off"
    settings_texts["draw_distance"].text = str(DRAW_DISTANCES[settings["draw_index"]])
    settings_texts["crosshair_size"].text = str(CROSSHAIR_SIZES[settings["crosshair_index"]])
    settings_texts["show_fps"].text = "On" if settings["show_fps"] else "Off"


refresh_settings_ui()


# --------------------------------------------------
# INPUT
# --------------------------------------------------

def input(key):
    if key == "escape":
        if paused:
            if settings_menu is not None and settings_menu.enabled:
                open_pause_from_settings()
            else:
                resume()
        else:
            open_pause()

        return

    if key == "left mouse":
        if not paused:
            shoot()

    if key == "space":
        if not paused:
            try:
                mouse.locked = True
            except Exception:
                pass


# --------------------------------------------------
# GAME LOOP
# --------------------------------------------------

def update():
    global last_join, last_state, cooldown, health
    global last_map_request, arena_half

    dt = time.dt

    process_network()

    if my_id is None and pytime.time() - last_join > 0.5:
        send_msg({"type": "join"})
        last_join = pytime.time()

    if my_id is not None and not map_received and pytime.time() - last_map_request > 1.0:
        send_msg({"type": "get_map"})
        last_map_request = pytime.time()

    if my_id is not None and pytime.time() - last_state > 1 / 30:
        send_msg(
            {
                "type": "state",
                "id": my_id,
                "x": camera.x,
                "y": camera.y - EYE_HEIGHT,
                "z": camera.z,
                "yaw": camera.rotation_y,
            }
        )

        last_state = pytime.time()

    if fps_text is not None and settings["show_fps"]:
        fps_text.text = f"FPS: {int(1 / dt) if dt > 0 else 0}"

    if paused:
        hud.text = "Paused"
        return

    if mouse.locked:
        camera.rotation_y += mouse.velocity[0] * settings["sensitivity"] * dt
        camera.rotation_x -= mouse.velocity[1] * settings["sensitivity"] * dt
        camera.rotation_x = clamp(camera.rotation_x, -80, 80)

    move = Vec3(0, 0, 0)

    if held_keys["w"]:
        move += camera.forward

    if held_keys["s"]:
        move -= camera.forward

    if held_keys["a"]:
        move -= camera.right

    if held_keys["d"]:
        move += camera.right

    move.y = 0

    if move.length() > 0:
        move = move.normalized() * SPEED * dt
        camera.position += move

    camera.y = EYE_HEIGHT

    limit = max(20.0, arena_half - 2.0)

    camera.x = clamp(camera.x, -limit, limit)
    camera.z = clamp(camera.z, -limit, limit)

    cooldown = max(0, cooldown - dt)

    hud.text = (
        f"Server: {SERVER_IP} | "
        f"ID: {my_id if my_id is not None else 'joining...'} | "
        f"HP: {health} | "
        f"Map: {'Yes' if map_received else 'Loading...'}"
    )


set_mouse_game_mode()

app.run()

if my_id is not None:
    send_msg({"type": "quit", "id": my_id})