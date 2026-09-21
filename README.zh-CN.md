# Coco（可可）房产智能体

> 房产顾问智能体，专为房产中介打造。内置客户管理、智能房源匹配、跟进提醒、数据报告等核心能力，一行命令安装，即装即用。

[![Coco AI](https://img.shields.io/github/v/release/liyuheng200408-pixel/coco-real-estate?label=Coco%20AI)](https://github.com/liyuheng200408-pixel/coco-real-estate/releases/latest)

> 🏷️ **当前版本：v0.21.3-68** · [Gitee](https://gitee.com/liyuheng200408/coco-real-estate/releases) · [GitHub](https://github.com/liyuheng200408-pixel/coco-real-estate/releases/tag/v0.21.3-68)

## ⚠️ 免责声明

**本项目的定位是个人学习与技术交流**，非商业产品。作者开源本项目仅为分享行业智能体的实现思路与代码，不提供任何形式的担保或技术支持。

1. **学习用途定位**：本项目默认面向个人学习、技术研究、功能演示场景。若你希望将其用于生产环境（真实客户、真实业务数据），请务必先自行评估风险、完整测试、并做好以下准备，**因使用本软件产生的一切后果由使用者自行承担**。

2. **生产环境风险与数据备份**：应用于生产环境前，请务必：① 亲自完成**全量功能测试**（参考仓库 `docs/TESTING_FEISHU_FULL.md` 的实测清单）；② **定期备份数据**（项目提供 `backup_db.py` 备份工具，请确认自动备份任务真实生效，不要想当然）；③ 妥善保管备份文件。因未备份、误删、重装系统、服务器故障、断电等造成的任何数据丢失，项目方不承担责任。

3. **加密密钥保管**：客户手机号、微信号等敏感字段使用加密密钥（COCO_ENC_KEY）加密存储。**该密钥是解密客户数据的唯一凭证**，一旦丢失或泄露，将导致客户数据永久无法解密。请务必独立备份该密钥，因密钥丢失造成的数据不可读，项目方不承担责任。

4. **软件按现状提供**：本项目按"现状"（AS-IS）提供，不承诺无缺陷、不保证特定功能完全满足你的需求。AI 模型可能产生错误、幻觉或不准确的信息（例如将未执行的操作描述为已执行），使用时请以实际数据为准。使用过程中出现的任何问题或损失，项目方不承担由此产生的直接或间接责任。

5. **数据准确性**：贷款政策、税费等外部信息具有时效性，Coco 查询到的政策信息仅供参考，请以当地官方机构的最新公告为准。因政策信息滞后或不准确造成的损失，项目方不承担责任。

6. **合规使用**：请确保你的业务操作符合当地法律法规（如个人信息保护法、房地产中介管理规定等）。本项目不构成任何投资建议或法律建议。因违规使用本软件产生的法律后果，由使用者自行承担。

## ✨ 核心功能

| 模块 | 说明 |
|------|------|
| 🎯 客户管理 | S/A/B/C 四级分类，自动计算跟进周期；客户画像管理（预算、户型、区域、装修偏好）；一键添加、查询、更新客户；客户生日管理 |
| 🏠 智能匹配 | 多维度加权评分算法：价格 30% + 户型 25% + 面积 20% + 区域 15% + 装修 10%，自动推荐最合适房源；预算略差一点的房源也能拿到分数，不会被直接埋没；客户反馈过缺陷（采光差、临街吵等）的房源自动降权并在匹配理由中标注；客户指定区域时，区域相符的房源一律排在前面；新房源入库自动反匹配所有活跃客户 |
| 🏠 房源详情 | 问某套房源（给编号或标题均可）一次返回全部字段 + 自动计算的单价（总价÷面积，保留两位小数）+ 业主联系方式 + 图片、调价记录；标题对不上时列出最接近的候选请你确认 |
| ⏰ 跟进提醒 | 定时任务默认关闭；需要时对 Coco 说一句「开启定时任务」即可（早报 09:00 / 午间检查 13:00 / 逾期提醒每 30 分钟）。S 级客户 2 天内跟进 |
| 🏠 带看管理 | 预约带看、记录带看结果、客户反馈、自动 1 小时回访提醒 |
| 📝 成交管理 | 定金→签约→贷款→过户→交房 五阶段状态机，自动推进提醒 |
| 📊 数据报告 | 客户统计、房源统计、逾期跟进提醒、经营周报/月报、竞品对比、客户意向度评分 |
| 💬 话术库 | 自定义话术保存复用，覆盖开场/异议处理/逼定/跟进场景 |
| 🏷 发布助手 | 一键生成朋友圈/贝壳/安居客/58 房源发布文案 |
| 🔐 数据加密 | 客户手机号、微信号等敏感字段 AES 加密存储，密钥自动生成（`.env.db`） |

## 🚀 一键安装与配置

### 第一步：一键安装

SSH 重新连接后，按顺序执行：

**前置条件**：只需一台 Linux 服务器（Ubuntu 系统，带 sudo 权限）并能联网，其余依赖由安装脚本自动处理：

- PostgreSQL（业务数据存储）
- Python 3.11 ~ 3.13（脚本用系统 Python 创建虚拟环境；版本不合适时会自动准备兼容版本）
- Node.js（浏览器工具需要，脚本按 26 → 24 → 22 取最新可用版本）
- ripgrep（快速文件搜索）
- ffmpeg（语音消息的音频格式转换）
- 海报字体与渲染器（约 140MB）

> 你无需手动安装 Python、Node.js、ripgrep、ffmpeg 或 PostgreSQL；安装脚本会检测缺失的依赖并自动安装。只需确认服务器有 sudo 权限、并能正常联网。

**执行一键安装**（按服务器所在位置选一条）：

**国内服务器（Gitee 源）：**
```bash
curl -fsSL https://gitee.com/liyuheng200408/coco-real-estate/raw/master/install.sh -o install.sh && bash install.sh
```

**海外服务器（GitHub 源）：**
```bash
curl -fsSL https://raw.githubusercontent.com/liyuheng200408-pixel/coco-real-estate/master/install.sh -o install.sh && bash install.sh
```

这个脚本会自动完成所有安装步骤（检测系统环境、安装依赖、克隆代码、创建数据库、注册服务并启动）。

### 第二步：安装后的配置

安装脚本执行成功后，你需要完成以下配置才能使用 Coco。

**1. 刷新环境变量**：

```bash
source ~/.bashrc
```

**2. 验证安装**：

```bash
coco version
```

如果能看到版本号（例如 hermes v0.21.3），就说明核心程序安装成功了。

**3. 配置模型**。你需要一个 API Key（DeepSeek API Key 购买：[https://platform.deepseek.com/usage](https://platform.deepseek.com/usage)）：

```bash
coco model
```

**4. 配置飞书**（飞书开放平台：[https://open.feishu.cn/?lang=zh-CN](https://open.feishu.cn/?lang=zh-CN)）：

```bash
coco setup
```

**5. 重启服务**：

```bash
coco restart
```

### 第三步：测试智能体

**1. 打开飞书 App**，搜索你的智能体名称

**2. 发送一条消息**（如"你好"）

**3. 智能体会回复配对码**，在终端执行批准：`coco pairing approve feishu <配对码>`

**4. 批准后再发消息**，智能体应该正常回复

## 🔧 常用命令

### 更新

使用单条命令更新至最新版本：

```bash
coco update
```

> 更新只用这条命令。**不要用 `install.sh` 更新**（它会重建安装目录，清掉数据库密钥与图片缓存），**也不要直接跑 `hermes update`**（官方更新会重置你手改过的代码）。

> 更新会自动备份，客户数据全程保留，不会删除你的加密密钥。

### 查看版本

**查看版本：**
```bash
coco version
```
输出形如：Coco v0.21.3-68。

**查看全部可用命令：**
```bash
coco help
```
列出 version / check / backup / uninstall / help。

注意：想单独查底层框架版本可用 `coco cli --version`。

### 服务管理

> 定时任务如需在重装/重启后自动开启（无需每天手动开），可在服务器的 `.env.db` 里加一行 `COCO_ENABLE_CRON=1` 再重启服务。

**启动服务：**
```bash
coco start
```

**停止服务：**
```bash
coco stop
```

**重启服务：**
```bash
coco restart
```

**查看状态：**
```bash
coco status
```

**查看日志（最近 50 行）：**
```bash
coco logs
```


### 数据库备份

安装时已自动设置每日凌晨 2 点备份，备份文件在 `~/backups/real_estate/`，保留 30 天。加密密钥同时自动备份到 `~/backups/real_estate/enc_key.txt`。

> 重要：请把 `enc_key.txt` 密钥文件保存到安全的地方（电脑/U盘/网盘）。密钥丢失将导致客户数据永久无法解密。首次使用智能体时 Coco 也会提醒您备份。

**手动备份：**
```bash
coco backup
```

**查看备份列表：**
```bash
coco backups
```

**查看备份文件**（`.dump` 数据库 / `.tar.gz` 图片 / `enc_key.txt` 密钥）：
```bash
ls -la ~/backups/real_estate/
```

**在服务器上打包：**
```bash
( cd ~/backups/real_estate && tar czf ~/coco_backup_$(date +%Y%m%d).tar.gz ./*.dump ./*.tar.gz ./enc_key.txt )
```

**在你自己的电脑上下载：**
```bash
scp <用户名>@<服务器IP>:~/coco_backup_*.tar.gz ~/Desktop/
```

### 服务器迁移

迁移到新服务器时，一条命令完成数据库 + 图片 + 加密密钥恢复：

**旧服务器打包（含数据库/图片/加密密钥）：**
```bash
( cd ~/backups/real_estate && tar czf /root/coco_migration.tar.gz ./*.dump ./*.tar.gz ./enc_key.txt )
```

**拷贝到新服务器后一键恢复：**
```bash
coco restore --migration /root/coco_migration.tar.gz
```

**重启服务（发"你好"即完成迁移）：**
```bash
coco restart
```

> 顺序说明：自动恢复数据库 → 图片 → 加密密钥（enc_key.txt 合并进 .env.db），任一步失败即中止并提示。密钥必须先于服务启动恢复，否则旧数据无法解密。

### 恢复

**从某个数据库备份恢复**（备份文件名用上面的 `ls` 查看）：
```bash
coco restore --file real_estate_20260101_020000.dump
```

**从整机迁移包恢复**（数据库 + 图片 + 加密密钥，顺序为数据库 → 图片 → 密钥）：
```bash
coco restore --migration /root/coco_migration.tar.gz
```

**恢复后重启服务：**
```bash
coco restart
```

**体检核对**（数据库 / 密钥 / 备份新鲜度）：
```bash
coco check
```

### 卸载

**选择卸载程度**（1 保留数据 / 2 卸载并清理状态 / 3 彻底清理），输入 yes 确认：
```bash
coco uninstall
```

- 1、2 档会在动手前自动备份数据库与加密密钥，并打印备份包路径与下载命令；3 档（彻底清理，含数据库）不备份，如需备份请先执行 `coco backup`。

### 重装系统完整恢复流程

**重装会清空服务器所有数据，动手前务必完成前两步。**

**第 1 步：旧服务器备份并打包下载（重装前必做）**

**备份数据库（强制）：**
```bash
coco backup --force
```

**确认备份文件齐全：**
```bash
ls -la ~/backups/real_estate/
```

**打包迁移文件：**
```bash
( cd ~/backups/real_estate && tar czf /root/coco_migration.tar.gz ./*.dump ./*.tar.gz ./enc_key.txt )
```

**下载迁移包到本地电脑（重装后服务器没数据了，务必下载）：**
```bash
scp root@服务器IP:/root/coco_migration.tar.gz ~/Desktop/
```

**第 2 步：重装服务器系统**

在云服务器控制台选择「重装系统」，镜像选 Ubuntu 24.04（或 26.04），确认执行。这一步会把服务器清空，恢复成一台全新的机器。

推荐 Ubuntu **24.04.4 LTS 或 26.04.1 LTS**。

**第 3 步：在服务器上安装 Coco**

按文档开头的「一键安装与配置」章节完成安装与配置。

**第 4 步：恢复数据**

**把迁移包传回服务器（本地电脑执行）：**
```bash
scp ~/Desktop/coco_migration.tar.gz root@服务器IP:/root/
```

**执行数据恢复：**
```bash
coco restore --migration /root/coco_migration.tar.gz
```

**重启服务：**
```bash
coco restart
```

**第 5 步：验证**

```bash
coco check
```

预期：数据库/密钥/备份新鲜度全部 PASS；在飞书给 Coco 发"看下房源统计"，数据完整返回（房源/客户/成交都在，品牌名保留）。

## 📁 项目结构

```
coco-real-estate/
├── install.sh                    # 一键安装脚本
├── run_agent.py                  # Agent 核心（Hermes）
├── cli.py                        # 命令行入口
├── agent/
│   ├── real_estate_db.py         # 房产数据库模块（PostgreSQL）
│   ├── real_estate_prompt.py     # Coco 系统提示词
│   ├── prompt_builder.py         # 身份注入（Coco）
│   └── system_prompt.py          # 系统提示词（已注入房产能力）
├── tools/
│   ├── real_estate_customer.py     # 客户管理工具
│   ├── real_estate_property.py     # 房源管理工具
│   ├── real_estate_followup.py     # 跟进管理工具
│   ├── real_estate_analytics.py    # 数据统计工具
│   ├── real_estate_calculator.py   # 计算工具
│   ├── real_estate_communication.py # 沟通工具
│   └── real_estate_policy.py       # 政策工具
├── skills/
│   └── real_estate/SKILL.md     # 房产技能文档
├── scripts/
│   └── backup_db.py             # 数据库备份脚本（pg_dump）
├── toolsets.py                  # 工具集定义（已注册 real_estate）
└── plugins/platforms/feishu/    # 飞书适配器
```

## 🤖 使用示例

```
你: 帮我添加客户张三，预算300-500万，想买朝阳区三居室
Coco: 已添加客户张三
     - 手机：138****8001
     - 预算：300-500万
     - 需求：3室，朝阳区
     - 等级：C级（初步接触）

你: 有没有合适的房源推荐给张三？
Coco: 根据张三的需求，为您推荐以下房源：
     1. 望京新城精装三居 - 450万 (匹配度: 85分)

你: 看看今天需要跟进什么
Coco: 每日早报
     - 2位S级客户待跟进
     - 3条今日任务
```

添加客户、推荐房源、跟进提醒，全部在飞书对话里完成。

## 📝 常见问题

### 数据库连接失败

**启动 PostgreSQL 数据库：**
```bash
sudo systemctl start postgresql
```

**查看服务状态：**
```bash
coco status
```

**查看日志（最近 50 行）：**
```bash
coco logs
```

### 飞书消息收不到

1. 检查 App ID / App Secret 是否正确（`coco setup` 重新配置）
2. 确认飞书应用已发布
3. 确认事件订阅配置正确

### 智能体不回复

1. `coco status` 确认服务在运行
2. `coco logs` 查看报错
3. 确认模型 API Key 有效（`coco model` 重新配置）

## 📄 License

MIT License - 基于 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 定制

## 🙏 致谢

- [Nous Research](https://nousresearch.com) - Hermes Agent 原作者
- [Hermes Agent](https://hermes-agent.nousresearch.com) - 基础框架
