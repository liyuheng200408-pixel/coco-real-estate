#!/usr/bin/env bash
#
# Coco（可可）房产智能体 - 一键安装脚本
# 基于 Hermes Agent 定制版
# 用法(国内): curl -fsSL https://gitee.com/liyuheng200408/coco-real-estate/raw/master/install.sh -o install.sh && bash install.sh
# 用法(海外): curl -fsSL https://raw.githubusercontent.com/liyuheng200408-pixel/coco-real-estate/master/install.sh -o install.sh && bash install.sh
# 脚本自动探测网络：Gitee 不通时自动切换 GitHub 源
#
set -euo pipefail

# ==================== 配置 ====================
# 双源配置：Gitee（国内快）+ GitHub（海外稳定），自动切换
GITEE_RAW_URL="https://gitee.com/liyuheng200408/coco-real-estate/raw/master/install.sh"
GITEE_REPO_URL="https://gitee.com/liyuheng200408/coco-real-estate.git"
GITEE_ZIP_URL="https://gitee.com/liyuheng200408/coco-real-estate/repository/archive/master.zip"
GITHUB_REPO_URL="https://github.com/liyuheng200408-pixel/coco-real-estate.git"
GITHUB_ZIP_URL="https://github.com/liyuheng200408-pixel/coco-real-estate/archive/refs/heads/master.zip"
INSTALL_DIR="$HOME/hermes-agent"
SERVICE_NAME="hermes-agent"   # 旧版自建系统服务的名字，仅用于安装时清理残留；现统一用官方用户服务 hermes-gateway

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ==================== 系统检测 ====================
check_system() {
    info "检测系统环境..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    else
        error "不支持的操作系统: $OSTYPE"
    fi
    ok "操作系统: $OS"
    
    if command -v apt-get &> /dev/null; then
        PKG_MANAGER="apt"
    elif command -v yum &> /dev/null; then
        PKG_MANAGER="yum"
    elif command -v dnf &> /dev/null; then
        PKG_MANAGER="dnf"
    elif [[ "$OS" == "macos" ]] && command -v brew &> /dev/null; then
        PKG_MANAGER="brew"
    else
        PKG_MANAGER="none"
    fi
    ok "包管理器: $PKG_MANAGER"
}

# ==================== 依赖安装 ====================
install_deps() {
    info "安装系统依赖..."
    case $PKG_MANAGER in
        apt)
            sudo apt-get update -qq
            sudo apt-get install -y -qq python3 python3-pip python3-venv git curl build-essential libpq-dev postgresql postgresql-contrib fonts-wqy-zenhei
            ;;
        yum|dnf)
            sudo $PKG_MANAGER install -y python3 python3-pip git curl gcc gcc-c++ postgresql-server postgresql-devel
            sudo $PKG_MANAGER install -y wqy-zenhei-fonts 2>/dev/null || sudo $PKG_MANAGER install -y google-noto-sans-cjk-fonts 2>/dev/null || true
            sudo postgresql-setup --initdb 2>/dev/null || true
            ;;
        brew)
            brew install python3 git postgresql
            brew install --cask font-wqy-zenhei 2>/dev/null || true
            ;;
        *)
            error "请手动安装: python3, pip3, git, curl, postgresql"
            ;;
    esac
    ok "系统依赖安装完成"
}

# ==================== Python 环境 ====================
setup_python() {
    info "配置 Python 环境..."
    PYTHON_CMD="python3"
    if ! command -v $PYTHON_CMD &> /dev/null; then
        error "Python3 未安装"
    fi
    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
    info "Python 版本: $PYTHON_VERSION"
    
    if [[ ! -d "$INSTALL_DIR/venv" ]]; then
        $PYTHON_CMD -m venv "$INSTALL_DIR/venv"
        ok "虚拟环境创建完成"
    fi
    source "$INSTALL_DIR/venv/bin/activate"
    pip install --upgrade pip -q
    ok "Python 环境配置完成"
}

