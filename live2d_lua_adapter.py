import io
import json
import os
import random
from pathlib import Path

from lupa.luajit21 import LuaRuntime
from PIL import Image

from process_utils import app_base_dir
from zst_model_archive import is_virtual_path, load_virtual_bytes


BASE_DIR = Path(app_base_dir())
LIVE2D_LUA_DIR = BASE_DIR / "third_party" / "Live2D-v2-Lua"
MODELS_DIR = BASE_DIR / "models"


def _normalize_lua_path(path) -> str:
    if isinstance(path, bytes):
        path = path.decode("utf-8")
    return str(path).replace("\\", "/")


def _load_model_bytes(path: str) -> bytes:
    path = _normalize_lua_path(path)
    if is_virtual_path(path):
        try:
            return load_virtual_bytes(path)
        except KeyError:
            fixed = _fix_mtn_path(path)
            if fixed:
                return Path(fixed).read_bytes()
            raise

    fs_path = Path(path)
    if not fs_path.exists():
        fixed = _fix_mtn_path(path)
        if fixed:
            fs_path = Path(fixed)
    return fs_path.read_bytes()


def _load_model_json(path: str) -> dict:
    return json.loads(_load_model_bytes(path).decode("utf-8"))


def _texture_rgba(path: str) -> tuple[int, int, bytes]:
    source = io.BytesIO(load_virtual_bytes(path)) if is_virtual_path(path) else Path(path)
    with Image.open(source) as image:
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        else:
            image = image.copy()
        return image.width, image.height, image.tobytes()


def _fix_mtn_path(path: str) -> str:
    basename = os.path.basename(path)
    mtn_emp_dir = MODELS_DIR / "_mtn_emp"
    if not basename or not mtn_emp_dir.is_dir():
        return ""
    for root, _dirs, files in os.walk(mtn_emp_dir):
        if basename in files:
            return str(Path(root) / basename)
    return ""


class _ModelSetting:
    def __init__(self, data: dict):
        self.json = data

    def getMotionNames(self) -> list[str]:
        motions = self.json.get("motions") or {}
        if not isinstance(motions, dict):
            return []
        return [str(name) for name in motions if name]

    def getMotionNum(self, name: str) -> int:
        group = self._motion_group(name)
        return len(group)

    def resolveMotion(self, name: str, no: int = 0) -> tuple[str, int] | None:
        group = self._motion_group(name)
        if group:
            return name, max(0, min(int(no), len(group) - 1))

        target = Path(str(name).replace("\\", "/")).name.lower()
        target_stem = Path(target).stem
        motions = self.json.get("motions") or {}
        if not isinstance(motions, dict):
            return None
        for group_name, group in motions.items():
            if not isinstance(group, list):
                continue
            for idx, item in enumerate(group):
                if not isinstance(item, dict):
                    continue
                motion_file = Path(str(item.get("file", "")).replace("\\", "/")).name.lower()
                if motion_file == target or Path(motion_file).stem == target_stem:
                    return str(group_name), idx
        return None

    def _motion_group(self, name: str) -> list:
        motions = self.json.get("motions") or {}
        if not isinstance(motions, dict):
            return []
        group = motions.get(name) or []
        return group if isinstance(group, list) else []

    def getHitAreaNum(self) -> int:
        hit_areas = self.json.get("hit_areas") or []
        return len(hit_areas) if isinstance(hit_areas, list) else 0


class MotionPriority:
    NONE = 0
    IDLE = 1
    NORMAL = 2
    FORCE = 3


class _MatrixManager:
    def __init__(self):
        self._width = 1.0
        self._height = 1.0

    def on_resize(self, width: float, height: float):
        self._width = max(float(width), 1.0)
        self._height = max(float(height), 1.0)

    def screenToScene(self, x: float, y: float):
        if self._width > self._height:
            scale = 2.0 * (self._width / self._height) / self._width
        else:
            scale = 2.0 / self._height
        return (float(x) - self._width / 2.0) * scale, -(float(y) - self._height / 2.0) * scale


