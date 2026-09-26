"""房源照片归档：照片进库前搬进不会被清理的目录（2026-09-26）

背景（实测查清）：网关保活线程**每小时**把 `$HERMES_HOME/cache/images`（老实例 `$HERMES_HOME/image_cache`）
里最后修改时间超过 24 小时的文件删掉 —— 而经纪人发来的房源照片就存在那里、`re_properties.images`
存的就是那些路径 ⇒ 照片上传一天后从磁盘消失，库里留下打不开的路径（海报 B 款会反过来找经纪人要照片）。

本文件钉两件事：
1. 归档行为（复制、幂等、链接/缺文件原样保留、同名不同图不互相覆盖）；
2. `add_property` / `add_property_images` 存进库的是**归档后**的路径。
"""
import json
from pathlib import Path

import pytest

from agent.real_estate_media import archive_images, images_archive_dir, is_archived


# ---------- 归档行为 ----------
@pytest.fixture
def archive(tmp_path, monkeypatch):
    """归档目录指向临时目录；返回 (归档目录, 造源文件的函数)"""
    target = tmp_path / "real_estate_images"
    monkeypatch.setenv("COCO_IMAGES_DIR", str(target))

    def _make_cache_photo(name: str, data: bytes = b"photo-bytes"):
        src_dir = tmp_path / "cache" / "images"
        src_dir.mkdir(parents=True, exist_ok=True)
        path = src_dir / name
        path.write_bytes(data)
        return path

    return target, _make_cache_photo


def test_local_photo_is_copied_into_archive(archive):
    target, make = archive
    src = make("img_abc123.jpg")
    got, detail = archive_images(str(src))

    archived = Path(got)
    assert archived.parent == target
    assert archived.exists() and archived.read_bytes() == b"photo-bytes"
    assert archived.name.startswith("img_abc123_") and archived.suffix == ".jpg"
    assert detail["archived"] == 1
    assert src.exists(), "原缓存文件要留着（消息里引用的还是它，24 小时后由网关自己回收）"


def test_same_photo_twice_does_not_duplicate(archive):
    target, make = archive
    src = make("img_abc123.jpg")
    first, _ = archive_images(str(src))
    second, detail = archive_images(str(src))

    assert first == second
    assert detail["archived"] == 0 and detail["already"] == 1
    assert len(list(target.iterdir())) == 1


def test_already_archived_path_is_untouched(archive):
    _target, make = archive
    src = make("img_abc123.jpg")
    archived, _ = archive_images(str(src))

    again, detail = archive_images(archived)
    assert again == archived
    assert detail["archived"] == 0


def test_url_and_missing_path_keep_original_value(archive):
    target, _make = archive
    url = "https://example.com/a.jpg"
    missing = "/tmp/does-not-exist-coco.jpg"
    got, detail = archive_images(f"{url},{missing}")

    assert got == f"{url},{missing}"
    assert detail["missing"] == [missing]
    assert not any(target.iterdir()), "链接和找不到的文件都不该在归档目录里造东西"


def test_same_name_different_content_does_not_overwrite(archive):
    target, make = archive
    first, _ = archive_images(str(make("img_same.jpg", b"first")))
    second, _ = archive_images(str(make("img_same.jpg", b"second")))

    assert first != second
    assert {Path(first).read_bytes(), Path(second).read_bytes()} == {b"first", b"second"}
    assert len(list(target.iterdir())) == 2


def test_empty_value_stays_empty(archive):
    assert archive_images(None) == (None, {"archived": 0, "already": 0, "missing": [], "failed": []})
    assert archive_images("  ")[0] is None


def test_archive_dir_reads_env_at_call_time(tmp_path, monkeypatch):
    """目录要现算（读环境变量），不能缓存在 import 期 —— 否则多 profile / 改配置都不生效"""
    monkeypatch.setenv("COCO_IMAGES_DIR", str(tmp_path / "one"))
    assert images_archive_dir() == tmp_path / "one"
    monkeypatch.setenv("COCO_IMAGES_DIR", str(tmp_path / "two"))
    assert images_archive_dir() == tmp_path / "two"
    assert is_archived(str(tmp_path / "two" / "img_x.jpg"))


# ---------- 工具层：入库的是归档后的路径 ----------
def _registry(tmp_path, monkeypatch, archive_dir):
    url = f"sqlite:///{tmp_path}/image_archive.db"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("COCO_IMAGES_DIR", str(archive_dir))
    from agent.real_estate_db import init_real_estate_db

    init_real_estate_db(url)
    import model_tools  # noqa: F401 —— 触发工具发现与注册

    from tools.registry import registry

    return registry


def _call(registry, name, args):
    return json.loads(registry.get_entry(name).handler(args, session_id="agent:main:feishu:dm:oc_x"))


def test_add_property_stores_archived_path(tmp_path, monkeypatch):
    archive_dir = tmp_path / "real_estate_images"
    registry = _registry(tmp_path, monkeypatch, archive_dir)
    photo = tmp_path / "cache" / "images" / "img_777aaa.jpg"
    photo.parent.mkdir(parents=True, exist_ok=True)
    photo.write_bytes(b"front-photo")

    out = _call(registry, "add_property", {
        "title": "归档测试 1号楼2单元101", "price": 1_000_000, "area": 88.0,
        "image_paths": str(photo),
    })

    assert out["success"] is True
    stored = out["property"]["images"]
    assert stored.startswith(str(archive_dir)), f"库里应存归档路径，实际 {stored}"
    assert Path(stored).exists()
    assert "image_archive" not in out, "归档成功时不该给告警字段"


def test_add_property_images_archives_and_keeps_missing_warning(tmp_path, monkeypatch):
    archive_dir = tmp_path / "real_estate_images"
    registry = _registry(tmp_path, monkeypatch, archive_dir)
    created = _call(registry, "add_property", {"title": "归档测试 2号楼101", "price": 900_000, "area": 70.0})
    pid = created["property"]["id"]
    photo = tmp_path / "cache" / "images" / "img_888bbb.jpg"
    photo.parent.mkdir(parents=True, exist_ok=True)
    photo.write_bytes(b"living-room")

    out = _call(registry, "add_property_images", {"property_id": pid, "images": str(photo)})
    assert out["added_count"] == 1
    stored = out["property"]["images"]
    assert stored.startswith(str(archive_dir)) and Path(stored).exists()

    missing = _call(registry, "add_property_images",
                    {"property_id": pid, "images": "/tmp/not-here-coco.jpg"})
    warnings = " ".join(missing.get("warnings") or [])
    assert "没找到" in warnings, "找不到的本地文件仍要如实提示（口径不变）"
