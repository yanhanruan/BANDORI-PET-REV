import json
from pathlib import Path
from process_utils import app_base_dir

BASE_DIR = app_base_dir()
MODELS_DIR = BASE_DIR / "models"
OUTFIT_JSON = BASE_DIR / "outfit.json"
BAND_JSON = BASE_DIR / "band.json"
CHARACTERS_DIR = BASE_DIR / "characters"


class ModelManager:
    def __init__(self):
        self._characters: dict[str, dict] = {}
        self._costume_names: dict[str, dict[str, str]] = {}
        self._bands: list[dict] = []
        self._advanced_roleplay_cache: dict[str, bool] | None = None
        self._scan()
        self._parse_outfit_json()
        self._parse_band_json()

    def _scan_advanced_roleplay_support(self) -> dict[str, bool]:
        support = {character: False for character in self.characters}
        if not CHARACTERS_DIR.exists():
            return support

        display_to_key = {
            self.get_display_name(character): character
            for character in self.characters
        }
        for entry in sorted(CHARACTERS_DIR.iterdir()):
            if not entry.is_dir():
                continue
            character = display_to_key.get(entry.name)
            if not character:
                continue
            support[character] = any(
                path.is_file() and path.suffix.lower() == ".md"
                for path in entry.iterdir()
            )
        return support

    def _scan(self):
        for entry in sorted(MODELS_DIR.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_"):
                continue
            char_name = entry.name
            costumes = []
            for costume_dir in sorted(entry.iterdir()):
                if not costume_dir.is_dir():
                    continue
                model_json = costume_dir / "model.json"
                if model_json.exists():
                    costumes.append({
                        "id": costume_dir.name,
                        "path": str(model_json.resolve()),
                    })
            if costumes:
                self._characters[char_name] = {
                    "costumes": costumes,
                }

    def _parse_outfit_json(self):
        if not OUTFIT_JSON.exists():
            return
        data = json.loads(OUTFIT_JSON.read_text(encoding="utf-8"))
        chars = data.get("characters", {})
        for key, info in chars.items():
            self._characters.setdefault(key, {})
            self._characters[key]["display"] = info.get("display", key)
            costumes = info.get("costumes", {})
            if costumes:
                self._costume_names.setdefault(key, {})
                self._costume_names[key].update(costumes)

    def _parse_band_json(self):
        if BAND_JSON.exists():
            data = json.loads(BAND_JSON.read_text(encoding="utf-8"))
            configured_bands = data.get("bands", [])
        else:
            configured_bands = []

        seen = set()
        for band in configured_bands:
            characters = [
                c for c in band.get("characters", [])
                if c in self._characters and self.get_costumes(c)
            ]
            if not characters:
                continue
            seen.update(characters)
            self._bands.append({
                "id": band.get("id", ""),
                "display": band.get("display", band.get("id", "")),
                "logo": str((BASE_DIR / band.get("logo", "")).resolve()) if band.get("logo") else "",
                "characters": characters,
            })

        ungrouped = [
            c for c in self.characters
            if c not in seen and self.get_costumes(c)
        ]
        if ungrouped:
            self._bands.append({
                "id": "others",
                "display": "其他角色",
                "characters": ungrouped,
            })

    @property
    def characters(self) -> list[str]:
        return list(self._characters.keys())

    @property
    def bands(self) -> list[dict]:
        return self._bands

    def get_band_display_name(self, band_id: str) -> str:
        for band in self._bands:
            if band["id"] == band_id:
                return band["display"]
        return band_id

    def get_band_characters(self, band_id: str) -> list[str]:
        for band in self._bands:
            if band["id"] == band_id:
                return band["characters"]
        return []

    def get_character_band(self, character: str) -> str:
        for band in self._bands:
            if character in band["characters"]:
                return band["id"]
        return ""

    def has_advanced_roleplay(self, character: str) -> bool:
        if self._advanced_roleplay_cache is None:
            self._advanced_roleplay_cache = self._scan_advanced_roleplay_support()
        return self._advanced_roleplay_cache.get(character, False)

    def get_band_advanced_roleplay_status(self, band_id: str) -> str:
        characters = self.get_band_characters(band_id)
        if not characters:
            return "red"

        supported_count = sum(
            1 for character in characters
            if self.has_advanced_roleplay(character)
        )
        if supported_count == len(characters):
            return "green"
        if supported_count > 0:
            return "yellow"
        return "red"

    def get_display_name(self, character: str) -> str:
        return self._characters.get(character, {}).get("display", character.title())

    @staticmethod
    def get_character_image_path(character: str) -> str:
        char_dir = MODELS_DIR / character
        for ext in ("png", "jpg", "webp"):
            path = char_dir / f"character.{ext}"
            if path.exists():
                return str(path.resolve())
        return ""

    def get_costumes(self, character: str) -> list[dict]:
        return self._characters.get(character, {}).get("costumes", [])

    def get_costume_display_name(self, character: str, costume_id: str) -> str:
        return self._costume_names.get(character, {}).get(costume_id, costume_id)

    def get_default_costume(self, character: str) -> str:
        costumes = self.get_costumes(character)
        if not costumes:
            return ""
        preferred = ["live_default", "casual", "school_winter", "school_summer"]
        costume_ids = [c["id"] for c in costumes]
        for pref in preferred:
            if pref in costume_ids:
                return pref
        return costumes[0]["id"]

    @staticmethod
    def get_model_json_path(character: str, costume: str) -> str:
        path = MODELS_DIR / character / costume / "model.json"
        if path.exists():
            return str(path.resolve())
        return ""

    def get_motion_names(self, character: str, costume: str) -> list[str]:
        path = self.get_model_json_path(character, costume)
        if not path:
            return []
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        motions = data.get("motions", {})
        if not isinstance(motions, dict):
            return []
        return sorted(str(name) for name in motions if name)
