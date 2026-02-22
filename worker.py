import re
import requests
import base64
import socket
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import maxminddb

# --- КОНФИГУРАЦИЯ ---
SOURCES = [
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge.txt",
    "https://raw.githubusercontent.com/freev2rayspeed/v2ray/main/v2ray.txt",
    "https://raw.githubusercontent.com/aiboboxx/v2rayfree/main/v2ray",
    "https://raw.githubusercontent.com/vpei/free-v2ray-config/master/v2ray.txt",
    "https://raw.githubusercontent.com/tbbatbb/Proxy/master/dist/v2ray.config",
    "https://raw.githubusercontent.com/StayHu/v2ray/master/v2ray.txt"
]

PERSONAL_LINKS_FILE = "my_personal_links.txt"
ACTIVITY_LOG = "activity_log.txt"
TARGET_COUNTRIES = ['BY', 'KZ', 'PL', 'CH', 'SE', 'DE', 'US']
OUTPUT_FILE = "my_stable_configs.txt"

GEOIP_URL = "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb"
GEOIP_FILENAME = "GeoLite2-Country.mmdb"

THREADS = 100
TIMEOUT = 1.2

def download_geoip_with_retry(retries=3):
    """Скачивание базы GeoIP с повторными попытками"""
    if os.path.exists(GEOIP_FILENAME):
        print("✅ База GeoIP уже на месте.")
        return True
    
    for i in range(retries):
        try:
            print(f"🌐 Загрузка GeoIP (Попытка {i+1})...")
            response = requests.get(GEOIP_URL, stream=True, timeout=30)
            response.raise_for_status()
            with open(GEOIP_FILENAME, 'wb') as f:
                f.write(response.content)
            print("✅ База успешно загружена.")
            return True
        except Exception as e:
            print(f"⚠️ Ошибка при загрузке: {e}")
            time.sleep(5)
    return False

def get_ip_from_host(host):
    """Преобразование хоста в IP"""
    try:
        return socket.gethostbyname(host)
    except:
        return None

def check_tcp_port(ip, port):
    """Проверка доступности порта через TCP"""
    try:
        with socket.create_connection((ip, int(port)), timeout=TIMEOUT):
            return True
    except:
        return False

def extract_host_port(config):
    """Извлечение хоста и порта из ссылки"""
    try:
        if "@" in config:
            address_part = config.split("@")[1].split("?")[0].split("#")[0]
            if ":" in address_part:
                host, port = address_part.split(":")[:2]
                return host.strip(), port.strip()
    except:
        pass
    return None, None

def decode_content(content):
    """Декодирование Base64 если нужно"""
    try:
        if "://" not in content[:20]:
            return base64.b64decode(content).decode('utf-8')
    except:
        pass
    return content

def process_config(config, reader):
    """Полный цикл обработки конфига"""
    config = config.strip()
    if not config or len(config) < 10: return None
    
    host, port = extract_host_port(config)
    if not host or not port: return None

    ip = host if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host) else get_ip_from_host(host)
    if not ip: return None

    # 1. Проверка страны (Локально)
    try:
        geo_data = reader.get(ip)
        country_code = geo_data.get('country', {}).get('iso_code')
    except:
        country_code = None

    if country_code not in TARGET_COUNTRIES: return None
    
    # 2. Проверка живучести порта
    if not check_tcp_port(ip, port): return None

    # 3. Успех: Форматирование и тег
    base_url = config.split("#")[0]
    final_name = f"[{country_code}]_Exp_{ip}"
    return {"id": f"{ip}:{port}", "data": f"{base_url}#{final_name}"}

def update_activity_log(count):
    """Обновление лога активности для пробуждения GitHub Actions"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(ACTIVITY_LOG, "w", encoding="utf-8") as f:
            f.write(f"Last Check: {now}\nFound Alive: {count}\nStatus: Active (Anti-Stall Pulse)")
        print(f"💓 Пульс обновлен: {now}")
    except Exception as e:
        print(f"⚠️ Не удалось обновить пульс: {e}")

def main():
    print("🚀 Запуск HEAVY-DUTY WORKER v3.3 [Extreme Pulse Mode]...")
    if not download_geoip_with_retry():
        print("🛑 Критическая ошибка: База GeoIP отсутствует. Выход.")
        return

    reader = maxminddb.open_database(GEOIP_FILENAME)
    all_raw_configs = []

    # --- ЧАСТЬ 1: Глобальные источники ---
    print(f"📡 Сбор из {len(SOURCES)} глобальных источников...")
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=15)
            decoded = decode_content(r.text)
            lines = decoded.splitlines()
            all_raw_configs.extend([l.strip() for l in lines if l.strip()])
            print(f"✅ Загружено {len(lines)} из {url[:40]}...")
        except Exception as e:
            print(f"⚠️ Пропуск источника {url[:30]}: {e}")

    # --- ЧАСТЬ 2: Личный файл (Свалка) ---
    if not os.path.exists(PERSONAL_LINKS_FILE):
        with open(PERSONAL_LINKS_FILE, "w", encoding="utf-8") as f:
            f.write("# Босс, кидай сюда ссылки или сырые vless/trojan конфиги!\n")
        print(f"📝 Создан файл {PERSONAL_LINKS_FILE}")
    else:
        print(f"📂 Обработка твоего файла {PERSONAL_LINKS_FILE}...")
        try:
            with open(PERSONAL_LINKS_FILE, "r", encoding="utf-8") as f:
                for line in f.read().splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    
                    if line.startswith("http"):
                        try:
                            r = requests.get(line, timeout=10)
                            decoded = decode_content(r.text)
                            all_raw_configs.extend([l.strip() for l in decoded.splitlines() if l.strip()])
                        except:
                            print(f"⚠️ Ошибка загрузки личной ссылки: {line[:40]}")
                    else:
                        all_raw_configs.append(line)
        except Exception as e:
            print(f"⚠️ Ошибка чтения личного файла: {e}")

    # --- ЧАСТЬ 3: Многопоточная проверка ---
    print(f"📊 Всего элементов на проверку: {len(all_raw_configs)}")
    print(f"⚙️ Запуск фильтрации (Потоков: {THREADS})...")

    results = {}
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        future_tasks = [executor.submit(process_config, cfg, reader) for cfg in all_raw_configs]
        for future in as_completed(future_tasks):
            res = future.result()
            if res:
                # Дедупликация по IP:Port
                if res['id'] not in results:
                    results[res['id']] = res['data']

    # --- ЧАСТЬ 4: Сохранение и Пульс ---
    final_list = list(results.values())
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(final_list))
        print(f"💾 Результат сохранен в {OUTPUT_FILE}")
    except Exception as e:
        print(f"❌ Ошибка записи результата: {e}")

    update_activity_log(len(final_list))
    reader.close()
    print(f"🏁 ГОТОВО! Уникальных живых конфигов: {len(final_list)}")

if __name__ == "__main__":
    main()
