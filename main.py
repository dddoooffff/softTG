import sys
import os
import json
import asyncio
import random
from datetime import datetime, timedelta
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError

# ==================== КЛАСС ЗАЩИТЫ ====================
class AntiBanProtection:
    def __init__(self):
        self.delay_min = 8
        self.delay_max = 18
        self.batch_size = 5
        self.batch_pause = 120
        self.max_per_hour = 30
        self.max_per_day = 100
        self.cooldown_after_error = 180
        self.sent_count = {}
        self.last_reset = {}
        self.typing_speed = (3, 7)
    
    def random_delay(self):
        return random.uniform(self.delay_min, self.delay_max)
    
    def human_typing(self):
        return random.uniform(self.typing_speed[0], self.typing_speed[1])
    
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
            base_message + " 🤝",
            base_message + "\n\nС уважением!",
            base_message + "\n\nДо связи!",
        ]
        return random.choice(variants)
    
    def shuffle_chats(self, chats):
        shuffled = chats.copy()
        random.shuffle(shuffled)
        return shuffled

# ==================== РАБОЧИЙ ПОТОК ====================
class SenderThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal()
    
    def __init__(self, accounts, chats, message, protection):
        super().__init__()
        self.accounts = accounts
        self.chats = chats
        self.message = message
        self.protection = protection
        self.is_running = True
    
    def stop(self):
        self.is_running = False
    
    def run(self):
        asyncio.run(self.start_sending())
        self.finished_signal.emit()
    
    async def start_sending(self):
        total_sent = 0
        total_errors = 0
        total_chats = len(self.chats)
        
        for acc_idx, acc in enumerate(self.accounts):
            if not self.is_running:
                break
                
            self.log_signal.emit(f"\n{'='*50}")
            self.log_signal.emit(f"🔹 Аккаунт: {acc['name']}")
            self.log_signal.emit(f"{'='*50}")
            
            client = TelegramClient(
                acc['session'], 
                acc['api_id'], 
                acc['api_hash']
            )
            
            try:
                await client.start()
                me = await client.get_me()
                self.log_signal.emit(f"✅ Вошли как: {me.first_name} (ID: {me.id})")
                
                shuffled_chats = self.protection.shuffle_chats(self.chats)
                max_messages = min(30, self.protection.max_per_hour)
                sent_this_session = 0
                
                for i, chat in enumerate(shuffled_chats[:max_messages]):
                    if not self.is_running:
                        break
                    
                    if not self.protection.check_limits(acc['name']):
                        self.log_signal.emit(f"⏳ Достигнут лимит 30 сообщений")
                        break
                    
                    self.log_signal.emit(f"📤 Отправка {i+1}/{max_messages} в {chat['title']}...")
                    
                    try:
                        await asyncio.sleep(self.protection.human_typing())
                        await client.send_message(
                            chat['id'], 
                            self.protection.rotate_message(self.message)
                        )
                        
                        self.protection.sent_count[acc['name']] = \
                            self.protection.sent_count.get(acc['name'], 0) + 1
                        
                        sent_this_session += 1
                        total_sent += 1
                        
                        delay = self.protection.random_delay()
                        self.log_signal.emit(f"✅ Отправлено! Пауза {delay:.1f} сек...")
                        await asyncio.sleep(delay)
                        
                        if random.random() < 0.15:
                            long_pause = random.uniform(15, 45)
                            self.log_signal.emit(f"☕ Длинная пауза {long_pause:.0f} сек...")
                            await asyncio.sleep(long_pause)
                        
                        self.progress_signal.emit(total_sent, total_chats * len(self.accounts))
                        
                    except FloodWaitError as e:
                        wait_time = e.seconds
                        self.log_signal.emit(f"⚠️ FloodWait на {wait_time} сек")
                        if wait_time > 3600:
                            self.log_signal.emit(f"❌ Слишком долго, пропускаем")
                            continue
                        await asyncio.sleep(wait_time + 10)
                    except RPCError as e:
                        self.log_signal.emit(f"❌ Ошибка RPC: {e}")
                        await asyncio.sleep(self.protection.cooldown_after_error)
                    except Exception as e:
                        self.log_signal.emit(f"❌ Ошибка: {e}")
                    
                    if sent_this_session % self.protection.batch_size == 0 and sent_this_session < max_messages:
                        pause = self.protection.batch_pause + random.uniform(-20, 20)
                        self.log_signal.emit(f"⏸️ Пауза между пачками {pause:.0f} сек...")
                        await asyncio.sleep(pause)
                    
                    if sent_this_session >= max_messages:
                        self.log_signal.emit(f"✅ Отправлено 30 сообщений!")
                        break
                
                await client.disconnect()
                self.log_signal.emit(f"✅ Аккаунт {acc['name']} завершил (отправлено: {sent_this_session})")
                
                if acc_idx < len(self.accounts) - 1:
                    pause = random.uniform(60, 180)
                    self.log_signal.emit(f"⏳ Пауза между аккаунтами {pause:.0f} сек...")
                    await asyncio.sleep(pause)
                
            except Exception as e:
                self.log_signal.emit(f"❌ Критическая ошибка {acc['name']}: {e}")
                total_errors += 1
        
        self.log_signal.emit(f"\n{'='*50}")
        self.log_signal.emit(f"🎉 ЗАВЕРШЕНО!")
        self.log_signal.emit(f"Отправлено: {total_sent}")
        self.log_signal.emit(f"Ошибок: {total_errors}")
        self.log_signal.emit(f"{'='*50}")