# ==================== 克隆项目 ====================
# 探测可用的源：优先 Gitee（国内快），不通自动切换 GitHub
probe_source() {
    if timeout 8 git ls-remote "$GITEE_REPO_URL" HEAD >/dev/null 2>&1; then
        echo "gitee"
    elif timeout 8 git ls-remote "$GITHUB_REPO_URL" HEAD >/dev/null 2>&1; then
        echo "github"
    else
        echo "none"
    fi
}

clone_project() {
    info "下载 Coco 房产智能体..."
    if [[ -d "$INSTALL_DIR" ]]; then
        warn "目录已存在，删除后重新下载..."
        rm -rf "$INSTALL_DIR"
    fi
    local src
    src=$(probe_source)
    case "$src" in
        gitee)
            info "使用 Gitee 源..."
            git clone "$GITEE_REPO_URL" "$INSTALL_DIR" 2>/dev/null || {
                warn "git clone 失败，尝试下载 zip..."
                curl -fsSL "$GITEE_ZIP_URL" -o /tmp/coco.zip
                unzip -q /tmp/coco.zip -d /tmp/
                mv /tmp/coco-real-estate-master "$INSTALL_DIR"
                rm -f /tmp/coco.zip
            }
            ;;
        github)
            info "Gitee 不可达，切换 GitHub 源..."
            git clone "$GITHUB_REPO_URL" "$INSTALL_DIR" 2>/dev/null || {
                warn "git clone 失败，尝试下载 zip..."
                curl -fsSL "$GITHUB_ZIP_URL" -o /tmp/coco.zip
                unzip -q /tmp/coco.zip -d /tmp/
                mv /tmp/coco-real-estate-master "$INSTALL_DIR"
                rm -f /tmp/coco.zip
            }
            ;;
        *)
            error "Gitee 和 GitHub 均无法访问，请检查服务器网络后重试"
            ;;
    esac
    cd "$INSTALL_DIR"
    ok "代码下载完成（来源: $src）"
}

# ==================== 安装依赖 ====================
install_packages() {
    info "安装 Python 依赖..."
    source "$INSTALL_DIR/venv/bin/activate"
    
    # 安装 Hermes 核心依赖（使用 pyproject.toml）
    cd "$INSTALL_DIR"
    pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e . -q 2>/dev/null || pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt -q 2>/dev/null || true
    
    # 安装房产专用依赖（含海报生成所需 qrcode；Pillow 为核心依赖由 -e . 安装；
    # ddgs 为 web_search 的免费搜索后端（DuckDuckGo，无需 API Key））
    pip install -i https://pypi.tuna.tsinghua.edu.cn/simple sqlalchemy psycopg2-binary lark-oapi apscheduler qrcode ddgs -q
    
    ok "依赖安装完成"
}

# ==================== 数据库配置 ====================
setup_database() {
    info "配置数据库..."
    DB_PASSWORD=$(openssl rand -hex 16)
    DB_USER="hermes"
    DB_NAME="hermes_agent"
    # 生成敏感字段加密密钥（Fernet，cryptography 已在 install_packages 装好）
    COCO_ENC_KEY=$("$INSTALL_DIR/venv/bin/python" -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || echo "")
    if [[ -z "$COCO_ENC_KEY" ]]; then
        warn "未能生成加密密钥，敏感字段将以明文存储（请确认 cryptography 已安装）"
    else
        ok "敏感字段加密密钥已生成"
    fi
    if [[ "$OS" == "linux" ]]; then
        sudo systemctl enable postgresql
        sudo systemctl start postgresql
    elif [[ "$OS" == "macos" ]]; then
        brew services start postgresql
    fi
    
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';" 2>/dev/null || true
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || true
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" 2>/dev/null || true
    
    cat > "$INSTALL_DIR/.env.db" << EOF
# 数据库配置（自动生成）
DB_HOST=localhost
DB_PORT=5432
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
COCO_ENC_KEY=$COCO_ENC_KEY
DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME
EOF
    chmod 600 "$INSTALL_DIR/.env.db"
    ok "数据库配置完成"
}

