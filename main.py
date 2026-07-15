import asyncio
import os
import json
import random
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, jsonify, redirect, url_for
from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError

# ==================== КОНФИГУРАЦИЯ ====================
CONFIG_FILE = 'config.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        'api_id': '',
        'api_hash': '',
        'accounts': [],
        'chats': [],
        'message': 'Привет! Это тестовое сообщение.',
        'protection': {
            'delay_min': 8,
            'delay_max': 18,
            'max_per_hour': 30,
            'batch_size': 5,
            'batch_pause': 120
        },
        'last_run': 'Никогда'
    }

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

config = load_config()

# ==================== ЗАЩИТА ОТ БАНА ====================
class AntiBanProtection:
    def __init__(self, config):
        self.delay_min = config['protection']['delay_min']
        self.delay_max = config['protection']['delay_max']
        self.batch_size = config['protection']['batch_size']
        self.batch_pause = config['protection']['batch_pause']
        self.max_per_hour = config['protection']['max_per_hour']
        self.sent_count = {}
        self.last_reset = {}
    
    def random_delay(self):
        return random.uniform(self.delay_min, self.delay_max)
    
    def check_limits(self, account_name):
        now = datetime.now()
        if account_name in self.last_reset:
            if (now - self.last_reset[account_name]) > timedelta(hours=1):
                self.sent_count[account_name] = 0
                self.last_reset[account_name] = now
        if self.sent_count.get(account_name, 0) >= self.max_per_hour:
            return False
        return True
    
    def rotate_message(self, base_message):
        variants = [
            base_message,
            base_message + " 🙌",
            base_message + " 👋",
            base_message + " ✅",
            base_message + "\n\nС уважением!"
        ]
        return random.choice(variants)
    
    def shuffle_chats(self, chats_list):
        if not chats_list:
            return []
        shuffled = list(chats_list)
        random.shuffle(shuffled)
        return shuffled

protection = AntiBanProtection(config)

