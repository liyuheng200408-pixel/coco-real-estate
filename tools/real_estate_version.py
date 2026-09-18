"""Coco 自身版本信息工具（经纪人问"你是什么版本"时用）

版本号存在仓库根 VERSION（形如 0.21.3-7：前半段是官方 Hermes 版本，后半段是本仓库第 N 次发行）。
官方 `hermes --version` 显示的是底座版本，不是 Coco 版本——所以这个信息必须由 Coco 自己如实回答，
不能让模型猜。
"""
import json
from pathlib import Path

from tools.registry import registry

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_first_line(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def get_coco_version(task_id: str = None) -> str:
    """查询 Coco 当前版本号（含所基于的官方 Hermes 版本）"""
    ver = _read_first_line(REPO_ROOT / "VERSION") or "未知"
    base = ver.split("-")[0] if "-" in ver else ver
    upstream = _read_first_line(REPO_ROOT / "UPSTREAM_VERSION").splitlines()
    return json.dumps({
        "success": True,
        "coco_version": ver,
        "hermes_base": base,
        "upstream_tag": upstream[0] if upstream else None,
        "message": f"Coco v{ver}（官方 Hermes {base} 定制版）",
    }, ensure_ascii=False)


registry.register(
    name="get_coco_version",
    toolset="real_estate",
    schema={"name": "get_coco_version", "description": "查询 Coco 自身的版本号（含所基于的官方 Hermes 版本）。经纪人问'你是什么版本/系统版本号是多少/是不是最新版/该不该更新'时调用本工具如实回答。注意：`hermes --version` 显示的是底座（官方 Hermes）版本，不是 Coco 版本，不要拿它当答案。", "parameters": {
        "type": "object",
        "properties": {},
    }},
    handler=lambda args, **kw: get_coco_version(),
)
