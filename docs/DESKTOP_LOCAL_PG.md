# 桌面版「本机模式」的便携 PostgreSQL：接口契约与接入设计

本文件只描述**接口与设计**，不含桌面版代码改动。

- 引导脚本：`apps/desktop/scripts/portable-postgres.ps1`
- Linux 等价验证：`apps/desktop/scripts/tests/portable-postgres-linux-e2e.sh`
  （便携包的下载/解压只在 Windows 发生；「幂等、随机端口、随机口令、只监听回环、
  连接串可用、凭据丢失可恢复」这些逻辑与平台无关，用系统 PG 二进制跑同一个脚本文件来验证）

---

## 一、接口契约（现状约定，脚本必须与之对齐）

### 1.1 `.env.db`

位置：`<HermesHome>\hermes-agent\.env.db`
（Windows 的 HermesHome = `%LOCALAPPDATA%\hermes`，见 `hermes_constants.py:_get_platform_default_hermes_home`；
`scripts/install.ps1` 的默认 `InstallDir` 也是 `$env:LOCALAPPDATA\hermes\hermes-agent`。）

由 `install.sh:setup_database()`（第 310~345 行）在服务器版生成，键与格式如下：

| 键 | 值 | 说明 |
|---|---|---|
| `DB_HOST` | `127.0.0.1` | 服务器版写作 `localhost` |
| `DB_PORT` | 随机/5432 | 本机模式为随机空闲端口 |
| `DB_NAME` | `hermes_agent` | |
| `DB_USER` | `hermes` | 即集群超级用户 |
| `DB_PASSWORD` | 随机 32 位 | 服务器版 `openssl rand -hex 16` |
| `COCO_ENC_KEY` | Fernet 密钥 | 客户手机号/微信加密的唯一钥匙，丢失不可恢复 |
| `DATABASE_URL` | `postgresql://hermes:<pw>@127.0.0.1:<port>/hermes_agent` | **权威连接串** |

补充约定：

- `.env.db` 里还可能有经纪人的其它配置（`COCO_ENABLE_CRON`、`COCO_CHAT_ID`…）——
  本机模式的写入**只改自己管的 6 个键（`DB_*` + `DATABASE_URL`），其余逐行原样保留**；
  `COCO_ENC_KEY` 只在缺失时补一个，已存在绝不覆盖（改坏等于抹掉经纪人自定义，或让旧数据解不开）。
- 文件权限：`install.sh` 用 `chmod 600`；Windows 等价物是去掉继承、只授权当前用户。
- 任何读取方都遵循「环境变量 `DATABASE_URL` > 文件」的优先级。

### 1.2 谁在消费这份契约

| 消费方 | 依赖 | 对便携 PG 的要求 |
|---|---|---|
| `agent/real_estate_db.py:init_real_estate_db()` | `os.getenv('DATABASE_URL')`，**为空即 raise**（2026-08-12 幽灵库事故的防复发机制，禁 sqlite 回退） | 进程环境里必须有 `DATABASE_URL` |
| `scripts/migrate.py` | 环境变量 > `<repo>/.env.db`；PG 方言迁移 | 迁移要在同一个库、同一连接串上跑 |
| `scripts/backup_db.py` | 从 **环境变量或 `~/.hermes/.env.db`** 或 `cwd/.env.db` 取 URL；调 **`pg_dump` / `pg_restore` / `psql`（裸命令名）**，密码走 `PGPASSWORD` | 便携 PG 的 `bin` 必须在后端进程 **PATH** 上 |
| `scripts/healthcheck.py` | 读 `<INSTALL_DIR>/.env.db` 的 `DATABASE_URL` | 同上；其"服务状态"项是 systemd 口径（Linux only） |
| 建表入口 | `python -c "from agent.real_estate_db import init_real_estate_db; init_real_estate_db()"`（`install.sh:setup_tables`）；网关注册链路里 `get_real_estate_db()` 惰性建表 | 建表前后都不需要额外手工步骤 |
| 备份/迁移 | `backup_db.py backup/restore/list/status`、`restore_migration --migration-tar`；`~/backups/real_estate/` + `enc_key.txt` | `pg_dump`/`pg_restore` 版本要能跟上服务器主版本 |

