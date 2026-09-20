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

## 改动清单（共 9 处官方文件 + 2 个自有文档）

| 编号 | 官方文件 | 改动内容 |
|---|---|---|
| 01 | `toolsets.py` | 注册 `real_estate` 工具集，并把 `real_estate` 挂进 `hermes-feishu` 工具集的 `includes` |
| 02 | `agent/prompt_builder.py` | 把身份文案常量（`DEFAULT_AGENT_IDENTITY`、能力说明等）内容换成 Coco |
| 03 | `agent/system_prompt.py` | 把房产提示词 `get_real_estate_prompt()` 拼进稳定提示词片段 |
| 04 | `agent/agent_init.py` | 启动时调用 `init_real_estate_db()` 初始化房产库 |
| 05 | `hermes_cli/config_defaults.py` | 压缩阈值 `threshold` 0.50→**0.8**、`protect_last_n` 20→**40** |
| 06 | `plugins/platforms/feishu/adapter.py` | 首次对话三件事：发欢迎语、发加密密钥备份提醒、自动注册定时任务 |
| 07 | `gateway/run_turn.py`（官方 v0.21 起从 `gateway/run.py` 拆到这里） | 首次对话开场白换成 Coco 自我介绍；关闭官方 profile-build 引导 |
| 08 | `scripts/sandbox/pick-release-tags.sh` | 标签过滤正则放宽：同时认「日期式 `vYYYY.M.D`」和「语义化 `vX.Y.Z`（含 `-N` 后缀）」 |
| 09 | `apps/desktop/electron/backend-env.ts`、`apps/desktop/electron/main.ts` | 桌面版「本机模式」接上便携 PostgreSQL：后端 PATH 带 `pgsql\bin`、后端环境注入 `DATABASE_URL`、拉起后端前先确保数据库在跑 |
| 10 | `scripts/install.ps1` | 安装器新增阶段 `coco-database`（在依赖之后、PATH 之前）：下载/初始化便携 PostgreSQL 并写出 `.env.db`，让首启界面能看到这一步 |

另有 2 个**自有文档**（不属于官方代码，同步时直接保留即可）：
`README.md`、`README.zh-CN.md`。

## 逐处说明

### 09 桌面版 electron（本机模式的便携 PostgreSQL 接线）
- **改什么**：
  - `backend-env.ts`：新增 `hermesManagedPostgresPathEntries()`（返回 `<hermesHome>/pgsql/bin`），
    并把它拼进 `buildDesktopBackendPath()`（位置：Hermes 自带的 node 目录与 venv 之后、
    继承来的 PATH 之前 —— 既不破坏官方既有的 node 优先顺序，又能压过系统里可能存在的
    另一个 PostgreSQL）；`buildDesktopBackendEnv()` 新增可选参数 `databaseUrl`，只在它是
    回环地址的 postgres 串时才写入 `DATABASE_URL`。
  - `main.ts`：两个后端工厂（`createPythonBackend` / `createActiveBackend`）从
    `<InstallDir>/.env.db` 读连接串传入；新增 `ensureLocalPostgres()`（每进程只跑一次、
    失败不阻塞启动、失败清缓存以便重试），调用点在 `runEnsureRuntime()` 的 Git Bash 预检
    之后、拉起后端之前。
  - 两个文件里的改动都带 `COCO-PATCH` 注释；配套模块 `apps/desktop/electron/portable-postgres.ts`。
- **为什么**：本机模式下数据层强制 PostgreSQL（`agent/real_estate_db.py` 缺少
  `DATABASE_URL` 时直接拒绝初始化，禁止回退 sqlite）。官方桌面版没有数据库这一环，
  所以要自己带一个：脚本负责装/跑，Electron 负责把连接串与 `pgsql\bin` 递给后端。
  顺序要求：数据库就绪 → 后端拿到 `DATABASE_URL` → 建表 → 网关启动。
- **上游变了怎么办**：这两个文件官方一直在动（`main.ts` 是 god file，长期在拆 sibling）。
  同步后先跑 `scripts/check_coco_hooks.py`，第 17/18 项会指认丢失；恢复时按上面的语义
  在新代码里重做（`ensureLocalPostgres()` 必须插在「后端进程被拉起之前」的那个位置），
  不要机械 apply 这个 patch。

### 10 scripts/install.ps1 —— 安装器里的本机数据库阶段
- **改什么**：`$InstallStages` 里新增 `coco-database`（位置：`node-deps` 之后、`path` 之前），
  Worker 是 `Stage-CocoDatabase` → `Install-CocoLocalDatabase`；后者调
  `apps/desktop/scripts/portable-postgres.ps1 -Action setup`，失败即抛（安装器把这一步标红）。
  `COCO_SKIP_LOCAL_DB=1` 可跳过。
- **为什么**：桌面版首启的进度界面由 install.ps1 的 stage 协议驱动（`-Manifest` 给阶段清单、
  `-Stage <name>` 单跑一步）。数据库不成为阶段，用户就看不到「正在准备本机数据库」，
  只会在后端启动时静默等待；而数据层缺少 `DATABASE_URL` 是直接拒绝初始化的。
  顺序必须在依赖之后（阶段里会顺带建表）、PATH 与网关之前（它们都要读 `.env.db`）。
- **上游变了怎么办**：自检第 19 项盯着（`COCO-PATCH` + `coco-database` + `Stage-CocoDatabase`）。
  官方若重构阶段表，按上面的语义在新结构里重做，别机械 apply。

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

### 08 scripts/sandbox/pick-release-tags.sh —— CI 挑标签的正则
- **改什么**：把只认日期式 `vYYYY.M.D` 的 grep 正则，放宽为同时认语义化版本
  （`^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9]+)?$`）。
- **为什么**：Coco 的发布标签是 `v0.21.3-1` 这种语义化格式，不是官方的日期式。
  不改这条，继承自官方的 install-e2e 工作流会报 `no release tags found`。
- **上游变了怎么办**：只要 Coco 还用语义化标签，这个放宽就必须保留；
  官方若改了该脚本的挑标签方式，按新方式重新放宽。

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
