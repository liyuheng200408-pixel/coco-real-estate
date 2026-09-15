# Coco 改动集（patches）

本目录记录 **Coco 相对官方 Hermes 源码的全部改动**，用途有两个：

1. **看得清**：同步官方新版本时，知道自己改了官方哪些地方、每处是干什么的；
2. **不遗漏**：同步后配合 `scripts/check_coco_hooks.py` 逐项自检，防止改动丢失。

## 这些补丁怎么来的

以官方 **2026-08-09 的主线快照**（commit `3bd844edf1777a680115f88a68474b4fb434092f`）为基准，
与 Coco 当前代码逐文件对比生成。

> ⚠️ **重要用法说明**：这些 `.patch` 文件是**改动记录**，不是拿来机械 `git apply` 的。
> 官方一旦改动了同一个文件（几乎必然），补丁就会 apply 失败。
> **正确的做法**：读本文件下面每一处的「改什么 / 为什么 / 上游变了怎么办」，
> 在新底座上重新实现，再用自检脚本验证结果。

## 改动清单（共 7 处官方文件 + 2 个自有文档）

| 编号 | 官方文件 | 改动内容 |
|---|---|---|
| 01 | `toolsets.py` | 注册 `real_estate` 工具集，并把 `real_estate` 挂进 `hermes-feishu` 工具集的 `includes` |
| 02 | `agent/prompt_builder.py` | 把身份文案常量（`DEFAULT_AGENT_IDENTITY`、能力说明等）内容换成 Coco |
| 03 | `agent/system_prompt.py` | 把房产提示词 `get_real_estate_prompt()` 拼进稳定提示词片段 |
| 04 | `agent/agent_init.py` | 启动时调用 `init_real_estate_db()` 初始化房产库 |
| 05 | `hermes_cli/config_defaults.py` | 压缩阈值 `threshold` 0.50→**0.8**、`protect_last_n` 20→**40** |
| 06 | `plugins/platforms/feishu/adapter.py` | 首次对话三件事：发欢迎语、发加密密钥备份提醒、自动注册定时任务 |
| 07 | `gateway/run.py` | 首次对话开场白换成 Coco 自我介绍；关闭官方 profile-build 引导 |

另有 2 个**自有文档**（不属于官方代码，同步时直接保留即可）：
`README.md`、`README.zh-CN.md`。

## 逐处说明

### 01 toolsets.py —— 工具集注册（最关键，漏了模型就"没能力"）
- **改什么**：在 `TOOLSETS` 字典里新增 `real_estate` 工具集定义；并在 `hermes-feishu`
  工具集的 `includes` 列表中加入 `"real_estate"`。
- **为什么**：Hermes 靠工具集清单决定"哪些工具发给模型"。不注册，模型完全看不到
  房产工具，会回答"我没有这个能力"。
- **上游变了怎么办**：官方若重构工具集结构，按新结构重新挂载；关键是
  **两个条件都要满足**（定义 + 被 hermes-feishu 引用）。

### 02 agent/prompt_builder.py —— 身份文案
- **改什么**：把默认身份常量等内容替换为 Coco 版本（"你是 Coco（可可），经纪人的
  客户和房源管家…"），以及"你能做什么"的回答指引。
- **为什么**：这是 Coco 自我介绍的第一来源。注意 Coco 的身份文案在**共 7 处**都有
  副本（adapter 欢迎语、gateway 开场白、prompt_builder、房产提示词、SOUL.md、
  技能文件等），改身份必须全部同步，否则会出现"改了这里那里还是旧文案"。
- **上游变了怎么办**：定位新版的对应常量名（可能改名），重新替换内容。

### 03 agent/system_prompt.py —— 注入房产提示词
- **改什么**：导入 `get_real_estate_prompt()` 并把返回值拼进稳定提示词片段。
- **为什么**：房产规则（登记规范、匹配原则、统计口径等）靠它注入。
- **上游变了怎么办**：找到新版系统提示词的拼装位置（函数名/变量名可能变），
  在同一位置恢复注入。**必须保持"稳定片段"语义**（不要拼进每轮变化的部分，
  否则会破坏 prompt 缓存、增加成本）。

### 04 agent/agent_init.py —— 启动初始化数据库
- **改什么**：导入并调用 `init_real_estate_db(db_url)`。
- **为什么**：CLI 启动路径需要建表。（注：gateway 启动路径不经过 agent_init，
  靠 `get_real_estate_db()` 的惰性初始化兜底；两条路都得在。）
- **上游变了怎么办**：找到新版 CLI 初始化入口，恢复调用。

### 05 hermes_cli/config_defaults.py —— 压缩阈值
- **改什么**：`threshold` 0.50 → **0.8**；`protect_last_n` 20 → **40**。
- **为什么**：老板 2026-08-29 定的统一配置（与生产 Coco 保持一致），
  压得太早会丢上下文。
- **上游变了怎么办**：新版若换了配置键名或结构，按新结构设置相同语义的值。

### 06 plugins/platforms/feishu/adapter.py —— 首次对话三件事
- **改什么**：
  1. `_maybe_send_coco_welcome`：首次对话发送固定欢迎语（marker 文件控制只发一次）；
  2. 首次对话把加密密钥（`~/backups/real_estate/enc_key.txt`）内容直接发给经纪人
     —— 密钥丢失=客户手机号永久不可解密，所以要在聊天记录里留一份；
  3. 首次对话自动注册定时任务（早报/午间/逾期，走 `register_coco_cron_jobs`）。
- **为什么**：这三件事决定了经纪人第一次接触 Coco 的体验与数据安全兜底。
- **上游变了怎么办**：官方对飞书适配器改动频繁（同期约 25 个提交）。找到新版
  "接收消息 → 处理"的入口，把这三件事挂回去；marker 文件路径保持
  `~/.hermes/.coco_welcome_sent`。

### 07 gateway/run.py —— 首次对话开场白
- **改什么**：网关首次对话的开场白换成 Coco 自我介绍；跳过官方的
  profile-build 引导流程。
- **为什么**：不经 adapter 的路径（模型自己输出自我介绍时）也需要正确文案，
  否则问"你是谁"会得到官方默认回答。
- **上游变了怎么办**：gateway/run.py 是官方改动最频繁的文件之一（同期 2,000+
  提交）。定位新版"首次对话/开场白"的逻辑点重新挂钩，不要试图保留旧代码块。

## 使用方法（同步时）

```bash
# 1. 交换血前先看这份清单，确认要重新应用哪几处
cat patches/README.md

# 2. 同步（脚本会替换官方层文件、保留 Coco 自有文件，并列出需要人工处理的点）
bash scripts/sync_upstream.sh <官方版本tag>

# 3. 逐处重新应用上面的改动
#    （按语义在新版代码里实现，不要机械 apply patch）

# 4. 自检：确认 7 处挂钩点 + 自建文件都在
python3 scripts/check_coco_hooks.py

# 5. 三层验收
python3 scripts/healthcheck.py
python3 scripts/smoke_test_real_estate.py
# 单测 + 飞书实测见 docs/UPSTREAM_SYNC.md
```

## 已知局限

- 补丁基于 2026-08-09 基准生成；我们的代码导入点与任何单一官方快照都不完全重合，
  因此 patch 中可能夹带少量"官方版本漂移"的内容。**以本文件的语义说明为准。**
- `07-gateway-run-greeting.patch` 体积较大（官方该文件改动频繁），仅作参考。
  实际同步时按语义在新版里重新挂钩。
