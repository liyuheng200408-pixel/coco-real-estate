# Coco（可可）房产助理

> 基于 [Hermes Agent](https://hermes-agent.nousresearch.com) 定制的房产顾问 AI 助手，专为房产中介打造。内置客户管理、智能房源匹配、跟进提醒、数据报告等核心能力，一行命令安装，即装即用。

中文文档见 [README.zh-CN.md](README.zh-CN.md)。

## ✨ 核心功能

| 模块 | 说明 |
|------|------|
| 🎯 客户管理 | S/A/B/C 四级分类，自动计算跟进周期；客户画像管理（预算、户型、区域、装修偏好）；一键添加、查询、更新客户；客户生日管理 |
| 🏠 智能匹配 | 多维度加权评分算法：价格 30% + 户型 25% + 面积 20% + 区域 15% + 装修 10%，自动推荐最合适房源；新房源自动反匹配 S/A 级客户 |
| ⏰ 跟进提醒 | 每日早报（09:00）、午间检查（13:00）、逾期检查（每30分钟）、生日提醒（08:00），S 级客户 2 天内跟进 |
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

```bash
# 1. 安装 Node.js 22（如果还没装）
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
# 2. 验证 Node 版本
node -v # 应该 v22.x
```

然后执行一键安装：

```bash
curl -fsSL https://gitee.com/liyuheng200408/coco-real-estate/raw/master/install.sh -o install.sh && bash install.sh
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

3. 设置 Hermes 后台运行，最常用的是 Gateway（网关服务）：

```bash
# 1. 安装为后台服务
hermes gateway install
# 2. 启动服务
hermes gateway start
```

这样即使关掉终端，Hermes 也会在后台持续运行，飞书消息也能正常收发。

4. 配置模型，这是最关键的一步，用来连接 AI 模型。你需要一个 API Key（DeepSeek API Key 购买：[https://platform.deepseek.com/usage](https://platform.deepseek.com/usage)）：

```bash
hermes model
```

5. 运行配置向导（连接飞书，飞书开放平台：[https://open.feishu.cn/?lang=zh-CN](https://open.feishu.cn/?lang=zh-CN)）：

```bash
hermes setup
```

### 第三步：重启服务并发布应用

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

```bash
cd ~/hermes-agent && source venv/bin/activate && git pull && pip install -e . -q && sudo systemctl restart hermes-agent
```

> 注意：此命令只更新代码与依赖。若更新涉及已有表结构/数据单位变更（如 2026-08 价格单位改元），需先执行 `bash scripts/migrate_price_to_yuan.sh` 迁移旧数据，再重启服务。新增表启动时自动创建，无需处理。

### 服务管理

```bash
sudo systemctl start hermes-agent
sudo systemctl stop hermes-agent
sudo systemctl restart hermes-agent
sudo systemctl status hermes-agent
sudo journalctl -u hermes-agent -n 50 --no-pager
```

### 数据库备份

每日凌晨 2 点自动备份至 `~/backups/real_estate/`，保留 30 天。加密密钥同时自动备份到 `~/backups/real_estate/enc_key.txt`。

> 重要：请把 `enc_key.txt` 密钥文件保存到安全的地方（电脑/U盘/网盘）。密钥丢失将导致客户数据永久无法解密。首次使用机器人时 Coco 也会提醒您备份。

```bash
cd ~/hermes-agent && source venv/bin/activate && python3 scripts/backup_db.py backup
cd ~/hermes-agent && source venv/bin/activate && python3 scripts/backup_db.py list
cd ~/hermes-agent && source venv/bin/activate && python3 scripts/backup_db.py restore --restore-file real_estate_20260101_020000.dump
```

### 服务器迁移

迁移到新服务器时，一条命令完成数据库 + 图片 + 加密密钥恢复：

> 📖 **完整操作手册见 [docs/BACKUP_MIGRATION.md](docs/BACKUP_MIGRATION.md)**（含重装系统、换服务器、单独恢复、FAQ 速查卡）

```bash
# 旧服务器打包（含数据库备份、图片备份、加密密钥）
cd ~/backups/real_estate && tar czf /root/coco_migration.tar.gz *.dump real_estate_images_*.tar.gz enc_key.txt

# 拷贝到新服务器后，一条命令恢复
cd ~/hermes-agent && source venv/bin/activate && python3 scripts/backup_db.py restore_migration --migration-tar /root/coco_migration.tar.gz

# 重启服务，给机器人发"你好"即完成迁移
sudo systemctl restart hermes-agent
```

> 顺序说明：自动恢复数据库 → 图片 → 加密密钥（enc_key.txt 合并进 .env.db），任一步失败即中止并提示。密钥必须先于服务启动恢复，否则旧数据无法解密。

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

```bash
sudo systemctl start postgresql
sudo systemctl status hermes-agent
journalctl -u hermes-agent -n 50 --no-pager
```

### 飞书消息收不到

1. 检查 App ID / App Secret 是否正确（`hermes setup` 重新配置）
2. 确认飞书应用已发布
3. 确认事件订阅配置正确

## 📄 License

MIT License - 基于 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 定制

## 🙏 致谢

- [Nous Research](https://nousresearch.com) - Hermes Agent 原作者
- [Hermes Agent](https://hermes-agent.nousresearch.com) - 基础框架
