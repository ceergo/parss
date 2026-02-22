import re
import requests
import base64
import socket
import os
import time
import json
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import maxminddb

# --- CONFIGURATION (MEGA SOURCES) ---
# Список проверенных источников для сбора сырых конфигураций
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
    "https://raw.githubusercontent.com/yebekhe/TV2RAY/main/sub/subscription",
    "https://raw.githubusercontent.com/freefq/free/master/v2",
    "https://raw.githubusercontent.com/Paw0015/Free-Vpn-Proxy/main/links/all",
    "https://raw.githubusercontent.com/V2Ray-Flags/V2Ray-Flags/main/V2Ray-Flags.txt"
]

# GitHub Trigger Config (ceergo/proverf)
# Параметры для активации Workflow во втором репозитории после завершения сбора
SECOND_REPO_OWNER = "ceergo"
SECOND_REPO_NAME = "proverf"
DISPATCH_EVENT_TYPE = "proxy_updated"

# File paths
PERSONAL_LINKS_FILE = "my_personal_links.txt"
ACTIVITY_LOG = "activity_log.txt"
OUTPUT_FILE = "my_stable_configs.txt"
BY_FILE = "BY_stable.txt"
KZ_FILE = "KZ_stable.txt"
CACHE_FILE = "proxy_cache.json"

# Target countries (Elite Filter)
# Только эти страны попадут в финальные списки
TARGET_COUNTRIES = ['BY', 'KZ', 'PL', 'CH', 'SE', 'DE', 'US', 'GB', 'FI', 'TR', 'NL', 'FR']

# Emoji Flags Dictionary
COUNTRY_FLAGS = {
    'BY': '🇧🇾', 'KZ': '🇰🇿', 'PL': '🇵🇱', 'CH': '🇨🇭', 'SE': '🇸🇪', 
    'DE': '🇩🇪', 'US': '🇺🇸', 'GB': '🇬🇧', 'FI': '🇫🇮', 'TR': '🇹🇷', 
    'NL': '🇳🇱', 'FR': '🇫🇷', 'UN': '🌐'
}

# GeoIP settings
GEOIP_URL = "https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-Country.mmdb"
GEOIP_FILENAME = "GeoLite2-Country.mmdb"

# Performance settings
THREADS = 150 
TIMEOUT = 2.5 

# Global counters for real-time reporting
stats_lock = threading.Lock()
processed_count = 0
total_configs_to_check = 0
alive_found = 0
dead_found = 0
skipped_cache = 0
dns_fail = 0
wrong_country = 0

def load_cache():
    """
    Загрузка кэша прокси с проверкой жизненного цикла.
    Если кэш старше 3 дней, он сбрасывается для обеспечения актуальности.
    """
    if not os.path.exists(CACHE_FILE):
        print(f"[CACHE] 🆕 Файл {CACHE_FILE} не найден. Создаю новый.")
        return {"start_date": datetime.now().isoformat(), "data": {}}
    
    try:
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
        
        start_date_str = cache.get("start_date", datetime.now().isoformat())
        start_date = datetime.fromisoformat(start_date_str)
        
        if datetime.now() - start_date > timedelta(days=3):
            print("[CACHE] 🔄 Цикл (3 дня) завершен. Очистка старой памяти...")
            return {"start_date": datetime.now().isoformat(), "data": {}}
            
        return cache
    except Exception as e:
        print(f"[CACHE] ⚠️ Ошибка при чтении кэша: {e}")
        return {"start_date": datetime.now().isoformat(), "data": {}}

def save_cache(cache_data):
    """
    Атомарное сохранение текущего состояния кэша.
    Использует fsync для гарантии записи на диск.
    """
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        print(f"✅ [CACHE] Память сохранена в {CACHE_FILE}")
    except Exception as e:
        print(f"[CACHE] ⚠️ Ошибка сохранения: {e}")