# ==================== ГЛАВНОЕ ОКНО ====================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.accounts = []
        self.chats = []
        self.message = ""
        self.protection = AntiBanProtection()
        self.sender_thread = None
        self.config_file = "config_gui.json"
        
        self.load_config()
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("📨 Telegram Рассыльщик с защитой")
        self.setGeometry(100, 100, 900, 700)
        
        # Центральный виджет
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # ===== ВЕРХНЯЯ ПАНЕЛЬ =====
        top_panel = QHBoxLayout()
        
        # Кнопки
        btn_add_acc = QPushButton("➕ Добавить аккаунт")
        btn_add_acc.clicked.connect(self.add_account)
        top_panel.addWidget(btn_add_acc)
        
        btn_load_chats = QPushButton("📂 Загрузить чаты")
        btn_load_chats.clicked.connect(self.load_chats)
        top_panel.addWidget(btn_load_chats)
        
        btn_set_msg = QPushButton("✏️ Сообщение")
        btn_set_msg.clicked.connect(self.set_message)
        top_panel.addWidget(btn_set_msg)
        
        btn_settings = QPushButton("⚙️ Настройки защиты")
        btn_settings.clicked.connect(self.show_settings)
        top_panel.addWidget(btn_settings)
        
        btn_start = QPushButton("🚀 СТАРТ")
        btn_start.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        btn_start.clicked.connect(self.start_sending)
        top_panel.addWidget(btn_start)
        
        btn_stop = QPushButton("⏹ СТОП")
        btn_stop.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
        btn_stop.clicked.connect(self.stop_sending)
        top_panel.addWidget(btn_stop)
        
        layout.addLayout(top_panel)
        
        # ===== ТАБЛИЦА АККАУНТОВ =====
        group_acc = QGroupBox("📋 Аккаунты")
        acc_layout = QVBoxLayout()
        
        self.table_acc = QTableWidget()
        self.table_acc.setColumnCount(4)
        self.table_acc.setHorizontalHeaderLabels(["Имя", "API ID", "Сессия", "Отправлено"])
        self.table_acc.horizontalHeader().setStretchLastSection(True)
        acc_layout.addWidget(self.table_acc)
        
        btn_del_acc = QPushButton("🗑 Удалить выбранный аккаунт")
        btn_del_acc.clicked.connect(self.delete_account)
        acc_layout.addWidget(btn_del_acc)
        
        group_acc.setLayout(acc_layout)
        layout.addWidget(group_acc)
        
        # ===== СПИСОК ЧАТОВ =====
        group_chats = QGroupBox("📢 Чаты для рассылки")
        chats_layout = QVBoxLayout()
        
        self.list_chats = QListWidget()
        chats_layout.addWidget(self.list_chats)
        
        btn_clear_chats = QPushButton("🗑 Очистить чаты")
        btn_clear_chats.clicked.connect(self.clear_chats)
        chats_layout.addWidget(btn_clear_chats)
        
        group_chats.setLayout(chats_layout)
        layout.addWidget(group_chats)
        
        # ===== ЛОГИ =====
        group_logs = QGroupBox("📝 Логи")
        logs_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        logs_layout.addWidget(self.log_text)
        
        group_logs.setLayout(logs_layout)
        layout.addWidget(group_logs)
        
        # ===== ПРОГРЕСС-БАР =====
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Статус-бар
        self.statusBar().showMessage("Готов к работе")
        
        # Обновляем таблицу
        self.update_accounts_table()
        self.update_chats_list()
    
    # ===== ЗАГРУЗКА / СОХРАНЕНИЕ =====
    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    self.accounts = data.get('accounts', [])
                    self.chats = data.get('chats', [])
                    self.message = data.get('message', '')
                    
                    prot = data.get('protection', {})
                    self.protection.delay_min = prot.get('delay_min', 8)
                    self.protection.delay_max = prot.get('delay_max', 18)
                    self.protection.max_per_hour = prot.get('max_per_hour', 30)
                    self.protection.max_per_day = prot.get('max_per_day', 100)
                    self.protection.batch_size = prot.get('batch_size', 5)
                    self.protection.batch_pause = prot.get('batch_pause', 120)
            except:
                pass
    
    def save_config(self):
        data = {
            'accounts': self.accounts,
            'chats': self.chats,
            'message': self.message,
            'protection': {
                'delay_min': self.protection.delay_min,
                'delay_max': self.protection.delay_max,
                'max_per_hour': self.protection.max_per_hour,
                'max_per_day': self.protection.max_per_day,
                'batch_size': self.protection.batch_size,
                'batch_pause': self.protection.batch_pause
            }
        }
        with open(self.config_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    # ===== ДОБАВЛЕНИЕ АККАУНТА =====
    def add_account(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Добавить аккаунт")
        dialog.setModal(True)
        layout = QVBoxLayout()
        
        # Поля
        fields = {}
        for label in ["Имя аккаунта:", "API ID:", "API Hash:"]:
            lbl = QLabel(label)
            layout.addWidget(lbl)
            edit = QLineEdit()
            if label == "API Hash:":
                edit.setEchoMode(QLineEdit.Password)
            fields[label] = edit
            layout.addWidget(edit)
        
        # Кнопки
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)
        
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            name = fields["Имя аккаунта:"].text().strip()
            api_id = fields["API ID:"].text().strip()
            api_hash = fields["API Hash:"].text().strip()
            
            if not name or not api_id or not api_hash:
                QMessageBox.warning(self, "Ошибка", "Заполните все поля!")
                return
            
            try:
                api_id = int(api_id)
            except:
                QMessageBox.warning(self, "Ошибка", "API ID должен быть числом!")
                return
            
            # Проверяем аккаунт
            session_name = name.replace(" ", "_")
            
            # Асинхронная проверка
            async def check_account():
                client = TelegramClient(session_name, api_id, api_hash)
                try:
                    await client.start()
                    me = await client.get_me()
                    await client.disconnect()
                    return True, me.first_name
                except Exception as e:
                    return False, str(e)
            
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                success, result = loop.run_until_complete(check_account())
                loop.close()
                
                if success:
                    self.accounts.append({
                        'name': name,
                        'api_id': api_id,
                        'api_hash': api_hash,
                        'session': session_name
                    })
                    self.protection.sent_count[name] = 0
                    self.protection.last_reset[name] = datetime.now()
                    self.update_accounts_table()
                    self.save_config()
                    self.log(f"✅ Аккаунт {name} добавлен!")
                else:
                    QMessageBox.critical(self, "Ошибка", f"Не удалось войти:\n{result}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка: {e}")
    
    # ===== ЗАГРУЗКА ЧАТОВ =====
    def load_chats(self):
        if not self.accounts:
            QMessageBox.warning(self, "Ошибка", "Сначала добавьте аккаунт!")
            return
        
        acc = self.accounts[0]
        
        async def get_chats():
            client = TelegramClient(acc['session'], acc['api_id'], acc['api_hash'])
            await client.start()
            dialogs = await client.get_dialogs()
            await client.disconnect()
            
            chats = []
            for d in dialogs:
                if d.is_group or d.is_channel:
                    chats.append({
                        'id': d.id,
                        'title': d.name or "Без названия"
                    })
            return chats
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            chats = loop.run_until_complete(get_chats())
            loop.close()
            
            if not chats:
                QMessageBox.information(self, "Инфо", "Нет доступных чатов")
                return
            
            # Диалог выбора
            dialog = QDialog(self)
            dialog.setWindowTitle("Выбор чатов")
            dialog.setModal(True)
            dialog.resize(500, 400)
            
            layout = QVBoxLayout()
            
            lbl = QLabel("Выберите чаты для рассылки:")
            layout.addWidget(lbl)
            
            list_widget = QListWidget()
            list_widget.setSelectionMode(QListWidget.MultiSelection)
            
            for chat in chats:
                item = QListWidgetItem(chat['title'])
                item.setData(Qt.UserRole, chat)
                # Отмечаем уже выбранные
                if any(c['id'] == chat['id'] for c in self.chats):
                    item.setSelected(True)
                list_widget.addItem(item)
            
            layout.addWidget(list_widget)
            
            btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            btn_box.accepted.connect(dialog.accept)
            btn_box.rejected.connect(dialog.reject)
            layout.addWidget(btn_box)
            
            dialog.setLayout(layout)
            
            if dialog.exec_() == QDialog.Accepted:
                self.chats = []
                for item in list_widget.selectedItems():
                    chat = item.data(Qt.UserRole)
                    self.chats.append(chat)
                
                self.update_chats_list()
                self.save_config()
                self.log(f"✅ Выбрано {len(self.chats)} чатов")
                
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка загрузки чатов: {e}")
    
    # ===== СООБЩЕНИЕ =====
    def set_message(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Настройка сообщения")
        dialog.setModal(True)
        dialog.resize(500, 300)
        
        layout = QVBoxLayout()
        
        lbl = QLabel("Введите текст сообщения:")
        layout.addWidget(lbl)
        
        text_edit = QTextEdit()
        text_edit.setText(self.message)
        layout.addWidget(text_edit)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)
        
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            self.message = text_edit.toPlainText()
            self.save_config()
            self.log(f"✅ Сообщение сохранено ({len(self.message)} символов)")
    
    # ===== НАСТРОЙКИ ЗАЩИТЫ =====
    def show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Настройки защиты")
        dialog.setModal(True)
        dialog.resize(400, 300)
        
        layout = QVBoxLayout()
        
        settings = [
            ('Задержка мин (сек):', self.protection.delay_min),
            ('Задержка макс (сек):', self.protection.delay_max),
            ('Сообщений в час:', self.protection.max_per_hour),
            ('Сообщений в день:', self.protection.max_per_day),
            ('Размер пачки:', self.protection.batch_size),
            ('Пауза между пачками (сек):', self.protection.batch_pause),
        ]
        
        self.settings_inputs = {}
        for label, value in settings:
            hbox = QHBoxLayout()
            lbl = QLabel(label)
            hbox.addWidget(lbl)
            
            spin = QSpinBox()
            spin.setRange(1, 999)
            spin.setValue(value)
            hbox.addWidget(spin)
            
            layout.addLayout(hbox)
            self.settings_inputs[label] = spin
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)
        
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            self.protection.delay_min = self.settings_inputs['Задержка мин (сек):'].value()
            self.protection.delay_max = self.settings_inputs['Задержка макс (сек):'].value()
            self.protection.max_per_hour = self.settings_inputs['Сообщений в час:'].value()
            self.protection.max_per_day = self.settings_inputs['Сообщений в день:'].value()
            self.protection.batch_size = self.settings_inputs['Размер пачки:'].value()
            self.protection.batch_pause = self.settings_inputs['Пауза между пачками (сек):'].value()
            
            self.save_config()
            self.log("✅ Настройки защиты сохранены!")
    
    # ===== ЗАПУСК РАССЫЛКИ =====
    def start_sending(self):
        if not self.accounts:
            QMessageBox.warning(self, "Ошибка", "Нет аккаунтов!")
            return
        if not self.chats:
            QMessageBox.warning(self, "Ошибка", "Не выбраны чаты!")
            return
        if not self.message:
            QMessageBox.warning(self, "Ошибка", "Не задано сообщение!")
            return
        
        # Подтверждение
        reply = QMessageBox.question(
            self, 
            "Подтверждение",
            f"Запустить рассылку?\n\n"
            f"Аккаунтов: {len(self.accounts)}\n"
            f"Чатов: {len(self.chats)}\n"
            f"Лимит: {self.protection.max_per_hour} в час\n"
            f"Задержка: {self.protection.delay_min}-{self.protection.delay_max} сек",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        self.log_text.clear()
        self.progress_bar.setValue(0)
        
        self.sender_thread = SenderThread(
            self.accounts,
            self.chats,
            self.message,
            self.protection
        )
        self.sender_thread.log_signal.connect(self.log)
        self.sender_thread.progress_signal.connect(self.update_progress)
        self.sender_thread.finished_signal.connect(self.on_sending_finished)
        self.sender_thread.start()
        
        self.statusBar().showMessage("🔄 Идёт рассылка...")
    
    def stop_sending(self):
        if self.sender_thread and self.sender_thread.isRunning():
            self.sender_thread.stop()
            self.log("⏹ Остановка рассылки...")
            self.statusBar().showMessage("⏹ Остановлено пользователем")
    
    def on_sending_finished(self):
        self.statusBar().showMessage("✅ Рассылка завершена")
        self.sender_thread = None
    
    # ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
    def log(self, text):
        self.log_text.append(text)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    def update_progress(self, current, total):
        if total > 0:
            value = int((current / total) * 100)
            self.progress_bar.setValue(value)
    
    def update_accounts_table(self):
        self.table_acc.setRowCount(len(self.accounts))
        for i, acc in enumerate(self.accounts):
            sent = self.protection.sent_count.get(acc['name'], 0)
            self.table_acc.setItem(i, 0, QTableWidgetItem(acc['name']))
            self.table_acc.setItem(i, 1, QTableWidgetItem(str(acc['api_id'])))
            self.table_acc.setItem(i, 2, QTableWidgetItem(acc['session']))
            self.table_acc.setItem(i, 3, QTableWidgetItem(str(sent)))
    
    def delete_account(self):
        row = self.table_acc.currentRow()
        if row >= 0:
            name = self.accounts[row]['name']
            reply = QMessageBox.question(
                self,
                "Удаление",
                f"Удалить аккаунт {name}?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                del self.accounts[row]
                self.update_accounts_table()
                self.save_config()
                self.log(f"🗑 Аккаунт {name} удалён")
    
    def update_chats_list(self):
        self.list_chats.clear()
        for chat in self.chats:
            self.list_chats.addItem(chat['title'])
    
    def clear_chats(self):
        self.chats = []
        self.update_chats_list()
        self.save_config()
        self.log("🗑 Чаты очищены")

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Устанавливаем иконку
    app.setWindowIcon(QIcon())
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())