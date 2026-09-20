# 桌面版「本机模式」真机验收清单（Windows）

> 用途：桌面版本机模式（本机跑数据库 + 网关）在真实 Windows 上的**整链路验收**。
> 这是目前唯一还没走过一遍的路径：安装包 → 首启装后端 → 本机数据库 → 飞书配对 → 对话落库。
> 逐条打勾；任何一条不过，把「失败时怎么回报」一节要的东西发回来即可（不用自己排查）。

## 0. 拿到安装包

直接下载（大小约 118MB）：

```
https://www.liyuheng.cn/static/dl-6e98b9/Coco-0.21.3-55-win-x64.exe
```

- sha256（下完可核对）：`4a91b68f5c91b427b689cbd7a620710981df01aa34b4df0c7525728cc3dccf84`
- 这个包在构建时钉住了首启要取用的代码 commit（含 2026-09-20 的「首启克隆 Coco 而不是官方
  Hermes」修复）；**换安装包时必须重新构建**，旧包钉的还是旧代码。
- 备用入口：Actions 页面 `Desktop Windows installer` 最近一次成功运行 → Artifacts → `coco-desktop-windows-installer`，
  或 `gh run download <run-id> -n coco-desktop-windows-installer --repo liyuheng200408-pixel/coco-real-estate`

已知前置：**Git for Windows**（官方也要求）。首启 bootstrap 的 `Stage-Git` 会尝试自动装便携 Git 到
`%LOCALAPPDATA%\hermes\git\`；上一版（0.21.3-53）在 Windows 上实测卡在
「Git for Windows is required for Hermes on Windows」——本清单第 3 步专门验这一点。

## 1. 安装

- [ ] 双击安装包：可选安装目录、**不需要管理员权限**（`perMachine:false`）
- [ ] 装完能从开始菜单启动，窗口标题/图标是 Coco（不是 Hermes）

## 2. 首次启动向导

- [ ] 出现模式选择；选「我没有服务器 → 本机安装」
- [ ] 进度里能看到 **Preparing the local database** 这一步（本机数据库阶段）
- [ ] 若卡在 Git：把弹窗原文截图发回（那说明 Stage-Git 没跑通，是已知待修点）

## 3. 本机数据库（装完立刻可查）

在 PowerShell 里跑这一条，它会自己体检并生成报告：

```powershell
pwsh -File "$env:LOCALAPPDATA\hermes\hermes-agent\apps\desktop\scripts\tests\portable-postgres-windows-selfcheck.ps1"
```

- [ ] 报告结论是「全部通过，本机数据库可用」
- [ ] `%LOCALAPPDATA%\hermes\hermes-agent\.env.db` 存在，含 `DATABASE_URL`、`DB_PASSWORD`、`COCO_ENC_KEY`
- [ ] 库只监听本机：`netstat -ano | findstr LISTENING | findstr 127.0.0.1` 能看到那个随机端口
- [ ] `%LOCALAPPDATA%\hermes\pgsql-data\` 是数据目录（关掉桌面版它仍然在，重开自动接上）

## 4. 每日备份（本机模式唯一的安全网）

- [ ] `schtasks /Query /TN Coco-LocalDatabase-Backup` 能查到任务
- [ ] `%USERPROFILE%\backups\real_estate\` 里有 `*.dump`、`enc_key.txt`、`env.db.bak`
- [ ] 手动再跑一次备份不报错：
      `pwsh -File "$env:LOCALAPPDATA\hermes\hermes-agent\apps\desktop\scripts\local-backup.ps1" -Action run`

## 5. 部署体检

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" "$env:LOCALAPPDATA\hermes\hermes-agent\scripts\healthcheck.py"
```

- [ ] 第 [2] 项报的是**本机数据库在运行**（不是 systemd 那种报错）
- [ ] 第 [5] 项数据库连接正常
- [ ] 输出里不出现 `systemctl` / `journalctl` / `timedatectl`

## 6. 飞书端到端（业务闭环）

- [ ] 在向导里配好模型（API Key）与飞书（App ID/Secret）
- [ ] 首次在飞书给机器人发消息 → 收到配对码 → 在服务器/本机执行 `hermes pairing approve feishu <码>`
- [ ] 给 Coco 发「登记客户：张先生，预算300万，想买美兰区3室」→ 回复成功
- [ ] 立刻查库确认**真的落库**（回复成功 ≠ 数据在库，这是历史事故的教训）：
      ```powershell
      $env:DATABASE_URL = (Select-String -Path "$env:LOCALAPPDATA\hermes\hermes-agent\.env.db" -Pattern '^DATABASE_URL=(.+)$').Matches.Groups[1].Value
      & "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" -c "from agent.real_estate_db import init_real_estate_db; db=init_real_estate_db(); print(db.get_stats())"
      ```
- [ ] 关掉桌面版再重开：会话/数据仍在，机器人恢复在线
- [ ] 明确告知用户的行为：**电脑关机 = 机器人离线**（数据在本地，重开即恢复）

## 7. 失败时怎么回报（不用自己排查）

按顺序给这三样即可：

1. 自检报告：`%LOCALAPPDATA%\hermes\pgsql-logs\selfcheck-*.txt`
2. 数据库日志：`%LOCALAPPDATA%\hermes\pgsql-data\coco-postgres.log`
3. 桌面版日志：`%LOCALAPPDATA%\hermes\logs\desktop.log`（最后 100 行）

如果是「安装/启动阶段」失败，再补一张弹窗截图（文案与退出码是定位关键）。

## 8. 已知限制（验收时不必当故障）

- 本机模式数据在用户电脑上，**关机/休眠期间机器人不在线**（向导里已写明）。
- 只监听 `127.0.0.1`，局域网其它机器连不上（设计如此）。
- macOS 暂无本机模式（二期）。
- 「连接服务器」模式与本机模式可在同一台机器切换（本清单不覆盖该切换路径）。