def download_geoip_with_retry(retries=3):
    """
    Скачивание базы GeoIP с проверкой целостности и повторными попытками.
    """
    if os.path.exists(GEOIP_FILENAME):
        print("✅ [GEOIP] База данных уже присутствует.")
        return True
    
    for i in range(retries):
        try:
            print(f"🌐 [GEOIP] Загрузка базы данных (Попытка {i+1})...")
            response = requests.get(GEOIP_URL, stream=True, timeout=30)
            response.raise_for_status()
            with open(GEOIP_FILENAME, 'wb') as f:
                f.write(response.content)
            print("✅ [GEOIP] База успешно загружена.")
            return True
        except Exception as e:
            print(f"⚠️ [GEOIP] Ошибка загрузки: {e}")
            if i < retries - 1:
                time.sleep(5)
    return False

def get_ip_from_host(host):
    """
    Резолвинг домена в IP-адрес. 
    Если на вход подан уже IP, возвращает его без DNS-запроса.
    """
    try:
        clean_host = host.strip()
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", clean_host):
            return clean_host
        return socket.gethostbyname(clean_host)
    except:
        return None

def check_tcp_port(ip, port):
    """
    Проверка доступности TCP порта.
    Поддерживает IPv4 и IPv6 (автоопределение).
    """
    try:
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(TIMEOUT)
            s.connect((ip, int(port)))
            return True
    except:
        return False

def extract_host_port(config):
    """
    Универсальный экстрактор данных для VLESS, VMess, Trojan, ShadowSocks.
    Декодирует VMess JSON и обрабатывает различные форматы ссылок.
    """
    try:
        if config.startswith("vmess://"):
            vmess_data = config.replace("vmess://", "")
            padding = len(vmess_data) % 4
            if padding: vmess_data += "=" * (4 - padding)
            try:
                decoded_js = json.loads(base64.b64decode(vmess_data).decode('utf-8'))
                host = decoded_js.get('add')
                port = decoded_js.get('port')
                if host and port:
                    return str(host).strip(), str(port).strip(), "VMESS"
            except: pass

        if "@" in config:
            protocol = config.split("://")[0].upper()
            # Извлечение части адреса до параметров и имен
            address_part = config.split("@")[1].split("?")[0].split("#")[0].split("/")[0]
            
            # Обработка IPv6 в квадратных скобках [2001:db8::1]:443
            if address_part.startswith("["):
                match = re.search(r"\[(.+)\]:(\d+)", address_part)
                if match:
                    return match.group(1), match.group(2), protocol
            
            # Стандартный формат host:port
            if ":" in address_part:
                parts = address_part.split(":")
                return parts[0].strip(), parts[-1].strip(), protocol

        elif config.startswith("ss://"):
            encoded_part = config.replace("ss://", "").split("#")[0]
            # SS может быть не закодирован в base64 в некоторых форматах
            if ":" in encoded_part and "@" not in encoded_part: 
                 parts = encoded_part.split(":")
                 return parts[0].strip(), parts[1].strip(), "SS"
            
            padding = len(encoded_part) % 4
            if padding: encoded_part += "=" * (4 - padding)
            try:
                decoded = base64.b64decode(encoded_part).decode('utf-8', errors='ignore')
                if "@" in decoded:
                    address_part = decoded.split("@")[1].split("/")[0]
                    if ":" in address_part:
                        host, port = address_part.split(":")[:2]
                        return host.strip(), port.strip(), "SS"
            except: pass
    except: pass
    return None, None, "UNKNOWN"

def decode_content(content):
    """
    Декодирование содержимого подписки, если оно в Base64.
    """
    try:
        if "://" not in content[:50]:
            return base64.b64decode(content).decode('utf-8')
    except: pass
    return content

