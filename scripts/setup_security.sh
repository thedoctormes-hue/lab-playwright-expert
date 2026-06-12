#!/usr/bin/env bash
# ============================================================
# setup-security.sh — настройка безопасности Playwright-инфраструктуры
# ============================================================
# Запуск: sudo bash setup-security.sh
#
# Что делает:
#   1. Создаёт отдельного пользователя для сервиса
#   2. Настраивает директории с безопасными правами
#   3. Устанавливает systemd unit с ограничениями
#   4. Настраивает кэш с правильными правами
#   5. Мигрирует старые cookies в зашифрованный vault
#   6. Генерирует API key
#   7. Настраивает logrotate
#   8. Проверяет конфигурацию
# ============================================================

set -euo pipefail

PROJECT_DIR="/root/LabDoctorM/projects/lab-playwright-expert"
SECRETS_DIR="/root/LabDoctorM/.secrets"
SERVICE_USER="screenshot-service"
SERVICE_GROUP="screenshot-service"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ─── Проверки ───────────────────────────────────────────────────

if [[ $EUID -ne 0 ]]; then
    log_error "Запуск требует root. Используйте: sudo bash $0"
    exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  🔒 Playwright Infrastructure Security Setup            ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ─── 1. Создание пользователя ──────────────────────────────────

log_info "[1/8] Создание системного пользователя..."

if id "$SERVICE_USER" &>/dev/null; then
    log_warn "Пользователь $SERVICE_USER уже существует"
else
    useradd \
        --system \
        --no-create-home \
        --shell /usr/sbin/nologin \
        --comment "Screenshot Service" \
        "$SERVICE_USER"
    log_info "Пользователь $SERVICE_USER создан"
fi

# ─── 2. Директории и права ─────────────────────────────────────

log_info "[2/8] Настройка директорий..."

# Кэш скриншотов
CACHE_DIR="/tmp/screenshot_cache_secure"
mkdir -p "$CACHE_DIR"
chown "$SERVICE_USER:$SERVICE_GROUP" "$CACHE_DIR"
chmod 700 "$CACHE_DIR"
log_info "Кэш: $CACHE_DIR (700, $SERVICE_USER)"

# Secrets
mkdir -p "$SECRETS_DIR"
chown root:root "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"
log_info "Secrets: $SECRETS_DIR (700, root)"

# Логи
LOG_DIR="/var/log/screenshot-service"
mkdir -p "$LOG_DIR"
chown "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR"
chmod 750 "$LOG_DIR"
log_info "Логи: $LOG_DIR (750, $SERVICE_USER)"

# ─── 3. Генерация API Key ──────────────────────────────────────

log_info "[3/8] Генерация API Key..."

API_KEY_FILE="$SECRETS_DIR/screenshot-service.env"
if [[ -f "$API_KEY_FILE" ]]; then
    log_warn "API key файл уже существует: $API_KEY_FILE"
    # Показать текущий ключ
    grep SCREENSHOT_API_KEY "$API_KEY_FILE" | sed 's/=/ = /'
else
    API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    cat > "$API_KEY_FILE" <<EOF
# Screenshot Service API Key
# Сгенерирован: $(date -Iseconds)
SCREENSHOT_API_KEY=${API_KEY}
EOF
    chmod 600 "$API_KEY_FILE"
    chown root:root "$API_KEY_FILE"
    log_info "API key сгенерирован и сохранён в $API_KEY_FILE"
    echo ""
    echo -e "  ${YELLOW}API Key:${NC} ${API_KEY}"
    echo -e "  ${RED}⚠️  Сохраните этот ключ!${NC}"
    echo ""
fi

# ─── 4. Установка systemd unit ─────────────────────────────────

log_info "[4/8] Установка systemd unit..."

cp "$PROJECT_DIR/config/screenshot-service.service" /etc/systemd/system/
systemctl daemon-reload
log_info "Unit установлен: /etc/systemd/system/screenshot-service.service"

# ─── 5. Миграция cookies ───────────────────────────────────────

log_info "[5/8] Миграция cookies в зашифрованный vault..."

LEGACY_COOKIES=(
    "$PROJECT_DIR/config/habr_cookies.json"
    "$PROJECT_DIR/config/vc_cookies.json"
)

for cookie_file in "${LEGACY_COOKIES[@]}"; do
    if [[ -f "$cookie_file" ]]; then
        platform=$(basename "$cookie_file" | sed 's/_cookies.json//')
        log_info "Миграция $platform cookies..."
        python3 -c "
