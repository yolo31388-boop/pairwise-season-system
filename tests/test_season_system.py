"""
游戏内季节系统与环境变化系统 - 验收测试
运行方式：python -m pytest tests/test_season_system.py -q
共 14 个测试用例
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from world.season_system import SeasonSystem


class TestSeasonSystem:
    def setup_method(self):
        self.system = SeasonSystem()

    # ---- update_season：周期与自动切换 ----
    def test_case_01(self):
        """季节按周期自动切换：spring -> summer"""
        assert self.system.update_season()["season"] == "spring"
        self.system.update(90.0)
        state = self.system.update_season()
        assert state["season"] == "summer"
        assert state["season_index"] == 1

    def test_case_02(self):
        """季节完整循环：春夏秋冬后回到春天"""
        self.system.update(90.0 * 4)
        state = self.system.update_season()
        assert state["season"] == "spring"
        assert state["year"] == 1
        transitions = [(h["from"], h["to"]) for h in state["history"]]
        assert transitions == [
            ("spring", "summer"),
            ("summer", "autumn"),
            ("autumn", "winter"),
            ("winter", "spring"),
        ]

    def test_case_03(self):
        """季节切换有过渡渐变而不是瞬间跳变"""
        self.system.update(85.0)  # 进入过渡区（90-10=80 之后）
        state = self.system.update_season()
        assert state["transitioning"] is True
        assert 0.0 < state["transition_progress"] < 1.0
        assert state["transition_progress"] == pytest.approx(0.5)
        env = self.system.environment_change()
        spring_sky = (0.55, 0.80, 0.95)
        summer_sky = (0.35, 0.65, 1.00)
        # 天空颜色应在两个季节之间插值，而非等于任一端
        assert env["sky_color"] != spring_sky
        assert env["sky_color"] != summer_sky
        for got, a, b in zip(env["sky_color"], spring_sky, summer_sky):
            assert min(a, b) <= got <= max(a, b)

    # ---- environment_change：地形/植被/水体 + 粒子 + 音效 ----
    def test_case_04(self):
        """环境变化不止天空：地形、植被、水体都随季节改变"""
        spring_env = self.system.environment_change()
        self.system.update(90.0 * 3)  # 进入冬天
        winter_env = self.system.environment_change()
        assert spring_env["terrain"] != winter_env["terrain"]
        assert winter_env["terrain"]["snow_cover"] == 1.0
        assert winter_env["terrain"]["ground"] == "snow"
        assert spring_env["vegetation"] != winter_env["vegetation"]
        assert winter_env["vegetation"]["growth"] == 0.0
        assert spring_env["water"] != winter_env["water"]
        assert winter_env["water"]["state"] == "frozen"
        assert spring_env["sky_color"] != winter_env["sky_color"]

    def test_case_05(self):
        """环境变化有粒子效果：下雪有雪花、下雨有雨滴"""
        winter = SeasonSystem({"start_season": "winter"})
        env = winter.environment_change(weather="snow")
        assert "snowflakes" in env["particles"]
        rainy = self.system.environment_change(weather="rain")
        assert "raindrops" in rainy["particles"]

    def test_case_06(self):
        """环境变化有音效：打雷有声音"""
        storm_env = self.system.environment_change(weather="storm")
        assert "thunder" in storm_env["sounds"]
        assert len(storm_env["sounds"]) > 0

    # ---- weather_interaction：地面覆盖 + 物理 + 视觉 ----
    def test_case_07(self):
        """下雪天地面有积雪"""
        result = self.system.weather_interaction("snow")
        assert result["ground_cover"] == "snow"
        assert result["snow_depth"] > 0.0

    def test_case_08(self):
        """天气联动有物理：雨天路滑影响移动"""
        rain = self.system.weather_interaction("rain")
        clear = self.system.weather_interaction("clear")
        assert rain["physics"]["friction"] < clear["physics"]["friction"]
        assert rain["physics"]["movement_modifier"] < 1.0
        assert rain["physics"]["slippery"] is True

    def test_case_09(self):
        """天气联动有视觉：雨天有雾气、晴天有光晕"""
        rain = self.system.weather_interaction("rain")
        assert "fog" in rain["visuals"]
        clear = self.system.weather_interaction("clear")
        assert "sun_halo" in clear["visuals"]

    # ---- creature_behavior：冬眠 + 迁徙 + 觅食 ----
    def test_case_10(self):
        """冬天动物冬眠"""
        winter = SeasonSystem({"start_season": "winter"})
        bear = winter.creature_behavior("bear")
        assert bear["hibernating"] is True
        assert bear["active"] is False
        summer_bear = self.system.creature_behavior("bear")
        assert summer_bear["hibernating"] is False

    def test_case_11(self):
        """鸟类秋冬季节往南迁徙"""
        autumn = SeasonSystem({"start_season": "autumn"})
        bird = autumn.creature_behavior("bird")
        assert bird["migrating"] is True
        assert bird["migration_direction"] == "south"
        spring_bird = self.system.creature_behavior("bird")
        assert spring_bird["migrating"] is False

    def test_case_12(self):
        """不同季节觅食的食物不同"""
        spring_food = self.system.creature_behavior("deer")["food"]
        winter = SeasonSystem({"start_season": "winter"})
        winter_food = winter.creature_behavior("deer")["food"]
        assert spring_food
        assert winter_food
        assert spring_food != winter_food

    # ---- season_events：节日活动 + 奖励 + 倒计时 ----
    def test_case_13(self):
        """季节事件存在且参与有奖励"""
        events = self.system.season_events()
        assert len(events) > 0
        for event in events:
            assert event["rewards"]
            assert event["rewards"]["exp"] > 0
            assert len(event["rewards"]["items"]) > 0

    def test_case_14(self):
        """季节事件有倒计时：可知开始与结束时间"""
        events = self.system.season_events()
        event = events[0]
        assert event["active"] is False
        assert event["time_until_start"] > 0.0
        assert event["time_until_end"] > 0.0
        # 推进到事件进行中：倒计时归零，结束倒计时减少
        self.system.update(event["starts_at"] + 1.0)
        active_event = self.system.season_events()[0]
        assert active_event["active"] is True
        assert active_event["time_until_start"] == 0.0
        assert 0.0 < active_event["time_until_end"] < event["time_until_end"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
