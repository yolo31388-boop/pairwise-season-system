"""
游戏内季节系统与环境变化系统 - 核心模块

功能：
- update_season():      季节更新（固定周期自动切换 + 平滑过渡渐变）
- environment_change(): 环境变化（天空/地形/植被/水体 + 粒子 + 音效）
- weather_interaction(): 天气联动（地面积雪 + 移动物理 + 视觉效果）
- creature_behavior():  生物行为变化（冬眠 / 迁徙 / 觅食）
- season_events():      季节事件（节日活动 + 奖励 + 倒计时）
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math
import time


SEASONS: Tuple[str, ...] = ("spring", "summer", "autumn", "winter")

# 每个季节的环境档案：天空、地形、植被、水体、粒子、音效
SEASON_ENVIRONMENT: Dict[str, Dict] = {
    "spring": {
        "sky_color": (0.55, 0.80, 0.95),
        "terrain": {"ground": "grass", "snow_cover": 0.0, "mud": 0.2, "foliage_density": 0.6},
        "vegetation": {"growth": 0.8, "leaf_color": "fresh_green", "flowers": True},
        "water": {"state": "liquid", "temperature": 12.0, "level": 0.7},
        "particles": ["pollen", "falling_petals"],
        "sounds": ["birds_chirping", "stream_flowing"],
    },
    "summer": {
        "sky_color": (0.35, 0.65, 1.00),
        "terrain": {"ground": "grass", "snow_cover": 0.0, "mud": 0.0, "foliage_density": 1.0},
        "vegetation": {"growth": 1.0, "leaf_color": "deep_green", "flowers": True},
        "water": {"state": "liquid", "temperature": 22.0, "level": 0.6},
        "particles": ["fireflies", "pollen"],
        "sounds": ["cicadas", "distant_thunder"],
    },
    "autumn": {
        "sky_color": (0.85, 0.70, 0.50),
        "terrain": {"ground": "leaf_litter", "snow_cover": 0.0, "mud": 0.1, "foliage_density": 0.4},
        "vegetation": {"growth": 0.3, "leaf_color": "amber", "flowers": False},
        "water": {"state": "liquid", "temperature": 10.0, "level": 0.5},
        "particles": ["falling_leaves"],
        "sounds": ["wind_through_leaves"],
    },
    "winter": {
        "sky_color": (0.75, 0.78, 0.85),
        "terrain": {"ground": "snow", "snow_cover": 1.0, "mud": 0.0, "foliage_density": 0.1},
        "vegetation": {"growth": 0.0, "leaf_color": "bare", "flowers": False},
        "water": {"state": "frozen", "temperature": -5.0, "level": 0.4},
        "particles": ["snowflakes"],
        "sounds": ["wind_howl"],
    },
}

# 天气联动：地面覆盖、移动物理（摩擦/移速修正）、视觉、粒子、音效
WEATHER_EFFECTS: Dict[str, Dict] = {
    "clear": {
        "ground_cover": None,
        "friction": 1.0,
        "movement_modifier": 1.0,
        "visuals": ["sun_halo", "lens_flare"],
        "particles": [],
        "sounds": [],
    },
    "rain": {
        "ground_cover": "puddles",
        "friction": 0.55,
        "movement_modifier": 0.85,
        "visuals": ["fog", "wet_ground", "overcast"],
        "particles": ["raindrops", "splashes"],
        "sounds": ["rainfall", "thunder"],
    },
    "storm": {
        "ground_cover": "puddles",
        "friction": 0.45,
        "movement_modifier": 0.75,
        "visuals": ["fog", "lightning_flash", "dark_clouds"],
        "particles": ["raindrops", "splashes"],
        "sounds": ["rainfall", "thunder", "wind_gust"],
    },
    "snow": {
        "ground_cover": "snow",
        "friction": 0.70,
        "movement_modifier": 0.80,
        "visuals": ["snow_haze", "white_out"],
        "particles": ["snowflakes"],
        "sounds": ["muffled_wind"],
    },
}

# 不同季节可觅食的食物
SEASON_FOOD: Dict[str, List[str]] = {
    "spring": ["new_shoots", "berries", "insects"],
    "summer": ["fruits", "fish", "insects"],
    "autumn": ["nuts", "mushrooms", "fallen_fruit"],
    "winter": ["stored_nuts", "bark", "roots"],
}

# 生物习性：是否冬眠、是否迁徙
CREATURE_TRAITS: Dict[str, Dict] = {
    "bear": {"hibernates": True, "migrates": False},
    "hedgehog": {"hibernates": True, "migrates": False},
    "bird": {"hibernates": False, "migrates": True},
    "deer": {"hibernates": False, "migrates": False},
    "rabbit": {"hibernates": False, "migrates": False},
}

# 季节事件：start/end 为季节进程比例（0~1），rewards 为参与奖励
SEASON_EVENTS: Dict[str, List[Dict]] = {
    "spring": [
        {"name": "blossom_festival", "start": 0.20, "end": 0.50,
         "rewards": {"exp": 100, "items": ["flower_crown", "petal_charm"]}},
    ],
    "summer": [
        {"name": "solstice_fair", "start": 0.30, "end": 0.60,
         "rewards": {"exp": 150, "items": ["sun_medal"]}},
    ],
    "autumn": [
        {"name": "harvest_festival", "start": 0.25, "end": 0.55,
         "rewards": {"exp": 120, "items": ["pumpkin_pie", "golden_sickle"]}},
    ],
    "winter": [
        {"name": "winter_feast", "start": 0.30, "end": 0.70,
         "rewards": {"exp": 200, "items": ["ice_crown", "warm_cloak"]}},
    ],
}


@dataclass
class Config:
    season_length: float = 90.0
    transition_length: float = 10.0
    start_season: str = "spring"


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_color(a: Tuple[float, ...], b: Tuple[float, ...], t: float) -> Tuple[float, ...]:
    return tuple(_lerp(x, y, t) for x, y in zip(a, b))


def _blend_profile(current: Dict, nxt: Dict, t: float) -> Dict:
    """按过渡进度 t 混合两个季节环境档案：数值插值，离散值在 t>=0.5 时切换。"""
    dominant = nxt if t >= 0.5 else current
    blended = {
        "sky_color": _lerp_color(current["sky_color"], nxt["sky_color"], t),
        "terrain": {},
        "vegetation": dict(dominant["vegetation"]),
        "water": dict(dominant["water"]),
        "particles": sorted(set(current["particles"]) | set(nxt["particles"])) if 0.0 < t < 1.0 else list(dominant["particles"]),
        "sounds": sorted(set(current["sounds"]) | set(nxt["sounds"])) if 0.0 < t < 1.0 else list(dominant["sounds"]),
    }
    for key in current["terrain"]:
        cur_v, nxt_v = current["terrain"][key], nxt["terrain"][key]
        if isinstance(cur_v, (int, float)) and isinstance(nxt_v, (int, float)):
            blended["terrain"][key] = _lerp(cur_v, nxt_v, t)
        else:
            blended["terrain"][key] = nxt_v if t >= 0.5 else cur_v
    for key in current["vegetation"]:
        cur_v, nxt_v = current["vegetation"][key], nxt["vegetation"][key]
        if isinstance(cur_v, (int, float)) and not isinstance(cur_v, bool) and isinstance(nxt_v, (int, float)) and not isinstance(nxt_v, bool):
            blended["vegetation"][key] = _lerp(cur_v, nxt_v, t)
    for key in current["water"]:
        cur_v, nxt_v = current["water"][key], nxt["water"][key]
        if isinstance(cur_v, (int, float)) and isinstance(nxt_v, (int, float)):
            blended["water"][key] = _lerp(cur_v, nxt_v, t)
    return blended


class SeasonSystem:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.season_length = float(self.config.get("season_length", Config.season_length))
        self.transition_length = float(self.config.get("transition_length", Config.transition_length))
        start = self.config.get("start_season", Config.start_season)
        if start not in SEASONS:
            raise ValueError(f"未知季节: {start}")
        self._start_season = start
        self._state = {}
        self._history = []
        self._season_index = SEASONS.index(start)
        self._season_time = 0.0
        self._elapsed = 0.0
        self.weather = self.config.get("weather", "clear")

    # ------------------------------------------------------------------
    # 基础驱动
    # ------------------------------------------------------------------
    def update(self, dt: float):
        """推进游戏时间，季节按周期自动切换。"""
        if dt < 0:
            raise ValueError("dt 不能为负")
        self._elapsed += dt
        self._season_time += dt
        while self._season_time >= self.season_length:
            self._season_time -= self.season_length
            old = SEASONS[self._season_index]
            self._season_index = (self._season_index + 1) % len(SEASONS)
            self._history.append({
                "from": old,
                "to": SEASONS[self._season_index],
                "at": self._elapsed,
            })

    def reset(self):
        self._state = {}
        self._history = []
        self._season_index = SEASONS.index(self._start_season)
        self._season_time = 0.0
        self._elapsed = 0.0

    # ------------------------------------------------------------------
    # 季节更新：周期 + 过渡
    # ------------------------------------------------------------------
    def _transition_progress(self) -> float:
        """季节末尾 transition_length 秒内从 0 渐变到 1。"""
        start = self.season_length - self.transition_length
        if self._season_time <= start:
            return 0.0
        return min(1.0, (self._season_time - start) / self.transition_length)

    def update_season(self, dt: Optional[float] = None) -> Dict:
        if dt is not None:
            self.update(dt)
        progress = self._transition_progress()
        return {
            "season": SEASONS[self._season_index],
            "next_season": SEASONS[(self._season_index + 1) % len(SEASONS)],
            "season_index": self._season_index,
            "season_time": self._season_time,
            "season_length": self.season_length,
            "season_progress": self._season_time / self.season_length,
            "transitioning": progress > 0.0,
            "transition_progress": progress,
            "year": int(self._elapsed // (self.season_length * len(SEASONS))),
            "history": list(self._history),
        }

    # ------------------------------------------------------------------
    # 环境变化：天空 + 地形 + 植被 + 水体 + 粒子 + 音效
    # ------------------------------------------------------------------
    def environment_change(self, weather: Optional[str] = None) -> Dict:
        t = self._transition_progress()
        current = SEASON_ENVIRONMENT[SEASONS[self._season_index]]
        nxt = SEASON_ENVIRONMENT[SEASONS[(self._season_index + 1) % len(SEASONS)]]
        env = _blend_profile(current, nxt, t)
        weather = weather or self.weather
        effects = WEATHER_EFFECTS.get(weather, WEATHER_EFFECTS["clear"])
        env["particles"] = sorted(set(env["particles"]) | set(effects["particles"]))
        env["sounds"] = sorted(set(env["sounds"]) | set(effects["sounds"]))
        env["weather"] = weather
        env["season"] = SEASONS[self._season_index]
        env["transition_progress"] = t
        return env

    # ------------------------------------------------------------------
    # 天气联动：地面覆盖 + 物理 + 视觉
    # ------------------------------------------------------------------
    def weather_interaction(self, weather: Optional[str] = None) -> Dict:
        weather = weather or self.weather
        effects = WEATHER_EFFECTS.get(weather, WEATHER_EFFECTS["clear"])
        season = SEASONS[self._season_index]
        ground_cover = effects["ground_cover"]
        snow_depth = 0.0
        if weather == "snow":
            snow_depth = 0.3 if season == "winter" else 0.1
        elif ground_cover is None and season == "winter":
            ground_cover = "snow"
            snow_depth = 0.2
        return {
            "weather": weather,
            "season": season,
            "ground_cover": ground_cover,
            "snow_depth": snow_depth,
            "physics": {
                "friction": effects["friction"],
                "movement_modifier": effects["movement_modifier"],
                "slippery": effects["friction"] < 1.0,
            },
            "visuals": list(effects["visuals"]),
            "particles": list(effects["particles"]),
            "sounds": list(effects["sounds"]),
        }

    # ------------------------------------------------------------------
    # 生物行为：冬眠 + 迁徙 + 觅食
    # ------------------------------------------------------------------
    def creature_behavior(self, creature: str) -> Dict:
        season = SEASONS[self._season_index]
        traits = CREATURE_TRAITS.get(creature, {"hibernates": False, "migrates": False})
        hibernating = traits["hibernates"] and season == "winter"
        migrating = traits["migrates"] and season in ("autumn", "winter")
        return {
            "creature": creature,
            "season": season,
            "hibernating": hibernating,
            "active": not hibernating,
            "migrating": migrating,
            "migration_direction": "south" if migrating else None,
            "foraging": not hibernating,
            "food": [] if hibernating else list(SEASON_FOOD[season]),
        }

    # ------------------------------------------------------------------
    # 季节事件：节日活动 + 奖励 + 倒计时
    # ------------------------------------------------------------------
    def season_events(self) -> List[Dict]:
        season = SEASONS[self._season_index]
        events = []
        for event in SEASON_EVENTS.get(season, []):
            start_at = event["start"] * self.season_length
            end_at = event["end"] * self.season_length
            active = start_at <= self._season_time < end_at
            events.append({
                "name": event["name"],
                "season": season,
                "active": active,
                "starts_at": start_at,
                "ends_at": end_at,
                "time_until_start": max(0.0, start_at - self._season_time),
                "time_until_end": max(0.0, end_at - self._season_time) if self._season_time >= start_at else end_at - start_at,
                "rewards": dict(event["rewards"]),
            })
        return events