# ==================== ВЕБ-СЕРВЕР ====================
app = Flask(__name__)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Telegram Рассыльщик</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        body { background: #f0f2f5; margin: 0; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .card { background: white; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1, h2 { color: #1a1a2e; margin-top: 0; }
        .flex { display: flex; gap: 20px; flex-wrap: wrap; }
        .flex > * { flex: 1; min-width: 300px; }
        label { display: block; margin: 10px 0 5px; font-weight: 600; }
        input, textarea, select { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; }
        textarea { min-height: 100px; }
        button { background: #4CAF50; color: white; border: none; padding: 12px 24px; border-radius: 6px; cursor: pointer; font-size: 16px; }
        button:hover { background: #45a049; }
        .btn-danger { background: #f44336; }
        .btn-danger:hover { background: #d32f2f; }
        .btn-primary { background: #2196F3; }
        .btn-primary:hover { background: #1976D2; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        .status { display: inline-block; padding: 4px 12px; border-radius: 12px; }
        .status-active { background: #4CAF50; color: white; }
        .status-inactive { background: #f44336; color: white; }
        .log-box { background: #1a1a2e; color: #00ff41; padding: 15px; border-radius: 6px; font-family: monospace; max-height: 300px; overflow-y: auto; font-size: 13px; white-space: pre-wrap; }
        .alert { padding: 15px; border-radius: 6px; margin: 10px 0; }
        .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .badge { background: #6c757d; color: white; padding: 2px 10px; border-radius: 12px; font-size: 14px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>📨 Telegram Рассыльщик</h1>
            <p>Статус: <span class="status status-active">✅ Работает</span></p>
            <p>Последний запуск: <strong>{{ config.last_run }}</strong></p>
        </div>

        <div class="card">
            <h2>🔑 API Настройки</h2>
            <form method="post" action="/update_api">
                <label>API ID</label>
                <input type="text" name="api_id" value="{{ config.api_id }}" required>
                <label>API Hash</label>
                <input type="text" name="api_hash" value="{{ config.api_hash }}" required>
                <button type="submit">Сохранить API</button>
            </form>
        </div>

        <div class="flex">
            <div class="card">
                <h2>👤 Аккаунты</h2>
                <form method="post" action="/add_account">
                    <input type="text" name="account_name" placeholder="Имя аккаунта" required>
                    <button type="submit" class="btn-primary">➕ Добавить</button>
                </form>
                <table>
                    <tr><th>Имя</th><th>Сессия</th><th>Действие</th></tr>
                    {% for acc in config.accounts %}
                    <tr>
                        <td>{{ acc.name }}</td>
                        <td>{{ acc.session }}</td>
                        <td>
                            <form method="post" action="/delete_account" style="display:inline;">
                                <input type="hidden" name="account_name" value="{{ acc.name }}">
                                <button type="submit" class="btn-danger" style="padding:4px 12px;">🗑</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>

            <div class="card">
                <h2>📢 Чаты</h2>
                <form method="post" action="/add_chat">
                    <input type="text" name="chat_id" placeholder="ID чата (число)" required>
                    <input type="text" name="chat_title" placeholder="Название" required>
                    <button type="submit" class="btn-primary">➕ Добавить</button>
                </form>
                <table>
                    <tr><th>Название</th><th>ID</th><th>Действие</th></tr>
                    {% for chat in config.chats %}
                    <tr>
                        <td>{{ chat.title }}</td>
                        <td>{{ chat.id }}</td>
                        <td>
                            <form method="post" action="/delete_chat" style="display:inline;">
                                <input type="hidden" name="chat_id" value="{{ chat.id }}">
                                <button type="submit" class="btn-danger" style="padding:4px 12px;">🗑</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </div>

        <div class="card">
            <h2>✏️ Сообщение</h2>
            <form method="post" action="/update_message">
                <textarea name="message">{{ config.message }}</textarea>
                <button type="submit">Сохранить сообщение</button>
            </form>
        </div>

        <div class="card">
            <h2>⚙️ Настройки защиты</h2>
            <form method="post" action="/update_protection">
                <div class="flex">
                    <div>
                        <label>Задержка мин (сек)</label>
                        <input type="number" name="delay_min" value="{{ config.protection.delay_min }}">
                    </div>
                    <div>
                        <label>Задержка макс (сек)</label>
                        <input type="number" name="delay_max" value="{{ config.protection.delay_max }}">
                    </div>
                    <div>
                        <label>Сообщений в час</label>
                        <input type="number" name="max_per_hour" value="{{ config.protection.max_per_hour }}">
                    </div>
                    <div>
                        <label>Размер пачки</label>
                        <input type="number" name="batch_size" value="{{ config.protection.batch_size }}">
                    </div>
                    <div>
                        <label>Пауза между пачками (сек)</label>
                        <input type="number" name="batch_pause" value="{{ config.protection.batch_pause }}">
                    </div>
                </div>
                <button type="submit">Сохранить настройки</button>
            </form>
        </div>

        <div class="card">
            <h2>🚀 Управление</h2>
            <div class="flex">
                <form method="post" action="/start_sending">
                    <button type="submit" style="background:#4CAF50; padding:15px 40px; font-size:18px;">▶️ СТАРТ</button>
                </form>
                <form method="post" action="/stop_sending">
                    <button type="submit" class="btn-danger" style="padding:15px 40px; font-size:18px;">⏹ СТОП</button>
                </form>
            </div>
        </div>

        <div class="card">
            <h2>📝 Логи</h2>
            <div class="log-box" id="logBox">{{ log }}</div>
            <form method="post" action="/clear_logs" style="margin-top:10px;">
                <button type="submit" class="btn-danger">Очистить логи</button>
            </form>
        </div>
    </div>
</body>
</html>
'''

logs = []
is_sending = False

def add_log(text):
    timestamp = datetime.now().strftime("%H:%M:%S")
    logs.append(f"[{timestamp}] {text}")
    if len(logs) > 500:
        logs.pop(0)

@app.route('/')
def index():
    log_text = '\n'.join(logs[-100:])
    return render_template_string(HTML_TEMPLATE, config=config, log=log_text)

@app.route('/update_api', methods=['POST'])
def update_api():
    config['api_id'] = request.form.get('api_id', '').strip()
    config['api_hash'] = request.form.get('api_hash', '').strip()
    save_config(config)
    add_log(f"✅ API обновлён")
    return redirect('/')

@app.route('/add_account', methods=['POST'])
def add_account():
    name = request.form.get('account_name', '').strip()
    if name and not any(a['name'] == name for a in config['accounts']):
        config['accounts'].append({'name': name, 'session': name})
        save_config(config)
        add_log(f"✅ Добавлен аккаунт: {name}")
    return redirect('/')

@app.route('/delete_account', methods=['POST'])
def delete_account():
    name = request.form.get('account_name', '')
    config['accounts'] = [a for a in config['accounts'] if a['name'] != name]
    save_config(config)
    add_log(f"🗑 Удалён аккаунт: {name}")
    return redirect('/')

@app.route('/add_chat', methods=['POST'])
def add_chat():
    try:
        chat_id = int(request.form.get('chat_id', ''))
        title = request.form.get('chat_title', '').strip()
        if chat_id and title:
            # Проверяем, нет ли уже такого чата
            if not any(c['id'] == chat_id for c in config['chats']):
                config['chats'].append({'id': chat_id, 'title': title})
                save_config(config)
                add_log(f"✅ Добавлен чат: {title} (ID: {chat_id})")
            else:
                add_log(f"⚠️ Чат с ID {chat_id} уже существует")
    except ValueError:
        add_log(f"❌ Ошибка: неверный ID чата (должно быть число)")
    except Exception as e:
        add_log(f"❌ Ошибка: {e}")
    return redirect('/')

@app.route('/delete_chat', methods=['POST'])
def delete_chat():
    try:
        chat_id = int(request.form.get('chat_id', 0))
        config['chats'] = [c for c in config['chats'] if c['id'] != chat_id]
        save_config(config)
        add_log(f"🗑 Удалён чат с ID: {chat_id}")
    except:
        pass
    return redirect('/')

@app.route('/update_message', methods=['POST'])
def update_message():
    config['message'] = request.form.get('message', '')
    save_config(config)
    add_log(f"✅ Сообщение обновлено ({len(config['message'])} символов)")
    return redirect('/')

@app.route('/update_protection', methods=['POST'])
def update_protection():
    try:
        config['protection']['delay_min'] = int(request.form.get('delay_min', 8))
        config['protection']['delay_max'] = int(request.form.get('delay_max', 18))
        config['protection']['max_per_hour'] = int(request.form.get('max_per_hour', 30))
        config['protection']['batch_size'] = int(request.form.get('batch_size', 5))
        config['protection']['batch_pause'] = int(request.form.get('batch_pause', 120))
        save_config(config)
        
        protection.delay_min = config['protection']['delay_min']
        protection.delay_max = config['protection']['delay_max']
        protection.max_per_hour = config['protection']['max_per_hour']
        protection.batch_size = config['protection']['batch_size']
        protection.batch_pause = config['protection']['batch_pause']
        
        add_log(f"✅ Настройки защиты обновлены")
    except:
        add_log(f"❌ Ошибка при сохранении настроек")
    return redirect('/')

@app.route('/clear_logs', methods=['POST'])
def clear_logs():
    global logs
    logs = []
    return redirect('/')

@app.route('/start_sending', methods=['POST'])
def start_sending():
    global is_sending
    if is_sending:
        add_log("⚠️ Рассылка уже запущена")
        return redirect('/')
    
    thread = threading.Thread(target=run_sending)
    thread.daemon = True
    thread.start()
    add_log("🚀 Запущена рассылка!")
    return redirect('/')

@app.route('/stop_sending', methods=['POST'])
def stop_sending():
    global is_sending
    is_sending = False
    add_log("⏹ Остановка рассылки...")
    return redirect('/')

# ==================== ЛОГИКА РАССЫЛКИ ====================
def run_sending():
    global is_sending
    is_sending = True
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_messages())
    except Exception as e:
        add_log(f"❌ Ошибка: {e}")
    finally:
        is_sending = False
        add_log("✅ Рассылка завершена")
        config['last_run'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_config(config)

async def send_messages():
    if not config['api_id'] or not config['api_hash']:
        add_log("❌ Ошибка: API_ID и API_HASH не заданы!")
        return
    
    if not config['accounts']:
        add_log("❌ Нет аккаунтов!")
        return
    
    if not config['chats']:
        add_log("❌ Нет чатов!")
        return
    
    add_log(f"📊 Аккаунтов: {len(config['accounts'])}, Чатов: {len(config['chats'])}")
    add_log(f"📊 Лимит: {protection.max_per_hour} в час")
    
    total_sent = 0
    
    for acc in config['accounts']:
        if not is_sending:
            add_log("⏹ Остановлено пользователем")
            break
        
        add_log(f"🔹 Аккаунт: {acc['name']}")
        
        try:
            client = TelegramClient(
                acc['session'],
                int(config['api_id']),
                config['api_hash']
            )
            
            await client.start()
            me = await client.get_me()
            add_log(f"✅ Вошли как: {me.first_name} (ID: {me.id})")
            
            shuffled_chats = protection.shuffle_chats(config['chats'])
            sent_this_session = 0
            
            for chat in shuffled_chats:
                if not is_sending:
                    break
                
                if sent_this_session >= protection.max_per_hour:
                    add_log(f"⏳ Достигнут лимит {protection.max_per_hour} для {acc['name']}")
                    break
                
                try:
                    await client.send_message(
                        chat['id'],
                        protection.rotate_message(config['message'])
                    )
                    
                    sent_this_session += 1
                    total_sent += 1
                    add_log(f"✅ {sent_this_session}. {chat['title']}")
                    
                    delay = protection.random_delay()
                    await asyncio.sleep(delay)
                    
                except FloodWaitError as e:
                    add_log(f"⚠️ FloodWait на {e.seconds} сек")
                    await asyncio.sleep(e.seconds + 10)
                except Exception as e:
                    add_log(f"❌ Ошибка отправки: {e}")
            
            await client.disconnect()
            add_log(f"✅ Аккаунт {acc['name']} завершил (отправлено: {sent_this_session})")
            
        except Exception as e:
            add_log(f"❌ Критическая ошибка {acc['name']}: {e}")
    
    add_log(f"🎉 ГОТОВО! Отправлено {total_sent} сообщений")

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))
    add_log("🔄 Запуск веб-сервера...")
    app.run(host='0.0.0.0', port=port)