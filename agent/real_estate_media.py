"""房源照片归档：把照片从「会被自动清理的网关缓存目录」复制进不会被清理的归档目录。

背景（2026-09-26 查清）：网关保活线程**每小时**把 `$HERMES_HOME/cache/images`（老实例是
`$HERMES_HOME/image_cache`）里最后修改时间超过 24 小时的文件删掉。而经纪人发来的房源照片就
存在那里、`re_properties.images` 存的就是那些路径 → 照片上传一天后从磁盘消失，库里留下打不开
的路径（海报 B 款会反过来找经纪人要照片）。

修法：照片**进库前**复制一份到 `$HERMES_HOME/real_estate_images/`（不在任何清理名单里），
库里存归档后的路径。原有缓存文件不动 —— 别的链路（消息里的图片路径）还在引用它，24 小时后
由网关自己回收。

归档命名：`<原文件名主体>_<内容指纹 8 位><扩展名>`。指纹保证「同名不同图」不会互相覆盖，
也让「同一张图重发」落到同一个文件名（幂等：目标已存在就不再复制）。
"""
import hashlib
import os
import re
import shutil
from pathlib import Path

# 归档目录可用环境变量改（与 gateway 的媒体缓存目录口径一致：读取时现算，不缓存到 import 期）
ARCHIVE_DIR_ENV = "COCO_IMAGES_DIR"
_ARCHIVE_DIR_NAME = "real_estate_images"
_SAFE_EXT_RE = re.compile(r"^\.[A-Za-z0-9]{1,5}$")


def images_archive_dir() -> Path:
    """房源照片归档目录（默认 `$HERMES_HOME/real_estate_images`，创建后返回）"""
    override = os.getenv(ARCHIVE_DIR_ENV, "").strip()
    if override:
        path = Path(override).expanduser()
    else:
        try:
            from hermes_constants import get_hermes_home

            path = get_hermes_home() / _ARCHIVE_DIR_NAME
        except Exception:  # noqa: BLE001 —— 拿不到框架工具时退回默认家目录，别让录入失败
            path = Path.home() / ".hermes" / _ARCHIVE_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_archived(path) -> bool:
    """该路径是否已经在归档目录里（已在则无需再复制）"""
    if not path:
        return False
    try:
        target = images_archive_dir()
        return Path(os.path.abspath(str(path))).parent == Path(os.path.abspath(str(target)))
    except Exception:  # noqa: BLE001
        return False


def _is_url(value: str) -> bool:
    return "://" in value


def _archived_name(source: Path) -> tuple[str, str]:
    """按内容指纹算归档文件名；返回 (文件名, 指纹)"""
    digest = hashlib.sha1()
    with open(source, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    fingerprint = digest.hexdigest()[:8]
    ext = source.suffix.lower()
    if not _SAFE_EXT_RE.match(ext):
        ext = ".jpg"
    return f"{source.stem}_{fingerprint}{ext}", fingerprint


def archive_images(value):
    """把「一串图片」（逗号串或数组，已是归一化后的逗号串也认）里的本机文件复制进归档目录。

    返回 `(新的逗号串, 明细)`：
    - 链接（含 ://）：原样保留（不动网络图片）；
    - 已在归档目录里的路径：原样保留；
    - 本机存在但不在归档目录的文件：复制一份，返回归档后的路径（同一张图重复调用只复制一次）；
    - 本机找不到的文件：原样保留（由调用方决定怎么如实告知，别在这里臆造）。
    明细形如 `{"archived": n, "already": n, "missing": [...], "failed": [(路径, 原因)]}`。
    """
    from agent.real_estate_input import as_comma_text

    text = as_comma_text(value)
    detail = {"archived": 0, "already": 0, "missing": [], "failed": []}
    if not text:
        return text, detail

    out = []
    for item in [x.strip() for x in text.split(",") if x.strip()]:
        if _is_url(item) or is_archived(item):
            out.append(item)
            detail["already"] += 1
            continue
        source = Path(item).expanduser()
        if not source.is_file():
            out.append(item)
            detail["missing"].append(item)
            continue
        try:
            name, _ = _archived_name(source)
            target = images_archive_dir() / name
            if not target.exists():
                shutil.copy2(source, target)
                detail["archived"] += 1
            else:
                detail["already"] += 1
            out.append(str(target))
        except Exception as exc:  # noqa: BLE001 —— 归档失败不拦录入，保留原路径（由调用方如实说明）
            out.append(item)
            detail["failed"].append((item, str(exc)))
    return ",".join(out) if out else None, detail