### 1.3 引导脚本自身的接口（桌面版按这个调）

```
pwsh -File portable-postgres.ps1 -Action <setup|start|stop|status|selftest|print-env|fetch|reset-password> [选项]
```

| 选项 | 默认 | 用途 |
|---|---|---|
| `-Action` | `setup` | `setup` = 首次安装 + 幂等"确保在跑"（应用每次启动都可调） |
| `-DataRoot` | `%LOCALAPPDATA%\hermes\pgsql` | 便携 PG 安装根（`bin/lib/share`） |
| `-DataDir` | `%LOCALAPPDATA%\hermes\pgsql-data` | PGDATA |
| `-EnvFile` | `<HermesHome>\hermes-agent\.env.db` | 写连接串的目标 |
| `-PgBinDir` | 空 | 用已有 PG 的 bin（离线内置 / 非 Windows 等价验证） |
| `-ZipPath` / `COCO_PG_ZIP` | 空 | 本地 zip（安装包内置分发，不联网；`COCO_PG_ZIP` 供安装器设环境变量） |
| `COCO_PG_MIRROR` | 空 | 自建镜像前缀（Gitee Release 附件等），排在官方源之前 |
| `-Port` / `-DbUser` / `-DbName` | 0 / `hermes` / `hermes_agent` | 覆盖 |
| `-Json` | 关 | 机器可读输出（`status`/`setup`） |

退出码（桌面版据此给不同提示）：`0` 成功 · `1` 用法 · `2` 下载失败 · `3` 二进制缺失 ·
`4` initdb 失败 · `5` 启动失败 · `6` 数据目录在但凭据丢失 · `7` 自检未通过 · `8` 配置错误 ·
`9` 未预期错误（已包装成可读文本，附位置信息）。

`-Action selftest` 逐项检查并返回 `0/7`，检查项：可执行文件齐全 · `PG_VERSION` 主版本 ·
只监听 `127.0.0.1`（且块外无覆盖）· 端口/状态文件/`DATABASE_URL` 三处自洽 ·
`pg_hba` 仅回环 + scram · 服务可连 · **非回环地址连不上**（只监听回环的实证）·
正确口令可连且错误口令被拒 · 业务库存在 · `.env.db` 权限仅当前用户 ·
`pg_dump` 能连通业务库。

状态文件 `<DataDir>\coco-pg.json`：端口、库名、用户、安装根、版本、时间戳 —— **不放口令**
（口令只在 `.env.db`，单一秘密存放点）。

---

## 二、接入桌面版「本机模式」（设计 + 已落地的接线）

> 状态：**接线已实现**（见 `apps/desktop/electron/portable-postgres.ts` 与
> `backend-env.ts` / `main.ts` 里的 COCO-PATCH 注释）；本文剩余部分仍是设计说明，
> 供改这些代码时对照。

### 2.1 何时跑

1. **首次运行向导**：用户选「我没有服务器 → 本机安装」后，在现有
   `apps/desktop/electron/bootstrap-runner.ts` 驱动的 `install.ps1` 流程里，
   把本机 PG 作为一个 stage 插在**后端 venv 建好之后、网关首次启动之前**：
   - 前后顺序要求：`pg 就绪 → 建表（init_real_estate_db） → 启网关`，
     否则网关起来时 `DATABASE_URL` 还没写，会撞上「无 DATABASE_URL 即 raise」。
2. **每次应用启动**：调 `-Action setup`（幂等：已在跑就原样返回，端口/口令都不动）。
   失败不要直接弹"无法启动"，先按退出码分流（见 2.5）。

### 2.2 环境注入（两个必须点，均已实现）

- `buildDesktopBackendPath()` 现在会带上 `%LOCALAPPDATA%\hermes\pgsql\bin`
  （函数 `hermesManagedPostgresPathEntries()`）。位置：Hermes 自带的 node 目录与 venv
  之后、**继承来的 PATH 之前** —— 既不打乱官方顺序（上游测试盯着），又能压过系统里
  可能存在的另一个 PostgreSQL（`pg_dump` 大版本不一致会备份失败）。
