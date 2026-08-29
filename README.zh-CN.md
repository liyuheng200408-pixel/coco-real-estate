# Coco（可可）房产助理

> 基于 [Hermes Agent](https://hermes-agent.nousresearch.com) 定制的房产顾问 AI 助手，专为房产中介打造。内置客户管理、智能房源匹配、跟进提醒、数据报告等核心能力，一行命令安装，即装即用。

## ⚠️ 免责声明

**本项目的定位是个人学习与技术交流**，非商业产品。作者开源本项目仅为分享基于 Hermes Agent 定制行业 AI 助手的思路与实现，不提供任何形式的担保或技术支持。

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
| 🏠 智能匹配 | 多维度加权评分算法：价格 30% + 户型 25% + 面积 20% + 区域 15% + 装修 10%，自动推荐最合适房源；新房源自动反匹配 S/A 级客户 |
| ⏰ 跟进提醒 | 早报/午间检查/逾期检查定时提醒功能（默认关闭，设置 `COCO_ENABLE_CRON=1` 开启：早报 09:00、午间 13:00、逾期每 30 分钟），S 级客户 2 天内跟进 |
| 🏠 带看管理 | 预约带看、记录带看结果、客户反馈、自动 1 小时回访提醒 |
| 📝 成交管理 | 定金→签约→贷款→过户→交房 五阶段状态机，自动推进提醒 |
| 📊 数据报告 | 客户统计、房源统计、逾期跟进提醒、经营周报/月报、竞品对比、客户意向度评分 |
| 💬 话术库 | 自定义话术保存复用，覆盖开场/异议处理/逼定/跟进场景 |
| 🏷 发布助手 | 一键生成朋友圈/贝壳/安居客/58 房源发布文案 |
| 🔐 数据加密 | 客户手机号、微信号等敏感字段 AES 加密存储，密钥自动生成（`.env.db`） |

## 🚀 一键安装与配置

### 第一步：一键安装

这是我本人维护的渠道，最稳定，也最适合中国大陆的网络环境：

SSH 重新连接后，先安装 Node.js 22（如果还没装）：

**安装 Node.js 22 源（如果还没装）：**
```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
```

**安装 Node.js 22：**
```bash
sudo apt install -y nodejs
```

**验证 Node 版本（应显示 v22.x）：**
```bash
node -v
```

然后执行一键安装（按服务器所在地区选一种，每条命令可单独复制）：

**国内服务器（Gitee 源，推荐）：**
```bash
curl -fsSL https://gitee.com/liyuheng200408/coco-real-estate/raw/master/install.sh -o install.sh && bash install.sh
```

**海外服务器（GitHub 源）：**
```bash
curl -fsSL https://raw.githubusercontent.com/liyuheng200408-pixel/coco-real-estate/master/install.sh -o install.sh && bash install.sh
```

这个脚本会自动完成所有安装步骤（检测系统环境、安装依赖、克隆代码、创建数据库、注册服务并启动）。

### 第二步：安装后的配置

安装脚本执行成功后，你需要完成以下配置才能使用 Hermes。

1. 刷新环境变量，为了让 hermes 命令立即生效：

```bash
source ~/.bashrc
```

2. 验证安装，检查 hermes 命令是否可用：

```bash
hermes --version
```

如果能看到版本号（例如 hermes v0.20.0），就说明核心程序安装成功了。

3. 配置模型，这是最关键的一步，用来连接 AI 模型。你需要一个 API Key（DeepSeek API Key 购买：[https://platform.deepseek.com/usage](https://platform.deepseek.com/usage)）：

```bash
hermes model
```

4. 运行配置向导（连接飞书，飞书开放平台：[https://open.feishu.cn/?lang=zh-CN](https://open.feishu.cn/?lang=zh-CN)）：

```bash
hermes setup
```

### 第三步：设置后台运行并重启服务

1. 设置 Hermes 后台运行，最常用的是 Gateway（网关服务）：

**安装为后台服务：**
```bash
hermes gateway install
```

**启动服务：**
```bash
hermes gateway start
```

这样即使关掉终端，Hermes 也会在后台持续运行，飞书消息也能正常收发。

> **部署提示**：一键安装脚本已自动配置网关数据库环境（PostgreSQL）。若手动执行 `hermes gateway install` 后 Coco 回复"添加成功"但查库无数据，说明服务未加载数据库环境——代码已内置防护：未配置 DATABASE_URL 时工具会直接报错而不是静默写入临时文件，按报错提示补环境即可。

2. 重启服务使配置生效：

```bash
hermes gateway restart
```

### 第四步：测试机器人

1. 打开飞书 App，搜索你的机器人名称
2. 发送一条消息（如"你好"）
3. 机器人会回复配对码，在终端执行批准：`hermes pairing approve feishu <配对码>`
4. 批准后再发消息，机器人应该正常回复

## 🔧 常用命令

### 更新版本

一键无损更新（备份 → 拉码 → 装依赖 → 跑迁移 → 自检 → 重启服务）：

```bash
cd ~/hermes-agent && source venv/bin/activate && git pull && bash scripts/update.sh
```

> 固定更新命令：前面的 `git pull` 会把 `update.sh` 拉下来（老版本也能用），`bash update.sh` 一次完成 备份→拉码→装依赖→跑迁移→健康自检→重启（自动识别真实服务 hermes-gateway/ hermes-agent）。无论本次更新是纯代码改动还是动了表结构，都无损升级，客户数据全程保留——迁移只增不删、事务内失败回滚，绝不删改已有数据。

> 注意：脚本绝不运行 `git clean -fd`（会删 .env.db 与加密密钥，导致旧客户数据无法解密）。重启自动识别正在运行的服务（hermes-gateway 优先，兼容 hermes-agent）。

### 部署健康自检

安装或更新后，一条命令体检（依赖 / 服务 / 联网搜索后端 / 数据库 / 密钥 / 定时任务）：

```bash
cd ~/hermes-agent && source venv/bin/activate && python3 scripts/healthcheck.py
```

全部 PASS 说明部署健康；FAIL 项会附修复提示。

### 服务管理

**启动服务：**
```bash
sudo systemctl start hermes-agent
```

**停止服务：**
```bash
sudo systemctl stop hermes-agent
```

**重启服务：**
```bash
sudo systemctl restart hermes-agent
```

**查看状态：**
```bash
sudo systemctl status hermes-agent
```

**查看日志（最近 50 行）：**
```bash
sudo journalctl -u hermes-agent -n 50 --no-pager
```

### 数据库备份

安装时已自动设置每日凌晨 2 点备份，备份文件在 `~/backups/real_estate/`，保留 30 天。加密密钥同时自动备份到 `~/backups/real_estate/enc_key.txt`。

> 重要：请把 `enc_key.txt` 密钥文件保存到安全的地方（电脑/U盘/网盘）。密钥丢失将导致客户数据永久无法解密。首次使用机器人时 Coco 也会提醒您备份。

**手动备份：**
```bash
cd ~/hermes-agent && source venv/bin/activate && python3 scripts/backup_db.py backup
```

**查看备份列表：**
```bash
cd ~/hermes-agent && source venv/bin/activate && python3 scripts/backup_db.py list
```

**恢复备份：**
```bash
cd ~/hermes-agent && source venv/bin/activate && python3 scripts/backup_db.py restore --restore-file real_estate_20260101_020000.dump
```

### 服务器迁移

迁移到新服务器时，一条命令完成数据库 + 图片 + 加密密钥恢复：

**旧服务器打包（含数据库/图片/加密密钥）：**
```bash
cd ~/backups/real_estate && tar czf /root/coco_migration.tar.gz *.dump real_estate_images_*.tar.gz enc_key.txt
```

**拷贝到新服务器后一键恢复：**
```bash
cd ~/hermes-agent && source venv/bin/activate && python3 scripts/backup_db.py restore_migration --migration-tar /root/coco_migration.tar.gz
```

**重启服务（发"你好"即完成迁移）：**
```bash
sudo systemctl restart hermes-agent
```

> 顺序说明：自动恢复数据库 → 图片 → 加密密钥（enc_key.txt 合并进 .env.db），任一步失败即中止并提示。密钥必须先于服务启动恢复，否则旧数据无法解密。

### 重装系统完整恢复流程（2026-08-12 实测验证）

以下流程已在真实服务器上重装系统实测通过（数据完整恢复，healthcheck 全 PASS）。**重装会清空服务器所有数据，动手前务必完成前两步。**

**第 1 步：旧服务器备份并打包下载（重装前必做）**

**备份数据库（强制）：**
```bash
cd ~/hermes-agent && source venv/bin/activate && python3 scripts/backup_db.py backup --force
```

**确认备份文件齐全：**
```bash
cd ~/backups/real_estate && ls -la
```

**打包迁移文件：**
```bash
cd ~/backups/real_estate && tar czf /root/coco_migration.tar.gz *.dump real_estate_images_*.tar.gz enc_key.txt
```

**下载迁移包到本地电脑（重装后服务器没数据了，务必下载）：**
```bash
scp root@服务器IP:/root/coco_migration.tar.gz ~/Desktop/
```

**第 2 步：重装系统**（云控制台重装 Ubuntu 24.04）

**第 3 步：全新安装**（装完不要手动改任何环境，验证 install.sh 补丁是否生效）

按服务器所在地区选一种命令安装（每条可单独复制）：
```bash
curl -fsSL https://gitee.com/liyuheng200408/coco-real-estate/raw/master/install.sh -o install.sh && bash install.sh
```
或（海外服务器 GitHub 源）：
```bash
curl -fsSL https://raw.githubusercontent.com/liyuheng200408-pixel/coco-real-estate/master/install.sh -o install.sh && bash install.sh
```
装好后按顺序配置：
**激活项目环境：**
```bash
cd ~/hermes-agent && source venv/bin/activate
```

**配置模型 API Key：**
```bash
hermes model
```

**配置飞书机器人：**
```bash
hermes setup
```

**安装并启动后台服务：**
```bash
hermes gateway install && hermes gateway start
```

**第 4 步：恢复数据**

**把迁移包传回服务器（本地电脑执行）：**
```bash
scp ~/Desktop/coco_migration.tar.gz root@服务器IP:/root/
```

**在服务器激活环境：**
```bash
cd ~/hermes-agent && source venv/bin/activate
```

**执行数据恢复：**
```bash
python3 scripts/backup_db.py restore_migration --migration-tar /root/coco_migration.tar.gz
```

**重启网关服务：**
```bash
systemctl --user restart hermes-gateway.service
```

**第 5 步：验证**

```bash
cd ~/hermes-agent && source venv/bin/activate && python3 scripts/healthcheck.py
```

预期：数据库/密钥/备份新鲜度全部 PASS；在飞书给 Coco 发"看下房源统计"，数据完整返回（房源/客户/成交都在，品牌名保留）。

> ⚠️ 若 healthcheck 数据库项 FAIL，说明 gateway 服务未加载数据库环境——这是 2026-08-12 幽灵库事故的复发信号，按报错提示修复环境后重启，不要继续使用。

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

## 📝 常见问题

### 数据库连接失败

**启动 PostgreSQL 数据库：**
```bash
sudo systemctl start postgresql
```

**查看服务状态：**
```bash
sudo systemctl status hermes-agent
```

**查看日志（最近 50 行）：**
```bash
journalctl -u hermes-agent -n 50 --no-pager
```

### 飞书消息收不到

1. 检查 App ID / App Secret 是否正确（`hermes setup` 重新配置）
2. 确认飞书应用已发布
3. 确认事件订阅配置正确

### 机器人不回复

1. `sudo systemctl status hermes-agent` 确认服务在运行
2. `journalctl -u hermes-agent -n 50 --no-pager` 查看报错
3. 确认模型 API Key 有效（`hermes model` 重新配置）

## 📄 License

MIT License - 基于 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 定制

## 🙏 致谢

- [Nous Research](https://nousresearch.com) - Hermes Agent 原作者
- [Hermes Agent](https://hermes-agent.nousresearch.com) - 基础框架
