#!/usr/bin/env bash
#
# Coco（可可）房产助理 - 一键安装脚本
# 基于 Hermes Agent 定制版
# 用法: curl -fsSL https://gitee.com/liyuheng200408/real-estate-agent/raw/master/install.sh | bash
#
set -euo pipefail

# ==================== 配置 ====================
REPO_URL="https://gitee.com/liyuheng200408/real-estate-agent.git"
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
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        warn "目录已存在，拉取最新代码..."
        cd "$INSTALL_DIR"
        git pull
    else
        git clone "$REPO_URL" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi
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
    
    if [[ "$OS" == "linux" ]]; then
        sudo systemctl enable postgresql
        sudo systemctl start postgresql
    elif [[ "$OS" == "macos" ]]; then
        brew services start postgresql
    fi
    
    sudo -u postgres psql -c "CREATE USER hermes WITH PASSWORD '$DB_PASSWORD';" 2>/dev/null || true
    sudo -u postgres psql -c "CREATE DATABASE hermes_agent OWNER hermes;" 2>/dev/null || true
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE hermes_agent TO hermes;" 2>/dev/null || true
    
    cat > "$INSTALL_DIR/.env.db" << EOF
# 数据库配置（自动生成）
DB_HOST=localhost
DB_PORT=5432
DB_NAME=hermes_agent
DB_USER=hermes
DB_PASSWORD=$DB_PASSWORD
DATABASE_URL=postgresql://hermes:$DB_PASSWORD@localhost:5432/hermes_agent
EOF
    ok "数据库配置完成"
}

# ==================== 交互式配置 ====================
interactive_config() {
    info "配置 Coco 房产助理..."
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Coco（可可）房产助理 - 配置向导${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    # 选择模型厂商
    echo -e "${YELLOW}请选择模型厂商:${NC}"
    echo "  1) 小米 MiMo"
    echo "  2) OpenAI"
    echo "  3) OpenRouter"
    echo "  4) 其他（手动配置）"
    read -r PROVIDER_CHOICE
    
    case $PROVIDER_CHOICE in
        1)
            PROVIDER="xiaomi"
            PROVIDER_NAME="小米 MiMo"
            API_KEY_VAR="XIAOMI_API_KEY"
            ;;
        2)
            PROVIDER="openai"
            PROVIDER_NAME="OpenAI"
            API_KEY_VAR="OPENAI_API_KEY"
            ;;
        3)
            PROVIDER="openrouter"
            PROVIDER_NAME="OpenRouter"
            API_KEY_VAR="OPENROUTER_API_KEY"
            ;;
        *)
            PROVIDER="custom"
            PROVIDER_NAME="自定义"
            API_KEY_VAR="OPENAI_API_KEY"
            ;;
    esac
    
    echo -e "${YELLOW}请输入 ${PROVIDER_NAME} API Key:${NC}"
    read -r API_KEY
    
    echo -e "${YELLOW}请输入飞书 App ID:${NC}"
    read -r FEISHU_APP_ID
    
    echo -e "${YELLOW}请输入飞书 App Secret:${NC}"
    read -r FEISHU_APP_SECRET
    
    cat > "$INSTALL_DIR/.env" << EOF
# Coco 房产助理配置
# 模型厂商: $PROVIDER_NAME
$API_KEY_VAR=$API_KEY
FEISHU_APP_ID=$FEISHU_APP_ID
FEISHU_APP_SECRET=$FEISHU_APP_SECRET
HERMES_HOME=$INSTALL_DIR
GATEWAY_ALLOW_ALL_USERS=true
EOF
    
    cat "$INSTALL_DIR/.env.db" >> "$INSTALL_DIR/.env"
    rm -f "$INSTALL_DIR/.env.db"
    chmod 600 "$INSTALL_DIR/.env"
    ok "配置完成"
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
ExecStart=$INSTALL_DIR/venv/bin/python -m hermes_cli.main gateway run
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
Environment=HERMES_HOME=$INSTALL_DIR
GATEWAY_ALLOW_ALL_USERS=true

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
        sudo systemctl start $SERVICE_NAME
        ok "服务已启动"
    else
        cd "$INSTALL_DIR"
        source "venv/bin/activate"
        nohup python3 -m hermes_cli.main gateway run > /dev/null 2>&1 &
        ok "服务已在后台启动"
    fi
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
    interactive_config
    setup_service
    start_service
    print_result
}

main "$@"