- `buildDesktopBackendEnv()` 新增可选参数 `databaseUrl`，只在**回环地址**的
  postgres 连接串时才写入 `DATABASE_URL`；`main.ts` 的两个后端工厂
  （`createPythonBackend` / `createActiveBackend`）都从 `<InstallDir>\.env.db` 读取后传入。
  **不在 Electron 侧自己拼连接串** —— 端口会因冲突漂移，`.env.db` 是唯一权威。

启动顺序（已接进 `runEnsureRuntime()`，在 Git Bash 预检之后、拉起后端之前）：
数据库就绪 → 后端进程拿到 `DATABASE_URL` → 建表（后端首次工具调用）→ 网关启动。
准备失败**不阻塞**启动：只记日志，让后端给出「未配置 DATABASE_URL，拒绝初始化数据库」
的明确报错，同时清掉缓存以便用户修好网络后重试。

### 2.3 进程生命周期

- 集群由 `pg_ctl` 拉起，是**独立于 Electron 的常驻进程**：Electron 崩了/被关掉，
  Coco 的飞书网关仍然在线（这正是产品要求：桌面版只是外壳，机器人在后台值守）。
- 因此 **应用退出时不要 kill postgres**；只提供显式「停止本机服务」入口
  （`-Action stop`，`pg_ctl stop -m fast`，不丢数据）。
- 电脑关机 = 机器人下线，向导里必须写明（与现有「本机模式」提示一致）。
- 开机自启（设计）：任务计划程序注册一条用户级登录任务调 `-Action setup`
  （无需管理员）；不要注册成 Windows 服务（要管理员，且违反"不写系统服务"的约束）。

### 2.4 备份 / 恢复

- 备份复用现成脚本：`venv\Scripts\python.exe scripts\backup_db.py backup`
  （PATH 里要有 `pgsql\bin`），产物落 `~/backups/real_estate/*.dump`。
- 首次安装成功后自动建一条**每日备份**计划任务，并把 `enc_key.txt` 一并备份
  （`install.sh` 的既有做法：备份密钥到 `~/backups/real_estate/enc_key.txt`）。
- 恢复：`backup_db.py restore_migration --migration-tar <包>`（顺序：库→图片→密钥），
  恢复完 `-Action setup` 确保服务在跑。
- 「一键导出」给经纪人：把 dump + `enc_key.txt` + 图片打成迁移包，提示存网盘
  （本机模式下数据在用户电脑上，备份是用户自己的责任边界）。

### 2.5 失败时的用户提示（文案落点）

文案在 `apps/desktop/src/i18n/zh.ts`，按退出码分流到既有区块：

| 退出码 | 落点 | 建议文案（中文，可直接用） |
|---|---|---|
| `2` 下载失败 | `failure.description` + 块内新增 hint | 「本机数据库组件下载失败。请检查网络后重试；若长期失败，可改用连接服务器模式。」（附「重试」按钮 = 重跑 setup） |
| `3` 二进制缺失 | 同上 | 「本机数据库组件不完整，请点『修复安装』重新补齐。」 |
| `4`/`5` initdb/启动失败 | `failure.description` + 「打开日志」 | 「本机数据库无法启动。请点『打开日志』把最后 20 行发给我们。」（日志：`%LOCALAPPDATA%\hermes\pgsql-data\coco-postgres.log`） |
| `6` 凭据丢失 | 新提示（不要走「无法启动」） | 「检测到已有数据库但凭据文件缺失。请从备份恢复 `.env.db`，或点『重置口令』（数据不会丢）。」 |
| `7` 自检未通过 | `failure.description` | 「本机数据库自检未通过（明细见日志）。为避免数据错乱，已停止启动机器人。」 |
| 端口被占用 | 无需提示（自动换端口并同步 `.env.db`） | — |

另有 `setupChoice*` / `localStartUnavailable`（`zh.ts` 约 3427 行）区块：本机模式入口处的
前置说明建议写「本机模式会在你的电脑上运行数据库，**电脑关机时机器人不在线**；
不需要管理员权限，数据全部保存在本机用户目录」。

### 2.6 安全边界（保持不变的口径）