class LuaLive2DModule:
    def __init__(self):
        self._lua = None
        self._embed = None
        self._initialized = False
        self._load_model = None
        self._resize = None
        self._draw = None
        self._drag = None
        self._hit_test = None
        self.MotionPriority = MotionPriority

    def init(self):
        return True

    def glInit(self):
        self._ensure_runtime()

    def clearBuffer(self):
        return True

    def dispose(self):
        if self._embed is not None:
            try:
                self._embed.dispose()
            except Exception:
                pass
        self._lua = None
        self._embed = None
        self._initialized = False

    def LAppModel(self):
        return LuaLAppModel(self)

    def _ensure_runtime(self):
        if self._initialized:
            return
        lua = LuaRuntime(unpack_returned_tuples=True, encoding=None)
        lua.execute(b'assert(require("ffi"), "lupa must be built with LuaJIT FFI")')
        lua_dir = LIVE2D_LUA_DIR.as_posix().encode("utf-8")
        lua.execute(
            b"local root = ...; "
            b"package.path = package.path .. ';' .. root .. '/?.ljbc;' .. root .. '/?/init.ljbc;' .. root .. '/?.lua;' .. root .. '/?/init.lua'",
            lua_dir,
        )
        self._embed = lua.execute(b'return require("live2d_embed")')
        self._embed.init()
        self._load_model = lua.eval(
            b"function(renderer, path, w, h, opts) return renderer:load_model(path, w, h, opts) end"
        )
        self._resize = lua.eval(b"function(renderer, w, h) return renderer:resize(w, h) end")
        self._draw = lua.eval(b"function(renderer, opts) return renderer:draw(opts) end")
        self._drag = lua.eval(b"function(renderer, x, y) return renderer:drag(x, y) end")
        self._hit_test = lua.eval(b"function(renderer, x, y) return renderer:hit_test(x, y) end")
        self._start_motion = lua.eval(
            b"function(renderer, name, no, priority) return renderer:start_motion(name, no, priority) end"
        )
        self._clear_motions = lua.eval(b"function(renderer) return renderer:clear_motions() end")
        self._is_motion_finished = lua.eval(
            b"function(renderer) "
            b"local model = renderer:get_model(); "
            b"return model == nil or model.mainMotionManager:isFinished(); "
            b"end"
        )
        self._set_expression = lua.eval(
            b"function(renderer, name) return renderer:set_expression(name) end"
        )
        self._reset_expression = lua.eval(b"function(renderer) return renderer:reset_expression() end")
        self._lua = lua
        self._initialized = True

    def _new_renderer(self, width: int, height: int):
        self._ensure_runtime()
        return self._embed.new(width, height)

    def _new_options(self, model_path: str):
        self._ensure_runtime()
        lua = self._lua

        def resource_loader(path):
            return _load_model_bytes(_normalize_lua_path(path))

        def texture_loader(no, path):
            w, h, rgba = _texture_rgba(_normalize_lua_path(path))
            entry = lua.table()
            entry[b"width"] = w
            entry[b"height"] = h
            entry[b"data"] = rgba
            entry[b"mipmap"] = False
            return entry

        resources = lua.table()
        resources[b"__loader"] = resource_loader
        resources[_normalize_lua_path(model_path).encode("utf-8")] = _load_model_bytes(model_path)

        textures = lua.table()
        textures[b"__loader"] = texture_loader

        opts = lua.table()
        opts[b"resource_streams"] = resources
        opts[b"texture_streams"] = textures
        opts[b"center"] = False
        opts[b"defer_expressions"] = True
        return opts


class LuaLAppModel:
    def __init__(self, module: LuaLive2DModule):
        self._module = module
        self._renderer = None
        self._width = 1
        self._height = 1
        self.modelSetting = None
        self.matrixManager = _MatrixManager()
        self.expressions = {}

    def LoadModelJson(self, model_json_path: str, disable_precision=False):
        del disable_precision
        model_json = _load_model_json(model_json_path)
        self.modelSetting = _ModelSetting(model_json)
        self.expressions = self._read_expression_names(model_json)
        self._renderer = self._module._new_renderer(self._width, self._height)
        opts = self._module._new_options(model_json_path)
        self._module._load_model(
            self._renderer,
            _normalize_lua_path(model_json_path).encode("utf-8"),
            self._width,
            self._height,
            opts,
        )

    def Resize(self, width: int, height: int):
        self._width = max(int(width), 1)
        self._height = max(int(height), 1)
        self.matrixManager.on_resize(self._width, self._height)
        if self._renderer is not None:
            self._module._resize(self._renderer, self._width, self._height)

    def Update(self):
        return True

    def Draw(self):
        if self._renderer is None:
            return
        opts = self._module._lua.table()
        opts[b"clear"] = False
        self._module._draw(self._renderer, opts)

    def Drag(self, x: float, y: float):
        if self._renderer is not None:
            self._module._drag(self._renderer, float(x), float(y))

    def HitTest(self, _area_name: str, x: float, y: float):
        if self._renderer is None:
            return None
        hits = self._module._hit_test(self._renderer, float(x), float(y))
        try:
            return "hit" if len(hits) > 0 else None
        except Exception:
            return None

    def StartMotion(self, name: str, no: int = 0, priority=MotionPriority.FORCE, **_kwargs):
        if self._renderer is None:
            return
        resolved = self.modelSetting.resolveMotion(str(name), int(no)) if self.modelSetting else None
        if resolved is None:
            return
        group_name, motion_no = resolved
        self._module._start_motion(
            self._renderer,
            group_name.encode("utf-8"),
            int(motion_no),
            int(priority),
        )

    def StartRandomMotion(self, name: str | None = None, priority=MotionPriority.IDLE, **_kwargs):
        if self.modelSetting is None:
            return
        if not name:
            names = self.modelSetting.getMotionNames()
            if not names:
                return
            name = random.choice(names)
        count = self.modelSetting.getMotionNum(name)
        if count <= 0:
            return
        self.StartMotion(name, random.randrange(count), priority)

    def ClearMotions(self):
        if self._renderer is not None:
            self._module._clear_motions(self._renderer)

    def IsMotionFinished(self) -> bool:
        if self._renderer is None:
            return True
        return bool(self._module._is_motion_finished(self._renderer))

    def SetExpression(self, name: str):
        if self._renderer is not None:
            self._module._set_expression(self._renderer, str(name).encode("utf-8"))

    def ResetExpression(self):
        if self._renderer is not None:
            self._module._reset_expression(self._renderer)

    @staticmethod
    def _read_expression_names(model_json: dict) -> dict[str, None]:
        expressions = model_json.get("expressions") or []
        if not isinstance(expressions, list):
            return {}
        names = {}
        for item in expressions:
            if isinstance(item, dict) and item.get("name"):
                names[str(item["name"])] = None
        return names


live2d = LuaLive2DModule()
