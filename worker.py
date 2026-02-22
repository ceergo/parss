import re
import requests
import base64
import socket
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import maxminddb

# --- CONFIGURATION (MEGA SOURCES) ---
# Combined list of stable and fresh proxy aggregators
SOURCES = [
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/sub/sub_merge.txt",
    "https://raw.githubusercontent.com/freev2rayspeed/v2ray/main/v2ray.txt",
    "https://raw.githubusercontent.com/aiboboxx/v2rayfree/main/v2ray",
    "https://raw.githubusercontent.com/vpei/free-v2ray-config/master/v2ray.txt",
    "https://raw.githubusercontent.com/tbbatbb/Proxy/master/dist/v2ray.config",
    "https://raw.githubusercontent.com/StayHu/v2ray/master/v2ray.txt",
    "https://raw.githubusercontent.com/Sincere-Xue/v2ray-worker/main/sub/sub_merge.txt",
    "https://raw.githubusercontent.com/LoverSe/v2ray/master/v2ray.txt",
    "https://raw.githubusercontent.com/iwxf/free-v2ray/master/0218/v2ray.txt",
    "https://raw.githubusercontent.com/erkaipl/v2ray/master/v2ray.txt",
    "https://raw.githubusercontent.com/Pawel-H-H/v2ray/master/v2ray.txt",
    "https://raw.githubusercontent.com/mfuu/v2ray/master/v2ray.txt",
    "https://raw.githubusercontent.com/yebekhe/TV2RAY/main/sub/subscription"
]

# File paths
PERSONAL_LINKS_FILE = "my_personal_links.txt"
ACTIVITY_LOG = "activity_log.txt"
OUTPUT_FILE = "my_stable_configs.txt"

# Target countries (Elite Filter + Bypass Expansion)
# Added: GB, FI, TR, NL, FR for better YouTube/Gemini performance
TARGET_COUNTRIES = ['BY', 'KZ', 'PL', 'CH', 'SE', 'DE', 'US', 'GB', 'FI', 'TR', 'NL', 'FR']

# GeoIP settings
GEOIP_URL = "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb"
GEOIP_FILENAME = "GeoLite2-Country.mmdb"

# Performance settings
THREADS = 100
TIMEOUT = 1.2

def download_geoip_with_retry(retries=3):
    """
    Downloads GeoIP database if missing. Uses retries for stability.
    """
    if os.path.exists(GEOIP_FILENAME):
        print("✅ База GeoIP найдена.")
        return True
    
    for i in range(retries):
        try:
            print(f"🌐 Загрузка GeoIP (Попытка {i+1})...")
            response = requests.get(GEOIP_URL, stream=True, timeout=30)
            response.raise_for_status()
            with open(GEOIP_FILENAME, 'wb') as f:
                f.write(response.content)
            print("✅ База GeoIP успешно загружена.")
            return True
        except Exception as e:
            print(f"⚠️ Ошибка загрузки базы: {e}")
            if i < retries - 1:
                time.sleep(5)
    return False

def get_ip_from_host(host):
    """
    Resolves hostname to IP. Returns None if fails.
    """
    try:
        return socket.gethostbyname(host)
    except:
        return None

def check_tcp_port(ip, port):
    """
    Low-level TCP check to verify if the server is reachable.
    """
    try:
        with socket.create_connection((ip, int(port)), timeout=TIMEOUT):
            return True
    except:
        return False

def extract_host_port(config):
    """
    Extracts host and port from VLESS/Trojan/VMess links.
    """
    try:
        if "@" in config:
            # Format: proto://uuid@host:port?params#name
            address_part = config.split("@")[1].split("?")[0].split("#")[0]
            if ":" in address_part:
                host, port = address_part.split(":")[:2]
                return host.strip(), port.strip()
    except:
        pass
    return None, None

def decode_content(content):
    """
    Handles Base64 subscription formats.
    """
    try:
        if "://" not in content[:20]:
            return base64.b64decode(content).decode('utf-8')
    except:
        pass
    return content

