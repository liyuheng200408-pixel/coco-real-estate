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


from agent.coco_cron import _AVAILABLE_JOBS  # noqa: E402

DAILY_PROMPT = next(item[3] for item in _AVAILABLE_JOBS if item[2] == "coco_daily_report")


class TestReportWordingGuards:
    """日报口径（2026-09-23 老板要求）：等级四级全列、数据要点只留解读

    真实教训：早报写"暂无 S 级 / A 级高意向客户"，把 B 级漏了；根源是早报的
    定时任务提示词只点了 S/A，且"数据要点"重复了上面已经列过的数字。
    """

    def test_prompt_requires_all_four_tiers(self):
        assert "【日报口径】" in PROMPT
        assert "S / A / B / C 四级都要提" in PROMPT
        assert "不要重复上面已经单列过的数字" in PROMPT

    def test_manual_has_report_rule(self):
        assert "日报口径（2026-09-23 加）" in MANUAL
        assert "S/A/B/C 四级都要提" in MANUAL

    def test_daily_cron_asks_for_all_tiers(self):
        """盯实际注册的早报提示词（不是整份文件——文件里会提到旧文案作为教训）"""
        assert "S/A/B/C 四级都要提" in DAILY_PROMPT
        assert "不要添加引导清单" in DAILY_PROMPT
        assert "S/A级客户状态" not in DAILY_PROMPT, "旧口径（只点 S/A）是漏 B 级的根源"


class TestGuidanceMenuGuards:
    """引导菜单话术（2026-09-23 老板选定版本 2）：只列 Coco 真能做的事"""

    def test_prompt_has_fixed_menu(self):
        assert "【引导菜单标准话术】" in PROMPT
        assert "我帮你录：客户、房源、跟进、带看结果、成交单" in PROMPT
        assert "我帮你配：客户 ↔ 房源匹配" in PROMPT
        assert "我帮你推：成交节点提醒（定金→签约→贷款→过户→交房）" in PROMPT
        assert "我帮你出：日报 / 周报 / 业绩看板" in PROMPT

    def test_prompt_forbids_claiming_viewing_and_deal(self):
        assert "不能替经纪人带看或成交" in PROMPT

    def test_prompt_covers_greeting_scene(self):
        """老板确认：这段清单是 Coco 打招呼时说的（不是早报带的）"""
        assert "打招呼（开场自我介绍）时" in PROMPT
        assert "开场带这段清单是可以的" in PROMPT

    def test_manual_has_menu_script(self):
        assert "引导菜单话术（2026-09-23 加）" in MANUAL
        assert "我帮你**录**（客户/房源/跟进/带看结果/成交单）" in MANUAL