import sys
sys.path.insert(0, '$PROJECT_DIR/scripts')
from secret_manager import migrate_cookies_to_vault
result = migrate_cookies_to_vault('$cookie_file', '$platform')
sys.exit(0 if result else 1)
" && log_info "✓ $platform cookies мигрированы" || log_warn "✗ Ошибка миграции $platform"
    else
        log_info "Нет файла: $cookie_file — пропуск"
    fi
done

# ─── 6. Logrotate ──────────────────────────────────────────────

log_info "[6/8] Настройка logrotate..."

cat > /etc/logrotate.d/screenshot-service <<'EOF'
/var/log/screenshot-service/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 screenshot-service screenshot-service
    sharedscripts
    postrotate
        systemctl reload screenshot-service 2>/dev/null || true
    endscript
}
EOF
log_info "Logrotate настроен"

# ─── 7. Проверка конфигурации ──────────────────────────────────

log_info "[7/8] Проверка конфигурации..."

ERRORS=0

# Проверить пользователя
if id "$SERVICE_USER" &>/dev/null; then
    log_info "✓ Пользователь $SERVICE_USER существует"
else
    log_error "✗ Пользователь $SERVICE_USER не найден"
    ((ERRORS++))
fi

# Проверить права на кэш
CACHE_PERMS=$(stat -c "%a" "$CACHE_DIR" 2>/dev/null || echo "000")
if [[ "$CACHE_PERMS" == "700" ]]; then
    log_info "✓ Кэш права 700"
else
    log_error "✗ Кэш права $CACHE_PERMS (ожидается 700)"
    ((ERRORS++))
fi

# Проверить права на secrets
SECRETS_PERMS=$(stat -c "%a" "$SECRETS_DIR" 2>/dev/null || echo "000")
if [[ "$SECRETS_PERMS" == "700" ]]; then
    log_info "✓ Secrets права 700"
else
    log_error "✗ Secrets права $SECRETS_PERMS (ожидается 700)"
    ((ERRORS++))
fi

# Проверить API key файл
if [[ -f "$API_KEY_FILE" ]]; then
    KEY_PERMS=$(stat -c "%a" "$API_KEY_FILE")
    if [[ "$KEY_PERMS" == "600" ]]; then
        log_info "✓ API key файл права 600"
    else
        log_error "✗ API key файл права $KEY_PERMS (ожидается 600)"
        ((ERRORS++))
    fi
else
    log_error "✗ API key файл не найден"
    ((ERRORS++))
fi

# Проверить systemd unit
if systemctl cat screenshot-service.service &>/dev/null; then
    log_info "✓ systemd unit валиден"
else
    log_error "✗ systemd unit невалиден"
    ((ERRORS++))
fi

# Проверить зависимости
for cmd in python3 curl; do
    if command -v "$cmd" &>/dev/null; then
        log_info "✓ $cmd доступен"
    else
        log_error "✗ $cmd не найден"
        ((ERRORS++))
    fi
done

# Проверить cryptography
if python3 -c "from cryptography.fernet import Fernet" 2>/dev/null; then
    log_info "✓ cryptography установлен"
else
    log_warn "✗ cryptography не установлен. pip install cryptography"
fi

# ─── 8. Итог ───────────────────────────────────────────────────

log_info "[8/8] Итоговая проверка..."

echo ""
echo "╔══════════════════════════════════════════════════════════╗"

if [[ $ERRORS -eq 0 ]]; then
    echo "║  ✅ Все проверки пройдены                              ║"
else
    echo "║  ⚠️  Обнаружено ошибок: ${ERRORS}                              ║"
fi

echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Следующие шаги:                                       ║"
echo "║                                                         ║"
echo "║  1. Запустить сервис:                                  ║"
echo "║     systemctl start screenshot-service                  ║"
echo "║                                                         ║"
echo "║  2. Проверить статус:                                  ║"
echo "║     systemctl status screenshot-service                 ║"
echo "║                                                         ║"
echo "║  3. Проверить работу:                                  ║"
echo "║     curl -H 'X-API-Key: <KEY>' \\                       ║"
echo "║       -X POST http://127.0.0.1:8190/screenshot \\       ║"
echo "║       -d '{\"url\": \"https://example.com\"}'             ║"
echo "║                                                         ║"
echo "║  4. Логи:                                              ║"
echo "║     journalctl -u screenshot-service -f                 ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

exit $ERRORS
