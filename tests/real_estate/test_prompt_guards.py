"""提示词护栏的回归测试（防被删/被改回去）。

2026-09-21 真实教训：Coco 说「update_property 工具不支持楼层字段」，而系统早已支持——
它沿用了几轮前的旧结论、没重新调用工具，导致经纪人被误导。为此加了一条通用护栏
「禁止臆断工具能力」。本文件钉住它，以及同批加的楼层/朝向字段规则仍在位。
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT = (REPO_ROOT / "agent" / "real_estate_prompt.py").read_text(encoding="utf-8")
MANUAL = (REPO_ROOT / "skills" / "real_estate" / "SKILL.md").read_text(encoding="utf-8")


class TestNoCapabilityGuessingGuard:
    def test_prompt_has_the_guard(self):
        assert "禁止臆断工具能力" in PROMPT
        # 核心要求：先真的调用工具；只有明确报错才允许说“不支持”
        assert "先调用对应工具用真实参数试一次" in PROMPT
        assert "未知参数" in PROMPT
        # 旧结论不算证据
        assert "不算证据" in PROMPT

    def test_manual_has_the_guard(self):
        assert "禁止臆断工具能力" in MANUAL

    def test_floor_orientation_rules_still_present(self):
        """同批加的楼层/朝向规则不能被顺手删掉"""
        assert "楼层/朝向等字段要单独传参" in PROMPT
        assert "楼层与朝向等字段必须单独传参" in MANUAL