def process_config(config, reader, cached_data):
    """
    Основная логика: Кэш -> DNS -> GeoIP -> TCP Check.
    Включает Trace-логирование для подозрительных BY/KZ узлов.
    """
    global processed_count, alive_found, dead_found, skipped_cache, dns_fail, wrong_country
    
    config = config.strip()
    if not config or "://" not in config: return None

    # TRACE LOGIC: Проверка, является ли конфиг потенциальной целью для BY/KZ
    is_target_trace = any(x in config.upper() for x in ["BY", "BELARUS", "KZ", "KAZAKHSTAN"])
    
    host, port, proto = extract_host_port(config)
    if not host or not port: return None

    fingerprint = f"{host}:{port}:{proto}"
    
    # 1. Проверка Кэша (Total Caching)
    if fingerprint in cached_data:
        entry = cached_data[fingerprint]
        
        if entry["status"] == "dead":
            with stats_lock: 
                processed_count += 1
                skipped_cache += 1
            return None
        
        if entry["status"] == "alive":
            country_code = str(entry.get("country", "UN")).strip().upper()
            ip = entry.get("ip", host)
            
            with stats_lock:
                processed_count += 1
                alive_found += 1
                skipped_cache += 1 
            
            flag = COUNTRY_FLAGS.get(country_code, '🌐')
            base_url = config.split("#")[0]
            final_name = f"{flag} [{country_code}] {proto} | {ip}"
            
            if is_target_trace or country_code in ['BY', 'KZ']:
                print(f"🕵️‍♂️ [TRACE_CACHE] {country_code} | {ip} найден в памяти.")
            
            return {
                "id": fingerprint, 
                "country": country_code, 
                "data": f"{base_url}#{final_name}",
                "status": "success"
            }

    # 2. DNS Резолвинг
    ip = get_ip_from_host(host)
    if not ip: 
        with stats_lock: 
            processed_count += 1
            dns_fail += 1
        return None

    # 3. GeoIP Определение (Строго по IP)
    try:
        geo_data = reader.get(ip)
        country_code = str(geo_data.get('country', {}).get('iso_code', 'UN')).strip().upper()
    except:
        country_code = "UN"

    # 4. Фильтр по странам
    if country_code not in TARGET_COUNTRIES:
        with stats_lock: 
            processed_count += 1
            wrong_country += 1
        return None
    
    # 5. Проверка TCP порта
    is_alive = check_tcp_port(ip, port)
    
    with stats_lock:
        processed_count += 1
        if is_alive: alive_found += 1
        else: dead_found += 1
        
    if is_target_trace:
        status_str = "ALIVE" if is_alive else "DEAD"
        print(f"🕵️‍♂️ [TRACE_CHECK] {country_code} | {ip}:{port} | Результат: {status_str}")
    
    # Обновление состояния в кэше
    cached_data[fingerprint] = {
        "status": "alive" if is_alive else "dead",
        "time": datetime.now().isoformat(),
        "ip": ip,
        "country": country_code
    }

    if not is_alive: 
        return None

    # 6. Форматирование финального имени
    flag = COUNTRY_FLAGS.get(country_code, '🌐')
    base_url = config.split("#")[0]
    final_name = f"{flag} [{country_code}] {proto} | {ip}"
    
    return {
        "id": fingerprint, 
        "country": country_code, 
        "data": f"{base_url}#{final_name}",
        "status": "success"
    }

