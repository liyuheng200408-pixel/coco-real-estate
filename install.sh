#!/usr/bin/env bash
#
# Coco（可可）房产助理 - 一键安装脚本
# 基于 Hermes Agent 定制版
# 用法: curl -fsSL https://gitee.com/liyuheng200408/coco-real-estate/raw/master/install.sh -o install.sh && bash install.sh
#
set -euo pipefail

# ==================== 配置 ====================
REPO_URL="https://gitee.com/liyuheng200408/coco-real-estate.git"
INSTALL_DIR="$HOME/hermes-agent"
SERVICE_NAME="hermes-agent"

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
            sudo apt-get install -y -qq python3 python3-pip python3-venv git curl build-essential libpq-dev postgresql postgresql-contrib
            ;;
        yum|dnf)
            sudo $PKG_MANAGER install -y python3 python3-pip git curl gcc gcc-c++ postgresql-server postgresql-devel
            sudo postgresql-setup --initdb 2>/dev/null || true
            ;;
        brew)
            brew install python3 git postgresql
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
clone_project() {
    info "下载 Coco 房产助理..."
    if [[ -d "$INSTALL_DIR" ]]; then
        warn "目录已存在，删除后重新下载..."
        rm -rf "$INSTALL_DIR"
    fi
    git clone "$REPO_URL" "$INSTALL_DIR" 2>/dev/null || {
        warn "git clone 失败，尝试下载 zip..."
        ZIP_URL="https://gitee.com/liyuheng200408/coco-real-estate/repository/archive/master.zip"
        curl -fsSL "$ZIP_URL" -o /tmp/coco.zip
        unzip -q /tmp/coco.zip -d /tmp/
        mv /tmp/coco-real-estate-master "$INSTALL_DIR"
        rm -f /tmp/coco.zip
    }
    cd "$INSTALL_DIR"
    ok "代码下载完成"
}

