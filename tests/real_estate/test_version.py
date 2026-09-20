"""Coco 版本查询工具 get_coco_version 测试（2026-09-18 加）

版本号来自仓库根 VERSION；官方 `hermes --version` 只显示底座版本，所以必须由工具如实回答。
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestCocoVersion:
    def test_returns_repo_version(self):
        """返回值与仓库根 VERSION 一致，并推导出底座版本"""
        import tools.real_estate_version as vmod
        data = json.loads(vmod.get_coco_version())
        assert data["success"] is True
        ver = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        assert data["coco_version"] == ver
        assert data["hermes_base"] == ver.split("-")[0]

    def test_message_is_user_facing_wording(self):
        """对外措辞统一为「官方 Hermes X 定制版」"""
        import tools.real_estate_version as vmod
        data = json.loads(vmod.get_coco_version())
        assert re.match(r"^Coco v[\d.]+-\d+（官方 Hermes [\d.]+ 定制版）$", data["message"])

    def test_upstream_tag_reported(self):
        """同时回报所基于的官方 tag（供排查用）"""
        import tools.real_estate_version as vmod
        data = json.loads(vmod.get_coco_version())
        assert data["upstream_tag"] and data["upstream_tag"].startswith("v")

    def test_registry_dispatch_ignores_runtime_kwargs(self):
        """走注册表真实分发：框架注入的 session_id/task_id 不能把工具调用打崩"""
        import tools.real_estate_version  # noqa: F401 —— 触发注册
        import model_tools  # noqa: F401
        from tools.registry import registry
        entry = registry.get_entry("get_coco_version")
        assert entry is not None
        data = json.loads(entry.handler({}, session_id="agent:main:feishu:dm:oc_x", task_id="t1"))
        assert data["success"] is True

    def test_exposed_in_real_estate_toolset(self):
        """必须在 real_estate 工具集清单里，否则模型看不到这个工具"""
        from toolsets import TOOLSETS
        assert "get_coco_version" in TOOLSETS["real_estate"]["tools"]


class TestReleaseVersionConsistency:
    """发版一致性：安装包名与 README 的版本行都必须跟着仓库根 VERSION 走。

    为什么要有：桌面版安装包的文件名取 apps/desktop/package.json 的 version
    （electron-builder 的 artifactName 用 ${version}），而版本权威是仓库根 VERSION ——
    实测打出来的包叫 Coco-0.21.3-53-win-x64.exe，而当时 VERSION 已经是 0.21.3-55，
    用户会以为装到了旧版。构建时也会从 VERSION 盖章（desktop-windows.yml），
    这条测试守住仓库里的两处不被忘掉。
    """

    def test_desktop_package_version_matches_repo_version(self):
        import json as _json

        ver = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        pkg = _json.loads((REPO_ROOT / "apps" / "desktop" / "package.json").read_text(encoding="utf-8"))
        assert pkg["version"] == ver, f"apps/desktop/package.json 是 {pkg['version']}，VERSION 是 {ver}"

    def test_installer_clones_coco_not_upstream_hermes(self):
        """首启引导脚本必须克隆 Coco 仓库，不能是官方 Hermes。

        为什么钉这条：桌面版首启会下载并执行 install.ps1，而官方原版写死克隆
        NousResearch/hermes-agent —— 装出来是官方 Hermes（没有 real_estate 工具集、
        没有身份定制），用户以为装了 Coco 却是空壳。实测已修（Gitee 主源 + GitHub 兜底）。
        """
        text = (REPO_ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")
        assert "coco-real-estate.git" in text, "install.ps1 没有指向 Coco 仓库"
        assert "NousResearch/hermes-agent" not in text, "install.ps1 仍在克隆官方 Hermes 仓库"

    def test_readmes_advertise_the_repo_version(self):
        ver = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        for name in ("README.md", "README.zh-CN.md"):
            text = (REPO_ROOT / name).read_text(encoding="utf-8")
            assert f"v{ver}" in text, f"{name} 里没有当前版本 v{ver}（发版时漏改）"
