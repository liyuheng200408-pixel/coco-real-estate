<p align="center">
  <img src="assets/banner.png" alt="Coco Real Estate Agent" width="100%">
</p>

# Coco（可可）- 房产助理 ☤
<p align="center">
  <a href="https://gitee.com/liyuheng200408/coco-real-estate">Coco 房产助理</a>
</p>

**基于 [Hermes Agent](https://hermes-agent.nousresearch.com) 定制的房产顾问 AI 助手。**

Coco（可可）是专为房产中介打造的 AI 第二大脑，内置客户管理、智能房源匹配、跟进提醒等核心能力。一行命令安装，即装即用。

## ✨ 核心功能

### 🎯 客户管理
- S/A/B/C 四级分类，自动计算跟进周期
- 客户画像管理（预算、户型、区域、装修偏好）
- 一键添加、查询、更新客户

### 🏠 智能匹配
- 多维度加权评分算法
- 价格（30%）+ 户型（25%）+ 面积（20%）+ 区域（15%）+ 装修（10%）
- 自动推荐最合适的房源

### ⏰ 跟进提醒
- 每日早报（09:00）
- 午间检查（13:00）
- 自定义提醒

### 📊 数据报告
- 客户统计
- 房源统计
- 逾期跟进提醒

## 🚀 一键安装

```bash
curl -fsSL https://gitee.com/liyuheng200408/coco-real-estate/raw/master/install.sh -o install.sh && bash install.sh
```

安装脚本会自动：
1. 检测系统环境（Ubuntu/CentOS/Mac）
2. 安装 Python、PostgreSQL
3. 克隆代码
4. 配置数据库
5. 交互式配置飞书凭证
6. 启动服务

## 📋 手动安装

### 环境要求
- Python 3.10+
- PostgreSQL 12+

### 步骤

```bash
# 1. 克隆
git clone https://gitee.com/liyuheng200408/coco-real-estate.git
cd coco-real-estate

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置
cp .env.example .env
# 编辑 .env 填入你的配置

# 5. 创建数据库
psql -U postgres -c "CREATE DATABASE hermes_agent;"

# 6. 启动
python main.py
```

## 🐳 Docker 部署

```bash
# 1. 配置 .env
cp .env.example .env
# 编辑 .env

# 2. 启动
docker-compose up -d

# 3. 查看日志
docker-compose logs -f
```

## ⚙️ 配置说明

编辑 `.env` 文件：

```bash
# OpenAI API Key
OPENAI_API_KEY=sk-xxx

# 飞书应用凭证
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx

# 数据库
DATABASE_URL=postgresql://user:***@localhost:5432/hermes_agent
```

## 🔧 常用命令

### 更新版本
```bash
cd ~/hermes-agent && source venv/bin/activate && git pull && pip install -e . -q && sudo systemctl restart hermes-agent
```

**如果提示冲突，运行这条强制更新：**
```bash
cd ~/hermes-agent && git checkout . && git clean -fd && git pull && pip install -e . -q && sudo systemctl restart hermes-agent
```

### 服务管理
```bash
sudo systemctl start hermes-agent    # 启动
sudo systemctl stop hermes-agent     # 停止
sudo systemctl restart hermes-agent  # 重启
sudo systemctl status hermes-agent   # 状态
sudo journalctl -u hermes-agent -n 50 --no-pager  # 日志
```

### 更换模型
```bash
cd ~/hermes-agent
source venv/bin/activate
hermes model  # 交互式选择
```

### 支持的模型厂商
| 厂商 | 配置 |
|------|------|
| 小米 MiMo | `provider: xiaomi` |
| OpenAI | `provider: openai` |
| OpenRouter | `provider: openrouter` |
| DeepSeek | `provider: deepseek` |
| 阿里通义 | `provider: qwen` |
| 本地模型 | `provider: ollama` |

### 配置修改
```bash
nano ~/.hermes/config.yaml  # 编辑配置
nano ~/hermes-agent/.env    # 编辑环境变量
sudo systemctl restart hermes-agent  # 重启生效
```

## 📁 项目结构

```
coco-real-estate/
├── main.py                    # 启动入口
├── run_agent.py               # Agent 核心（Hermes）
├── install.sh                 # 一键安装脚本
├── agent/
│   ├── real_estate_db.py      # 房产数据库模块
│   ├── real_estate_prompt.py  # Coco 系统提示词
│   └── system_prompt.py       # 系统提示词（已注入房产能力）
├── tools/
│   ├── real_estate_customer.py  # 客户管理工具（6个）
│   ├── real_estate_property.py  # 房源管理工具（5个）
│   └── real_estate_followup.py  # 跟进管理工具（6个）
├── skills/
│   └── real_estate/SKILL.md    # 房产技能文档
├── toolsets.py                 # 工具集定义（已注册 real_estate）
└── gateway/                    # 飞书适配器
```

## 🤖 使用示例

```
你: 帮我添加客户张三，预算300-500万，想买朝阳区三居室
Coco: ✓ 已添加客户张三
     - 📱 手机：138****8001
     - 💰 预算：300-500万
     - 🏠 需求：3室，朝阳区
     - ⭐ 等级：C级（初步接触）

你: 有没有合适的房源推荐给张三？
Coco: 根据张三的需求，为您推荐以下房源：
     1. 望京新城精装三居 - 450万 (匹配度: 85分)

你: 看看今天需要跟进什么
Coco: 📊 每日早报
     - 2位S级客户待跟进
     - 3条今日任务
```

## 📝 常见问题

### 数据库连接失败
```bash
sudo systemctl start postgresql
psql -U postgres -c "CREATE DATABASE hermes_agent;"
```

### 飞书消息收不到
1. 检查 App ID/Secret
2. 确认应用已发布
3. 检查事件订阅配置

## 📄 License

MIT License - 基于 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 定制

## 🙏 致谢

- [Nous Research](https://nousresearch.com) - Hermes Agent 原作者
- [Hermes Agent](https://hermes-agent.nousresearch.com) - 基础框架