# ==================== 安装依赖 ====================
install_packages() {
    info "安装 Python 依赖..."
    source "$INSTALL_DIR/venv/bin/activate"
    
    # 安装 Hermes 核心依赖（使用 pyproject.toml）
    cd "$INSTALL_DIR"
    pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e . -q 2>/dev/null || pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt -q 2>/dev/null || true
    
    # 安装房产专用依赖
    pip install -i https://pypi.tuna.tsinghua.edu.cn/simple sqlalchemy psycopg2-binary lark-oapi apscheduler -q
    
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
    info "配置 Coco 房产助理..."
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Coco（可可）房产助理 - 配置说明${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo -e "${YELLOW}安装完成后的配置步骤：${NC}"
    echo ""
    echo "1. 进入项目目录:"
    echo "   cd $INSTALL_DIR"
    echo ""
    echo "2. 激活虚拟环境:"
    echo "   source venv/bin/activate"
    echo ""
    echo "3. 配置模型（选择厂商和输入API Key）:"
    echo "   hermes model"
    echo ""
    echo "4. 配置飞书（输入 App ID 和 App Secret）:"
    echo "   hermes setup"
    echo ""
    echo "5. 启动服务:"
    echo "   sudo systemctl start hermes-agent"
    echo ""
    echo -e "${GREEN}配置完成后，机器人会自动连接飞书。${NC}"
    echo ""
    
    # 复制 SOUL.md 身份文件
    cp "$INSTALL_DIR/SOUL.md" "$HOME/.hermes/SOUL.md" 2>/dev/null || true
    ok "SOUL.md 身份文件已复制"
}

# ==================== 创建系统服务 ====================
setup_service() {
    info "配置系统服务..."
    if [[ "$OS" == "linux" ]] && command -v systemctl &> /dev/null; then
        sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null << EOF
[Unit]
Description=Coco Real Estate Agent (Hermes)
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env.db
ExecStart=$INSTALL_DIR/venv/bin/python -m hermes_cli.main gateway run
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
Environment=HERMES_HOME=$INSTALL_DIR
Environment=GATEWAY_ALLOW_ALL_USERS=true
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
        sudo systemctl daemon-reload
        sudo systemctl enable $SERVICE_NAME
        ok "Systemd 服务创建完成"
    else
        warn "非 systemd 系统，请手动启动: cd $INSTALL_DIR && python -m hermes_cli.main gateway run"
    fi
}

# ==================== 启动服务 ====================
start_service() {
    info "启动 Coco 房产助理..."
    if [[ "$OS" == "linux" ]] && command -v systemctl &> /dev/null; then
        # 修复权限（数据库/密钥文件仅所有者可读写，含 WAL/SHM 伴随文件）
        # 数据库可能落在 HERMES_HOME 或默认 ~/.hermes，两个位置都覆盖
        chmod 600 "$INSTALL_DIR"/state.db* "$INSTALL_DIR"/real_estate.db* "$INSTALL_DIR"/kanban.db* "$INSTALL_DIR"/cron/*.db 2>/dev/null || true
        chmod 600 "$HOME/.hermes"/state.db* "$HOME/.hermes"/real_estate.db* "$HOME/.hermes"/kanban.db* "$HOME/.hermes"/cron/*.db 2>/dev/null || true
        chmod 600 "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.db" "$HOME/.hermes/.env" 2>/dev/null || true
        sudo systemctl start $SERVICE_NAME
        # 服务启动可能新建数据库文件，再补一次权限（UMask 已兜底 0600）
        sleep 2
        chmod 600 "$INSTALL_DIR"/state.db* "$INSTALL_DIR"/real_estate.db* "$HOME/.hermes"/state.db* "$HOME/.hermes"/real_estate.db* 2>/dev/null || true
        ok "服务已启动"
    else
        cd "$INSTALL_DIR"
        source "venv/bin/activate"
        chmod -R 777 "$INSTALL_DIR" 2>/dev/null || true
        nohup python3 -m hermes_cli.main gateway run > /dev/null 2>&1 &
        ok "服务已在后台启动"
    fi
    
    # 创建 hermes 命令软链接
    ln -sf "$INSTALL_DIR/venv/bin/hermes" /usr/local/bin/hermes 2>/dev/null || true
    ok "hermes 命令已添加到系统路径"
    
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
    (crontab -l 2>/dev/null; echo "0 2 * * * cd $INSTALL_DIR && source venv/bin/activate && python3 scripts/backup_db.py backup >> ~/backups/real_estate/backup.log 2>&1") | crontab -
    ok "定时备份已设置（每天凌晨2点）"
}

# ==================== 打印结果 ====================
print_result() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  ✅ Coco（可可）房产助理安装完成！${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "安装目录: ${BLUE}$INSTALL_DIR${NC}"
    echo -e "配置文件: ${BLUE}$INSTALL_DIR/.env${NC}"
    echo ""
    echo -e "${YELLOW}常用命令:${NC}"
    echo -e "  启动服务: ${BLUE}sudo systemctl start $SERVICE_NAME${NC}"
    echo -e "  停止服务: ${BLUE}sudo systemctl stop $SERVICE_NAME${NC}"
    echo -e "  查看状态: ${BLUE}sudo systemctl status $SERVICE_NAME${NC}"
    echo -e "  查看日志: ${BLUE}sudo journalctl -u $SERVICE_NAME -f${NC}"
    echo -e "  重启服务: ${BLUE}sudo systemctl restart $SERVICE_NAME${NC}"
    echo ""
    echo -e "${YELLOW}下一步:${NC}"
    echo -e "  1. 在飞书开放平台配置事件订阅 URL"
    echo -e "  2. 测试飞书机器人消息"
    echo -e "  3. 开始使用 Coco 房产助理！"
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  🔐 重要！请立即备份数据加密密钥！${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo -e "客户手机号、微信号等敏感数据已加密存储。"
    echo ""
    echo -e "密钥文件已备份到: ${BLUE}~/backups/real_estate/enc_key.txt${NC}"
    echo ""
    echo -e "${RED}请务必把这个文件保存到安全的地方：${NC}"
    echo -e "  1. 下载到自己的电脑 / U盘 / 网盘（推荐）"
    echo -e "  2. 或打印一份纸质件收好"
    echo ""
    echo -e "${RED}警告：如果服务器重装或文件丢失，没有这把钥匙，${NC}"
    echo -e "${RED}所有客户手机号、微信号将永远无法解密！${NC}"
    echo ""
    read -p "按回车键确认已了解密钥备份的重要性，继续... " _confirm
    echo ""
    echo -e "${GREEN}========================================${NC}"
}

# ==================== 主函数 ====================
main() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  🏠 Coco（可可）房产助理 - 一键安装${NC}"
    echo -e "${BLUE}  基于 Hermes Agent 定制版${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    check_system
    install_deps
    clone_project
    setup_python
    install_packages
    setup_database
    setup_config
    setup_service
    start_service
    print_result
}

main "$@"