只监听 `127.0.0.1`（IPv4 回环；**不监听 `::1`**，避免 `localhost` 解析到 IPv6 造成连不上）；
`pg_hba.conf` 只放行 `127.0.0.1/32` 且强制 `scram-sha-256`（无 trust、无 LAN、无公网）；
口令 32 位随机、只存 `.env.db`（限当前用户可读）、状态文件里不放口令；
`unix_socket_directories = ''`（不额外开 unix socket）；
体积最小化：便携包只解 `bin/lib/share`（119.7MB，而非 906MB），
不注册系统服务、不需要管理员权限。

---

## 三、平台相关的部分（Windows 真机才能验）

跑法（两种，任选）：

```powershell
# 用户真机：一条命令跑完并生成报告，把报告发回即可
pwsh -File apps\desktop\scripts\tests\portable-postgres-windows-selfcheck.ps1
```

```bash
# CI 真机（GitHub Actions 的 windows-latest，手动触发，不自动跑）
gh workflow run desktop-local-pg-windows.yml --ref feat/desktop-local-pg
```

覆盖不到、只能真机确认的点：

- 便携 zip 的下载与解压（EDB 发行包）、`initdb.exe`/`pg_ctl.exe` 的真实执行；
- NTFS ACL 收紧（`%LOCALAPPDATA%\hermes\pgsql-data` 与 `.env.db` 只授权当前用户）；
- 管理员账户下 `pg_ctl` 用受限令牌拉起 `postgres.exe`（不需要提权，这是 PG 在 Windows 的既定行为）；
- 任务计划程序自启、与桌面版进程的退出联动；
- `install.ps1` 里本机 PG stage 的接线（当前接线在 `runEnsureRuntime()`，尚未做成独立 stage）。

---

## 四、验证记录（可复跑）

### 4.1 Linux 等价验证（本仓库内可复跑的脚本）

```bash
# 需要：非 root 用户（initdb 拒绝 root）、pwsh 7、系统 PostgreSQL、一个装了
# sqlalchemy/psycopg2-binary/cryptography 的 venv（脚本第 6 步会真的建表）
mkdir -p /tmp/coco-pg-e2e && uv venv /tmp/coco-pg-e2e/venv
uv pip install --python /tmp/coco-pg-e2e/venv/bin/python sqlalchemy psycopg2-binary cryptography
PWSH=pwsh PG_BIN=/usr/lib/postgresql/16/bin WORK=/tmp/coco-pg-e2e \
  bash apps/desktop/scripts/tests/portable-postgres-linux-e2e.sh
```

覆盖：首次安装与连接串自洽 / 幂等（端口·口令·数据目录·数据行都不动）/ 自检 /
端口冲突自动改选并同步 `.env.db` / 凭据丢失报错与 `reset-password` 恢复 /
`status`·`print-env` 机器可读输出 / 停止后重启。

### 4.2 实测结论（本机 Ubuntu 24.04 + PostgreSQL 16.15，同一个脚本文件）

- **60 项断言全通过**（含「非回环地址 `192.3.0.245` 连不上」「错误口令被拒」）。
- 真实 `agent/real_estate_db.py`（sha256 `c9155be2…`）在便携 PG 上建出 **12 张 `re_` 表**。
- 首次安装后 `.env.db` 的 `DATABASE_URL` 可直接被 `psql` 连上（不是只有 Python 能连）。
- 重复 `setup`：端口/口令/连接串不变、`PG_VERSION` 时间戳不变、业务行仍在；
  `postgresql.conf` 的托管块始终只有 1 份（重复写入是替换而非追加）。
- 端口被别的进程占用时自动改选新端口并同步 `.env.db`；再跑一次端口稳定不变。

### 4.3 便携包解出（用真实 338.7MB Windows 发行包验证过筛选逻辑）

- `postgresql-16.4-1-windows-x64-binaries.zip`：22649 项 → **只解出 1627 项 / 119.7MB**；
  `pgAdmin 4`(615.9MB)、`symbols`(155.6MB)、`doc`、`include`、`StackBuilder` 全部被排除。
- 校验函数 `Get-ZipStatus` 的判定顺序：存在 → ≥150MB → zip 魔数 → 目录可读 → 含 `bin/initdb`；
  缓存文件不合格会被删除并重新下载（不会把半截包喂给解压器）。