def process_config(config, reader):
    """
    Core logic: Host resolution -> Geo Filter -> TCP Check -> Formatting.
    """
    config = config.strip()
    if not config or len(config) < 10: return None
    
    host, port = extract_host_port(config)
    if not host or not port: return None

    # Resolve IP if host is a domain
    ip = host if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host) else get_ip_from_host(host)
    if not ip: return None

    # 1. GeoIP Filter
    try:
        geo_data = reader.get(ip)
        country_code = geo_data.get('country', {}).get('iso_code')
    except:
        country_code = "UN"

    if country_code not in TARGET_COUNTRIES:
        return None
    
    # 2. Survival Check (TCP)
    if not check_tcp_port(ip, port):
        return None

    # 3. Success! Format output
    base_url = config.split("#")[0]
    final_name = f"[{country_code}]_Exp_{ip}"
    return {"id": f"{ip}:{port}", "data": f"{base_url}#{final_name}"}

def update_activity_log(count):
    """
    Updates the log file to trigger activity on GitHub.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(ACTIVITY_LOG, "w", encoding="utf-8") as f:
            f.write(f"Last Check: {now}\nFound Alive: {count}\nStatus: Active (Mega Pulse)")
        print(f"💓 Пульс обновлен: {now}")
    except Exception as e:
        print(f"⚠️ Не удалось обновить лог активности: {e}")

def main():
    print("🚀 --- MEGA WORKER v3.5 [Global Bypass Mode] ---")
    start_time = time.time()

    if not download_geoip_with_retry():
        print("🛑 Критическая ошибка: База GeoIP не найдена. Работа невозможна.")
        return

    reader = maxminddb.open_database(GEOIP_FILENAME)
    all_raw_configs = []

    # --- PHASE 1: Global Sources ---
    print(f"📡 Сбор данных из {len(SOURCES)} глобальных источников...")
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=15)
            decoded = decode_content(r.text)
            lines = [l.strip() for l in decoded.splitlines() if l.strip()]
            all_raw_configs.extend(lines)
            print(f"✅ Успешно: {url[:50]}... ({len(lines)} строк)")
        except:
            print(f"⚠️ Ошибка источника: {url[:40]}")

    # --- PHASE 2: Personal Links ---
    if not os.path.exists(PERSONAL_LINKS_FILE):
        with open(PERSONAL_LINKS_FILE, "w", encoding="utf-8") as f:
            f.write("# Босс, кидай сюда свои ссылки! Каждая строка - новый конфиг.\n")
            f.write("# Сохранение этого файла вызовет мгновенное обновление.\n")
        print(f"📝 Создан файл личных ссылок: {PERSONAL_LINKS_FILE}")
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
                            all_raw_configs.extend([l.strip() for l in decode_content(r.text).splitlines() if l.strip()])
                        except: pass
                    else:
                        all_raw_configs.append(line)
        except Exception as e:
            print(f"⚠️ Ошибка чтения личного файла: {e}")

    # --- PHASE 3: Multithreaded Processing ---
    total_raw = len(all_raw_configs)
    print(f"📊 Всего элементов на входе: {total_raw}")
    print(f"⚙️ Запуск фильтрации (Потоков: {THREADS}, Таймаут: {TIMEOUT}s)...")

    results = {}
    processed = 0
    
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        future_tasks = [executor.submit(process_config, cfg, reader) for cfg in all_raw_configs]
        for future in as_completed(future_tasks):
            processed += 1
            # Progress reporting
            if processed % 500 == 0 or processed == total_raw:
                percent = (processed / total_raw) * 100
                print(f"📦 Прогресс: {processed}/{total_raw} ({percent:.1f}%)")
            
            res = future.result()
            if res:
                # Deduplicate by IP:Port
                if res['id'] not in results:
                    results[res['id']] = res['data']

    # --- PHASE 4: Saving & Analytics ---
    final_configs = list(results.values())
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(final_configs))
        print(f"💾 Результат сохранен: {OUTPUT_FILE}")
    except Exception as e:
        print(f"❌ Ошибка при сохранении результата: {e}")

    update_activity_log(len(final_configs))
    reader.close()
    
    duration = time.time() - start_time
    print("-" * 40)
    print(f"🏁 ГОТОВО за {duration:.1f} сек!")
    print(f"🔹 Обработано строк: {total_raw}")
    print(f"🔹 Уникальных живых: {len(final_configs)}")
    print(f"🔹 КПД: {(len(final_configs)/total_raw)*100:.2f}%")
    print("-" * 40)

if __name__ == "__main__":
    main()