# ==================== 交互式配置 ====================
setup_config() {
    info "配置 Coco 房产智能体..."
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Coco（可可）房产智能体 - 配置说明${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo -e "${YELLOW}安装完成后的配置步骤：${NC}"
    echo ""
    echo "1. 重新加载 shell（让 hermes 命令立即可用）:"
    echo "   source ~/.bashrc"
    echo ""
    echo "2. 配置模型（选择厂商并输入 API Key）:"
    echo "   hermes model"
    echo ""
    echo "3. 配置飞书（输入 App ID 和 App Secret）:"
    echo "   hermes setup"
    echo ""
    echo "4. 重启服务，让刚写入的配置生效（重要：网关只在启动时读取配置，配完不重启机器人不会响应）:"
    echo "   hermes gateway restart"
    echo ""
    echo -e "${GREEN}服务已由安装脚本自动注册并启动；完成第 4 步后，智能体会自动连接飞书。${NC}"
    echo ""
    echo "5. 首次在飞书给智能体发消息会收到配对码，在服务器执行以下命令完成配对:"
    echo "   hermes pairing approve feishu <配对码>"
    echo ""
    echo "提示: 若执行第 1 步后仍提示 hermes: command not found，手动补一次命令入口:"
    echo "   sudo ln -sf $INSTALL_DIR/venv/bin/hermes /usr/local/bin/hermes"
    echo ""
    
    # 复制 SOUL.md 身份文件（确保 ~/.hermes 存在）
    mkdir -p "$HOME/.hermes"
    cp "$INSTALL_DIR/SOUL.md" "$HOME/.hermes/SOUL.md" 2>/dev/null || true
    ok "SOUL.md 身份文件已复制"
}

# ==================== 初始化数据库表 ====================
setup_tables() {
    info "初始化数据库表..."
    cd "$INSTALL_DIR"
    set -a
    source "$INSTALL_DIR/.env.db" 2>/dev/null || true
    set +a
    "$INSTALL_DIR/venv/bin/python" -c "from agent.real_estate_db import init_real_estate_db; init_real_estate_db(); print('[Coco] 数据库表创建完成')" || warn "建表失败（首次工具调用时会自动重试）"
}

# ==================== gateway 用户服务环境补丁 ====================
# 背景（2026-08-12 真实事故）：hermes gateway install 生成的用户服务
# hermes-gateway.service 默认不带 EnvironmentFile，进程环境里没有 DATABASE_URL，
# 导致 get_real_estate_db() 静默回退 sqlite（~/.hermes/real_estate.db 幽灵库），
# Coco 回复"添加成功"但 PostgreSQL 查不到。这里预置 drop-in 补丁，
# 声明式文件先创建不碍事，gateway install 生成服务时自动生效。
setup_gateway_env_patch() {
    info "预置 gateway 用户服务数据库环境补丁..."
    local dropin_dir="$HOME/.config/systemd/user/hermes-gateway.service.d"
    local dropin_file="$dropin_dir/override.conf"
    mkdir -p "$dropin_dir"
    cat > "$dropin_file" << EOF
[Service]
EnvironmentFile=$INSTALL_DIR/.env.db
EOF
    chmod 600 "$dropin_file"
    ok "gateway 环境补丁已预置: $dropin_file"
}

# ==================== 安装 gateway 服务（官方用户服务） ====================
# 2026-09-16 改：不再自建系统服务，改用官方 hermes gateway install。
# 原因（老板重装实测）：自建的系统服务并不工作——重启它机器人无响应，重启官方用户服务才响应；
#   且两者并存时会互相抢同一个 bot token，表现为"消息不响应/时好时坏"。
# 官方命令还会一并处理开机自启（loginctl enable-linger）与历史服务清理（幂等，可重复执行）。
setup_service() {
    info "安装 gateway 服务..."
    if [[ "$OS" != "linux" ]] || ! command -v systemctl &> /dev/null; then
        warn "非 systemd 系统，请手动启动: cd $INSTALL_DIR && venv/bin/python -m hermes_cli.main gateway run"
        return
    fi

    # 清理旧版自建的系统服务（与用户服务并存会抢 bot token）
    if systemctl list-unit-files 2>/dev/null | grep -q '^hermes-agent\.service'; then
        sudo systemctl stop hermes-agent 2>/dev/null || true
        sudo systemctl disable hermes-agent 2>/dev/null || true
        sudo rm -f /etc/systemd/system/hermes-agent.service
        sudo systemctl daemon-reload 2>/dev/null || true
        warn "已移除旧版自建系统服务 hermes-agent（统一改用官方用户服务）"
    fi

    local HERMES_CLI="$INSTALL_DIR/venv/bin/hermes"
    if [[ ! -x "$HERMES_CLI" ]]; then
        warn "未找到 $HERMES_CLI，跳过服务安装（可稍后手动执行 hermes gateway install）"
        return
    fi
    # 装用户服务 + 立即启动 + 启用开机自启；失败不阻断安装
    if "$HERMES_CLI" gateway install --start-now --start-on-login 2>&1 | tail -6; then
        ok "gateway 用户服务已安装并启动（开机自启已启用）"
    else
        warn "服务安装异常，可稍后手动执行: hermes gateway install"
    fi
}

# ==================== 启动服务 ====================
start_service() {
    info "启动 Coco 房产智能体..."
    if [[ "$OS" == "linux" ]] && command -v systemctl &> /dev/null; then
        # 修复权限（数据库/密钥文件仅所有者可读写，含 WAL/SHM 伴随文件）
        # 数据库可能落在 HERMES_HOME 或默认 ~/.hermes，两个位置都覆盖
        chmod 600 "$INSTALL_DIR"/state.db* "$INSTALL_DIR"/real_estate.db* "$INSTALL_DIR"/kanban.db* "$INSTALL_DIR"/cron/*.db 2>/dev/null || true
        chmod 600 "$HOME/.hermes"/state.db* "$HOME/.hermes"/real_estate.db* "$HOME/.hermes"/kanban.db* "$HOME/.hermes"/cron/*.db 2>/dev/null || true
        chmod 600 "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.db" "$HOME/.hermes/.env" 2>/dev/null || true
        sleep 2
        # 服务已由 hermes gateway install --start-now 启动，这里只做确认（异常时补一次启动）
        if systemctl --user is-active --quiet hermes-gateway 2>/dev/null; then
            ok "服务运行中（hermes-gateway）"
        elif [[ -x "$INSTALL_DIR/venv/bin/hermes" ]]; then
            warn "服务未在运行，尝试启动..."
            "$INSTALL_DIR/venv/bin/hermes" gateway start 2>&1 | tail -3 || true
        fi
        # 服务启动可能新建数据库文件，再补一次权限（UMask 已兜底 0600）
        chmod 600 "$INSTALL_DIR"/state.db* "$INSTALL_DIR"/real_estate.db* "$HOME/.hermes"/state.db* "$HOME/.hermes"/real_estate.db* 2>/dev/null || true
        # 确保 SOUL.md 身份文件不被覆盖（gateway 首次启动可能生成官方 SOUL.md）
        mkdir -p "$HOME/.hermes"
        cp "$INSTALL_DIR/SOUL.md" "$HOME/.hermes/SOUL.md" 2>/dev/null || true
    else
        cd "$INSTALL_DIR"
        source "venv/bin/activate"
        chmod -R 777 "$INSTALL_DIR" 2>/dev/null || true
        nohup python3 -m hermes_cli.main gateway run > /dev/null 2>&1 &
        ok "服务已在后台启动"
    fi
    
    # 创建 hermes 命令入口（2026-09-16 修：原来缺 sudo 且静默吞错，普通用户装完 hermes 不可用）
    # 照官方的思路：能写 /usr/local/bin 就放那儿；不行退回 ~/.local/bin 并补 PATH；都失败才告警
    HERMES_BIN="$INSTALL_DIR/venv/bin/hermes"
    if [[ -x "$HERMES_BIN" ]]; then
        LINKED=0
        if [[ -w /usr/local/bin ]] && ln -sf "$HERMES_BIN" /usr/local/bin/hermes 2>/dev/null; then
            ok "hermes 命令已就绪：/usr/local/bin/hermes"
            LINKED=1
        elif command -v sudo >/dev/null 2>&1 && sudo ln -sf "$HERMES_BIN" /usr/local/bin/hermes 2>/dev/null; then
            ok "hermes 命令已就绪：/usr/local/bin/hermes"
            LINKED=1
        fi
        if [[ $LINKED == 0 ]]; then
            mkdir -p "$HOME/.local/bin"
            if ln -sf "$HERMES_BIN" "$HOME/.local/bin/hermes" 2>/dev/null; then
                ok "hermes 命令已就绪：$HOME/.local/bin/hermes"
                LINKED=1
                if ! grep -qs '\.local/bin' "$HOME/.bashrc" 2>/dev/null; then
                    printf '\n# Coco: hermes 命令所在目录\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.bashrc"
                    ok "已写入 PATH 到 ~/.bashrc（source ~/.bashrc 后生效）"
                fi
            fi
        fi
        if [[ $LINKED == 0 ]]; then
            warn "hermes 命令未能创建，请手动执行: sudo ln -sf $HERMES_BIN /usr/local/bin/hermes"
        fi
    else
        warn "未找到 $HERMES_BIN —— hermes 命令不可用（安装可能未完成）"
    fi

    # 创建 coco 命令入口（查版本号 / 体检 / 备份）：与 hermes 同一套策略
    COCO_BIN="$INSTALL_DIR/scripts/coco.sh"
    if [[ -x "$COCO_BIN" ]]; then
        LINKED=0
        if [[ -w /usr/local/bin ]] && ln -sf "$COCO_BIN" /usr/local/bin/coco 2>/dev/null; then
            ok "coco 命令已就绪：/usr/local/bin/coco（查版本号: coco version）"
            LINKED=1
        elif command -v sudo >/dev/null 2>&1 && sudo ln -sf "$COCO_BIN" /usr/local/bin/coco 2>/dev/null; then
            ok "coco 命令已就绪：/usr/local/bin/coco（查版本号: coco version）"
            LINKED=1
        fi
        if [[ $LINKED == 0 ]]; then
            mkdir -p "$HOME/.local/bin"
            if ln -sf "$COCO_BIN" "$HOME/.local/bin/coco" 2>/dev/null; then
                ok "coco 命令已就绪：$HOME/.local/bin/coco（查版本号: coco version）"
                LINKED=1
            fi
        fi
        if [[ $LINKED == 0 ]]; then
            warn "coco 命令未能创建，请手动执行: sudo ln -sf $COCO_BIN /usr/local/bin/coco"
        fi
    fi
    
    # 创建备份目录并设置定时备份
    mkdir -p ~/backups/real_estate
    chmod 700 ~/backups/real_estate

    # 自动备份加密密钥（防丢失：密钥在 .env.db，单独备份一份到备份目录）
    if [[ -f "$INSTALL_DIR/.env.db" ]] && grep -q "COCO_ENC_KEY=" "$INSTALL_DIR/.env.db"; then
        grep "^COCO_ENC_KEY=" "$INSTALL_DIR/.env.db" > ~/backups/real_estate/enc_key.txt
        chmod 600 ~/backups/real_estate/enc_key.txt
        ok "加密密钥已备份到 ~/backups/real_estate/enc_key.txt"
    else
        warn "未找到加密密钥，跳过密钥备份"
    fi
    
    # 添加定时备份任务（每天凌晨2点）
    if (crontab -l 2>/dev/null; echo "0 2 * * * cd $INSTALL_DIR && source venv/bin/activate && python3 scripts/backup_db.py backup >> ~/backups/real_estate/backup.log 2>&1") | crontab - 2>/dev/null; then
        ok "定时备份已设置（每天凌晨2点）"
    else
        warn "定时备份设置失败（crontab 不可用），可稍后手动设置"
    fi
}

# ==================== 打印结果 ====================
print_result() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  ✅ Coco（可可）房产智能体安装完成！${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    # 版本号直接读仓库根 VERSION 文件（2026-08-29 加）：以后只改 VERSION，安装终端自动同步，无需再改这里
    COCO_VER=$(cat "$INSTALL_DIR/VERSION" 2>/dev/null | tr -d '[:space:]' || echo "未知")
    # 版本号形如 0.21.3-1：前半段是官方底座，后半段是 Coco 自己的第 N 次发行
    COCO_BASE="${COCO_VER%%-*}"
    echo -e "版本: ${BLUE}v${COCO_VER}${NC}  （官方 Hermes ${COCO_BASE} 定制版）"
    echo -e "安装目录: ${BLUE}$INSTALL_DIR${NC}"
    echo -e "配置文件: ${BLUE}$INSTALL_DIR/.env${NC}"
    echo ""
    echo -e "${YELLOW}常用命令:${NC}"
    echo -e "  启动服务: ${BLUE}hermes gateway start${NC}"
    echo -e "  停止服务: ${BLUE}hermes gateway stop${NC}"
    echo -e "  查看状态: ${BLUE}hermes gateway status${NC}"
    echo -e "  重启服务: ${BLUE}hermes gateway restart${NC}"
    echo -e "  查看日志: ${BLUE}journalctl --user -u hermes-gateway -f${NC}"
    echo ""
    echo -e "${YELLOW}下一步:${NC}"
    echo -e "  1. 在飞书开放平台配置事件订阅 URL"
    echo -e "  2. 测试飞书智能体消息"
    echo -e "  3. 开始使用 Coco 房产智能体！"
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  🔐 重要！请立即备份数据加密密钥！${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo -e "客户手机号、微信号等敏感数据已加密存储。"
    echo ""
    echo -e "您的加密密钥如下（${RED}请用鼠标选中并复制保存${NC}）："
    echo ""
    if [[ -f ~/backups/real_estate/enc_key.txt ]]; then
        echo -e "${GREEN}  $(cat ~/backups/real_estate/enc_key.txt)${NC}"
    else
        echo -e "${GREEN}  COCO_ENC_KEY=（密钥文件未找到，请检查 ~/backups/real_estate/enc_key.txt）${NC}"
    fi
    echo ""
    echo -e "${YELLOW}保存方法（任选一种）：${NC}"
    echo -e "  1. 复制上面的密钥，粘贴保存到自己的电脑记事本 / 网盘"
    echo -e "  2. 下载密钥文件到本地电脑，在电脑上打开终端执行："
    echo -e "     scp root@服务器IP:/root/backups/real_estate/enc_key.txt ~/Desktop/"
    echo -e "     （把 服务器IP 换成您的服务器公网IP，Windows 用户在命令行执行）"
    echo ""
    echo -e "${RED}警告：如果服务器重装或文件丢失，没有这把钥匙，${NC}"
    echo -e "${RED}所有客户手机号、微信号将永远无法解密！${NC}"
    echo ""
    read -p "按回车键确认已了解密钥备份的重要性，继续... " _confirm
    echo ""
    echo -e "${GREEN}========================================${NC}"
}

# ==================== 时区统一（2026-09-19 加） ====================
# 目的：不管云服务商默认给什么时区（阿里云/腾讯云常为 UTC），装完都按北京时间走，
# 否则日志、定时任务（早报 09:00）、业务时间戳都会差 8 小时。
# 想保留服务器原时区：COCO_SKIP_TZ=1 bash install.sh
COCO_TARGET_TZ="Asia/Shanghai"

setup_timezone() {
    info "统一服务器时区为北京时间（$COCO_TARGET_TZ）"
    if [[ "${COCO_SKIP_TZ:-0}" == "1" ]]; then
        warn "已跳过时区设置（COCO_SKIP_TZ=1），服务器保持原时区"
        return 0
    fi
    local cur=""
    if command -v timedatectl >/dev/null 2>&1; then
        cur="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
    fi
    if [[ -z "$cur" && -f /etc/timezone ]]; then
        cur="$(tr -d '[:space:]' < /etc/timezone 2>/dev/null || true)"
    fi
    if [[ "$cur" == "$COCO_TARGET_TZ" ]]; then
        ok "服务器时区已是 $COCO_TARGET_TZ（当前 $(date '+%Y-%m-%d %H:%M %Z')）"
        return 0
    fi
    if command -v timedatectl >/dev/null 2>&1 && sudo timedatectl set-timezone "$COCO_TARGET_TZ" 2>/dev/null; then
        ok "服务器时区已设为 $COCO_TARGET_TZ（当前 $(date '+%Y-%m-%d %H:%M %Z')）"
        return 0
    fi
    # 回退：容器/精简系统没有 timedatectl 时直接写时区文件
    if sudo ln -sf "/usr/share/zoneinfo/$COCO_TARGET_TZ" /etc/localtime 2>/dev/null; then
        echo "$COCO_TARGET_TZ" | sudo tee /etc/timezone >/dev/null 2>&1 || true
        ok "服务器时区已设为 $COCO_TARGET_TZ（当前 $(date '+%Y-%m-%d %H:%M %Z')）"
        return 0
    fi
    warn "时区设置失败（可能需要 sudo 权限）"
    echo "     手动修复：sudo timedatectl set-timezone $COCO_TARGET_TZ"
}

# ==================== Coco 标准运行时配置（2026-09-19 加） ====================
# 轮次 500 / 压缩阈值 0.8 / 保留最近 40 条 / 网关卫生 5000 / 时区北京时间。
# 显式写进 config.yaml，避免"代码默认值改了但已装实例不生效"或"配置被向导/重装冲掉"。
setup_coco_config() {
    if [[ ! -f "$HOME/.hermes/config.yaml" ]]; then
        info "首次配置向导尚未运行，Coco 标准配置将在向导写入后自动生效"
        return 0
    fi
    if "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/scripts/coco_config_align.py"; then
        ok "Coco 标准运行时配置已对齐（轮次 500 / 压缩阈值 0.8 / 保留最近 40 条 / 时区北京时间）"
    else
        warn "运行时配置对齐未完成，可稍后执行 scripts/update.sh 重试"
    fi
}

# ==================== 海报渲染器与字体（2026-09-19 加） ====================
# 海报要用 librsvg + 中文商用字体才有"专业感"。失败不阻塞安装：海报会回落旧引擎/系统字体。
install_poster_fonts() {
    info "安装海报渲染器与字体（约 140MB，可跳过：COCO_SKIP_FONTS=1）"
    if [[ "${COCO_SKIP_FONTS:-0}" == "1" ]]; then
        warn "已跳过（COCO_SKIP_FONTS=1），海报将使用系统自带字体"
        return 0
    fi
    bash "$INSTALL_DIR/scripts/install_fonts.sh" || warn "字体安装未完成，可稍后重跑 scripts/install_fonts.sh（不影响出图）"
}

# ==================== 主函数 ====================
main() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  🏠 Coco（可可）房产智能体 - 一键安装${NC}"
    echo -e "${BLUE}  基于 Hermes Agent 定制版${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    check_system
    setup_timezone
    install_deps
    install_poster_fonts
    clone_project
    setup_python
    install_packages
    setup_database
    setup_config
    setup_coco_config
    setup_tables
    # 环境补丁必须先于服务安装：用户服务创建时才会带上 EnvironmentFile（防幽灵库）
    setup_gateway_env_patch
    setup_service
    start_service
    print_result
}

main "$@"