def update_activity_log(found, skipped, dead, dns, geo):
    """
    Запись расширенной статистики в activity_log.txt.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(ACTIVITY_LOG, "a", encoding="utf-8") as f:
            log_line = (f"[{now}] Alive: {found} | Dead: {dead} | Cache_Hit: {skipped} | "
                        f"DNS_Fail: {dns} | Wrong_Geo: {geo}\n")
            f.write(log_line)
    except: pass

def safe_write(filename, data_list):
    """
    Безопасная запись данных в файл с защитой от сбоев.
    """
    try:
        with open(filename, "w", encoding="utf-8") as f:
            if data_list:
                f.write("\n".join(data_list) + "\n")
            f.flush()
            os.fsync(f.fileno())
        print(f"💾 [FILE] {filename:18} | Кол-во: {len(data_list):4}")
    except Exception as e:
        print(f"❌ [ОШИБКА] Запись {filename}: {e}")

def trigger_second_repo():
    """
    Отправка сигнала (Dispatch) второму боту в репозиторий ceergo/proverf.
    Требуется секрет SECOND_REPO_PAT.
    """
    token = os.getenv("SECOND_REPO_PAT")
    if not token:
        print("⚠️ [TRIGGER] Токен SECOND_REPO_PAT не найден. Пропускаю активацию второго бота.")
        return

    url = f"https://api.github.com/repos/{SECOND_REPO_OWNER}/{SECOND_REPO_NAME}/dispatches"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {"event_type": DISPATCH_EVENT_TYPE}
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 204:
            print(f"🚀 [TRIGGER] Сигнал успешно отправлен в {SECOND_REPO_OWNER}/{SECOND_REPO_NAME}!")
        else:
            print(f"⚠️ [TRIGGER] Ошибка GitHub API: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ [TRIGGER] Не удалось отправить сигнал: {e}")

def main():
    global total_configs_to_check, processed_count, alive_found, dead_found, skipped_cache, dns_fail, wrong_country
    
    print("🚀 --- MEGA WORKER V4.5 [FINAL TRACE & TRIGGER] ---")
    start_time = time.time()

    # Инициализация ресурсов
    if not download_geoip_with_retry(): return

    reader = maxminddb.open_database(GEOIP_FILENAME)
    cache = load_cache()
    cached_data = cache["data"]
    
    all_raw_configs = []
    
    # 1. Сбор из облачных источников
    print("📡 --- ЭТАП СБОРА ДАННЫХ ---")
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=15)
            decoded = decode_content(r.text)
            configs = [l.strip() for l in decoded.splitlines() if "://" in l]
            all_raw_configs.extend(configs)
        except: pass

    # 2. Сбор из личных ссылок
    if os.path.exists(PERSONAL_LINKS_FILE):
        with open(PERSONAL_LINKS_FILE, "r", encoding="utf-8") as f:
            for line in f.read().splitlines():
                line = line.strip()
                if not line or line.startswith("#"): continue
                if line.startswith("http"):
                    try:
                        r = requests.get(line, timeout=15)
                        content = decode_content(r.text)
                        all_raw_configs.extend([l.strip() for l in content.splitlines() if "://" in l])
                    except: pass
                else: 
                    all_raw_configs.append(line)

    unique_candidates = list(set(all_raw_configs))
    total_configs_to_check = len(unique_candidates)
    print(f"🔍 Найдено уникальных кандидатов: {total_configs_to_check}")
    
    results_list = []
    seen_ids = set()
    
    # Параллельная проверка в 150 потоков
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        future_tasks = [executor.submit(process_config, cfg, reader, cached_data) for cfg in unique_candidates]
        for future in as_completed(future_tasks):
            res = future.result()
            if res and res.get("status") == "success" and res['id'] not in seen_ids:
                seen_ids.add(res['id'])
                results_list.append(res)

    # 3. Распределение и аудит
    print("\n📂 --- ФИНАЛЬНЫЙ АУДИТ РАСПРЕДЕЛЕНИЯ ---")
    by_configs = [r['data'] for r in results_list if r['country'] == 'BY']
    kz_configs = [r['data'] for r in results_list if r['country'] == 'KZ']
    
    if by_configs: print(f"🇧🇾 [BY] Найдено узлов: {len(by_configs)}")
    if kz_configs: print(f"🇰🇿 [KZ] Найдено узлов: {len(kz_configs)}")
    
    results_list.sort(key=lambda x: x['country'])
    all_configs = [r['data'] for r in results_list]

    # Сохранение результатов
    safe_write(OUTPUT_FILE, all_configs)
    safe_write(BY_FILE, by_configs)
    safe_write(KZ_FILE, kz_configs)

    # Завершение
    update_activity_log(len(all_configs), skipped_cache, dead_found, dns_fail, wrong_country)
    save_cache(cache)
    reader.close()
    
    # Сигнал второму боту
    trigger_second_repo()

    duration = time.time() - start_time
    print(f"\n✅ Успешно завершено за {duration:.1f}с. Живых прокси: {len(all_configs)}")

if __name__ == "__main__":
    main()
