"""「一串多个值」的参数：数组与逗号串都要认（2026-09-26）

起因：模型把这类参数**当数组传是常态**（`image_paths=["/tmp/a.jpg"]`、`tags=["近地铁","学区房"]`），
而实现按逗号串写（`.split(',')`）或原样塞进 `Text` 列 → 实测崩：

| 调用 | 崩法 |
|---|---|
| `add_property(image_paths=[…])` | `AttributeError: 'list' object has no attribute 'split'` |
| `add_property(images=[…])` | 同上 |
| `add_property(tags=[…])` | 数据库层 `type 'list' is not supported`（离线库也一样） |
| `update_property(tags=[…])` | 数据库层同上 |

契约（与 F102/F117 同族）：**数组元素逐个过同一套清洗**（转文本、去空白、丢空项），
"没给"与"给了空"归到同一档（不往库里写空串）；字符串照旧原样走各自的归一化。
"""
import json

import pytest
from conftest import make_property  # noqa: F401

from agent.real_estate_input import as_comma_text


# ---------- 共用件 ----------
@pytest.mark.parametrize("value,expected", [
    (None, None),
    ("", None),
    ("   ", None),
    ([], None),
    (["", "   "], None),
    ("/tmp/a.jpg", "/tmp/a.jpg"),                    # 字符串原样（不重排、不拆分）
    ("a.jpg, b.jpg", "a.jpg, b.jpg"),
    (["/tmp/a.jpg", "/tmp/b.jpg"], "/tmp/a.jpg,/tmp/b.jpg"),
    ([" /tmp/a.jpg ", "", "/tmp/b.jpg"], "/tmp/a.jpg,/tmp/b.jpg"),   # 去空白 + 丢空项
    (("/tmp/a.jpg", "/tmp/b.jpg"), "/tmp/a.jpg,/tmp/b.jpg"),         # 元组也认
    (["近地铁", "学区房"], "近地铁,学区房"),
    ([1, 2], "1,2"),                                  # 数字元素转文本（别让模型挨骂）
])
def test_as_comma_text(value, expected):
    assert as_comma_text(value) == expected


def test_as_comma_text_does_not_reorder_or_dedupe():
    """数组按原顺序拼（去重/归一留给各字段自己的口径，别在这里偷偷改语义）"""
    assert as_comma_text(["b", "a", "b"]) == "b,a,b"
