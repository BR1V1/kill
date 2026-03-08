
import requests
import json
import re
import time
import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse, unquote
import os

# --- НАСТРОЙКИ ---
GITHUB_RAW_URL = "https://raw.githubusercontent.com/roosterkid/openproxylist/refs/heads/main/V2RAY_BASE64.txt"  # Замените на реальную ссылку
XUI_PANEL_URL = "https://91.200.12.94:25495/3x-ui"  # URL панели 3x-UI
XUI_USERNAME = "mFuEDxBnf5"  # Логин
XUI_PASSWORD = "lFwVN8X1zp"  # Пароль

# Настройки обновления
UPDATE_INTERVAL_HOURS = 24  # Интервал обновления (в часах)
LOG_FILE = "xui_importer.log"

# Шаблон для поиска VMess/VLESS ссылок
LINK_PATTERN = r'(vless://|vmess://)[^\s]+'

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def load_last_update_time():
    """Загружает время последнего обновления из файла."""
    try:
        if os.path.exists('last_update.txt'):
            with open('last_update.txt', 'r') as f:
                return datetime.fromisoformat(f.read().strip())
    except Exception as e:
        logger.warning(f"Не удалось загрузить время последнего обновления: {e}")
    return None

def save_last_update_time(timestamp):
    """Сохраняет время последнего обновления в файл."""
    try:
        with open('last_update.txt', 'w') as f:
            f.write(timestamp.isoformat())
    except Exception as e:
        logger.error(f"Не удалось сохранить время последнего обновления: {e}")

def should_update():
    """Проверяет, нужно ли выполнять обновление."""
    last_update = load_last_update_time()
    if not last_update:
        return True
    next_update = last_update + timedelta(hours=UPDATE_INTERVAL_HOURS)
    return datetime.now() >= next_update

def download_links_from_github(url):
    """Скачивает файл с GitHub и извлекает из него ссылки."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        content = response.text
        links = re.findall(LINK_PATTERN, content, re.IGNORECASE)
        logger.info(f"Найдено ссылок: {len(links)}")
        return links
    except requests.RequestException as e:
        logger.error(f"Ошибка при загрузке файла с GitHub: {e}")
        return []

def parse_vless_link(link):
    """Парсит VLESS-ссылку в словарь с параметрами."""
    parsed = urlparse(link)
    query_params = dict(qc.split('=') for qc in parsed.query.split('&') if '=' in qc)
    return {
        "protocol": "vless",
        "address": parsed.netloc.split(':')[0],
        "port": int(parsed.netloc.split(':')[1]) if ':' in parsed.netloc else 443,
        "uuid": parsed.path.lstrip('/'),
        "flow": query_params.get('flow', ''),
        "encryption": query_params.get('encryption', 'none'),
        "network": query_params.get('type', 'tcp'),
        "security": query_params.get('security', 'tls'),
        "sni": query_params.get('sni', ''),
        "alpn": query_params.get('alpn', '').split(',') if query_params.get('alpn') else [],
        "fp": query_params.get('fp', ''),
        "pbk": query_params.get('pbk', ''),
        "sid": query_params.get('sid', ''),
        "spx": query_params.get('spx', '')
    }

def parse_vmess_link(link):
    """Парсит VMess-ссылку (упрощённо)."""
    logger.warning(f"Парсинг VMess-ссылки пока не реализован: {link}")
    return None

def login_to_xui(session):
    """Авторизуется в 3x-UI и получает токен."""
    login_url = f"{XUI_PANEL_URL}/login"
    payload = {
        "username": XUI_USERNAME,
        "password": XUI_PASSWORD
    }
    try:
        response = session.post(login_url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("Успешная авторизация в 3x-UI")
            return True
        else:
            logger.error(f"Ошибка авторизации: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Ошибка подключения к панели: {e}")
        return False

def add_outbound_to_xui(session, outbound_data):
    """Добавляет исходящее соединение через API 3x-UI."""
    add_url = f"{XUI_PANEL_URL}/panel/inbound/add"
    try:
        response = session.post(add_url, json=outbound_data, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                logger.info(f"Соединение добавлено: {outbound_data['remark']}")
                return True
            else:
                logger.error(f"Ошибка API: {result.get('msg', 'Unknown error')}")
                return False
        else:
            logger.error(f"HTTP ошибка: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Ошибка при добавлении соединения: {e}")
        return False

def process_links(links, session):
    """Обрабатывает список ссылок и добавляет их в 3x-UI."""
    for link in links:
        logger.info(f"Обрабатывается ссылка: {link}")

        # Определяем тип ссылки и парсим
        if link.lower().startswith('vless://'):
            config = parse_vless_link(link)
        elif link.lower().startswith('vmess://'):
            config = parse_vmess_link(link)
            if not config:
                continue
        else:
            logger.warning("Неподдерживаемый протокол. Пропускаем.")
            continue

        # Формируем данные для API 3x-UI (упрощённо)
        outbound_data = {
            "remark": f"Imported-{config['address']}:{config['port']}",
            "up": 0,
            "down": 0,
            "total": 0,
            "enable": True,
            "config": json.dumps({
                "protocol": config["protocol"],
                "settings": {
                    "clients": [{
                        "id": config["uuid"],
                        "flow": config["flow"]
                    }]
                },
                "streamSettings": {
                    "network": config["network"],
                    "security": config["security"],
                    "tlsSettings": {
                        "serverName": config["sni"],
                        "alpn": config["alpn"]
                    }
                }
            })
        }

        # Добавляем соединение
        add_outbound_to_xui(session, outbound_data)

def main():
    """Основная функция с циклом проверки обновлений."""
    logger.info("Запуск скрипта импорта соединений в 3x-UI")

    while True:
        # Проверяем, нужно ли обновлять
        if should_update():
            logger.info("Начинаем процесс обновления...")

            # Скачиваем ссылки
            links = download_links_from_github(GITHUB_RAW_URL)
            if not links:
                logger.warning("Не удалось получить ссылки. Пропускаем обновление.")
                # Обновляем время, чтобы не пытаться снова сразу
                save_last_update_time(datetime.now())
                time.sleep(3600)  # Ждём час перед следующей