# Coco（可可）房产助理

> 基于 [Hermes Agent](https://hermes-agent.nousresearch.com) 定制的房产顾问 AI 助手，专为房产中介打造。内置客户管理、智能房源匹配、跟进提醒、数据报告等核心能力，一行命令安装，即装即用。

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

> **⚠️ 部署提示（重要）**：`hermes gateway install` 生成的用户服务默认不带数据库环境变量，会导致房产数据写入本地 sqlite 而非 PostgreSQL（表现为 Coco 回复"添加成功"但查库没有数据）。一键安装脚本已自动预置补丁，无需手动处理；如果你手动执行 `hermes gateway install`，请确认存在以下补丁文件（不存在则手动创建）：
>
> ```bash
> # 确认补丁文件存在（install.sh 会自动生成）
> cat ~/.config/systemd/user/hermes-gateway.service.d/override.conf
> # 预期输出：
> # [Service]
> # EnvironmentFile=/root/hermes-agent/.env.db
> #
> # 如果文件不存在，手动创建：
> mkdir -p ~/.config/systemd/user/hermes-gateway.service.d
> printf '[Service]\nEnvironmentFile=/root/hermes-agent/.env.db\n' > ~/.config/systemd/user/hermes-gateway.service.d/override.conf
> systemctl --user daemon-reload
> systemctl --user restart hermes-gateway.service
> ```

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

> 注意：更新命令已移除 `git clean -fd`（会删除数据库和配置，勿手动执行）。

### 部署健康自检

安装或更新后，一条命令体检（依赖 / 服务 / 联网搜索后端 / 数据库 / 密钥 / 定时任务）：

```bash
cd ~/hermes-agent && source venv/bin/activate && python3 scripts/healthcheck.py
```

全部 PASS 说明部署健康；FAIL 项会附修复提示。

### 服务管理

```bash
sudo systemctl start hermes-agent    # 启动
sudo systemctl stop hermes-agent     # 停止
sudo systemctl restart hermes-agent  # 重启
sudo systemctl status hermes-agent   # 状态
sudo journalctl -u hermes-agent -n 50 --no-pager  # 日志
```

### 数据库备份

安装时已自动设置每日凌晨 2 点备份，备份文件在 `~/backups/real_estate/`，保留 30 天。加密密钥同时自动备份到 `~/backups/real_estate/enc_key.txt`。

> 重要：请把 `enc_key.txt` 密钥文件保存到安全的地方（电脑/U盘/网盘）。密钥丢失将导致客户数据永久无法解密。首次使用机器人时 Coco 也会提醒您备份。

```bash
# 手动备份
cd ~/hermes-agent && source venv/bin/activate && python3 scripts/backup_db.py backup

# 查看备份列表
cd ~/hermes-agent && source venv/bin/activate && python3 scripts/backup_db.py list

# 恢复备份
cd ~/hermes-agent && source venv/bin/activate && python3 scripts/backup_db.py restore --restore-file real_estate_20260101_020000.dump
```

### 服务器迁移

迁移到新服务器时，一条命令完成数据库 + 图片 + 加密密钥恢复：

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
sudo systemctl status hermes-agent  # 查看服务状态
journalctl -u hermes-agent -n 50 --no-pager  # 查看日志
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
