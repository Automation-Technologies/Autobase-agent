"""
Главный файл приложения агента.
Точка входа.
"""
import asyncio
import logging
import threading
from pathlib import Path
import sys
from concurrent.futures import Future

# На Windows Server ProactorLoop чаще отваливается с WinError 121 при длительных сокетах.
# SelectorLoop стабильнее для websocket-соединений в этом проекте.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Создаем необходимые папки ДО настройки логирования
# Определяем базовую директорию: для .exe - папка с exe, для .py - папка со скриптом
if getattr(sys, 'frozen', False):
    # Запущено как .exe
    base_dir = Path(sys.executable).parent
else:
    # Запущено как .py скрипт
    base_dir = Path(__file__).parent
(base_dir / "config").mkdir(exist_ok=True)
(base_dir / "maFiles").mkdir(exist_ok=True)
(base_dir / "logs").mkdir(exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/agent.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

from core.agent import Agent
from gui.main_window import AgentGUI


class Application:
    """Главное приложение."""

    def __init__(self, fernet_key: bytes, mafiles_dict: dict, on_close_callback=None):
        if getattr(sys, 'frozen', False):
            self.base_dir = Path(sys.executable).parent
        else:
            self.base_dir = Path(__file__).parent

        self.config_path = self.base_dir / "config" / "config.json"
        self.proxies_path = self.base_dir / "config" / "proxies.json"
        self.mafiles_dir = self.base_dir / "maFiles"
        self.accounts_storage_path = self.mafiles_dir / "accounts.json.enc"

        self.on_close_callback = on_close_callback

        self.agent = Agent(
            str(self.config_path),
            str(self.proxies_path),
            str(self.mafiles_dir),
            fernet_key=fernet_key,
            mafiles_dict=mafiles_dict,
            accounts_storage_path=self.accounts_storage_path,
        )
        
        # GUI
        self.gui = AgentGUI(
            mafiles_dir=str(self.mafiles_dir),
            on_start_agent=self.start_agent,
            on_stop_agent=self.stop_agent,
            on_save_config=self.save_config,
            on_save_proxy=self.save_proxy,
            on_remove_proxy=self.remove_proxy,
            on_save_account_credentials=self.save_account_credentials,
            on_delete_account=self.delete_account
        )
        
        # Настраиваем обработчик закрытия окна
        self.gui.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Настраиваем callback'и агента
        self.agent.set_callbacks(
            on_status_change=self.on_status_change,
            on_log=self.on_log
        )
        
        # Asyncio loop для агента
        self.loop = None
        self.agent_thread = None
        self._ingestion_lock = threading.Lock()
        self._is_ingestion_running = False
        
        # Загружаем данные в GUI
        self._load_initial_data()
    
    def _load_initial_data(self) -> None:
        """Загрузить начальные данные в GUI."""
        # Конфиг
        config = self.agent.get_config()
        self.gui.update_config_fields(config["agent_token"])
        
        # Аккаунты
        accounts = self.agent.get_accounts_with_proxies()
        self.gui.update_accounts_list(accounts)
    
    def start_agent(self) -> None:
        """Запустить агента в отдельном потоке."""
        if self.agent_thread and self.agent_thread.is_alive():
            self.on_log("⚠️ Агент уже запущен")
            return
        
        self.agent_thread = threading.Thread(target=self._run_agent_loop, daemon=True)
        self.agent_thread.start()
    
    def _run_agent_loop(self) -> None:
        """Запустить asyncio loop для агента."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            self.loop.run_until_complete(self.agent.start())
        except Exception as e:
            self.on_log(f"❌ Ошибка агента: {e}")
        finally:
            self.loop.close()
    
    def stop_agent(self) -> None:
        """Остановить агента."""
        if not self.loop or not self.agent_thread:
            self.on_log("⚠️ Агент не запущен")
            return
        
        # Останавливаем через asyncio
        asyncio.run_coroutine_threadsafe(self.agent.stop(), self.loop)
    
    def trigger_ingestion(self) -> None:
        """
        Запустить ingestion без блокировки GUI-потока.
        Раньше при незапущенном агенте вызывался asyncio.run() в main thread — окно «Not Responding».
        """
        log = logging.getLogger("Agent")

        with self._ingestion_lock:
            if self._is_ingestion_running:
                self.on_log("⚠️ Ingestion уже выполняется, повторный запуск пропущен")
                return
            self._is_ingestion_running = True

        def _refresh_accounts_list() -> None:
            accounts = self.agent.get_accounts_with_proxies()
            self.gui.after(0, lambda: self.gui.update_accounts_list(accounts))

        def _finish_ingestion() -> None:
            with self._ingestion_lock:
                self._is_ingestion_running = False

        def _on_ingestion_done(fut: Future) -> None:
            try:
                fut.result()
            except Exception:
                log.exception("Ingestion: ошибка выполнения")
            finally:
                _refresh_accounts_list()
                _finish_ingestion()

        if self.loop and self.loop.is_running():
            scheduled = asyncio.run_coroutine_threadsafe(
                self.agent.trigger_ingestion(),
                self.loop,
            )
            scheduled.add_done_callback(_on_ingestion_done)
            return

        def _worker() -> None:
            try:
                asyncio.run(self.agent.trigger_ingestion())
            except Exception:
                log.exception("Ingestion: ошибка выполнения")
            finally:
                _refresh_accounts_list()
                _finish_ingestion()

        threading.Thread(target=_worker, daemon=True).start()
    
    def save_config(self, agent_token: str) -> None:
        """Сохранить конфигурацию."""
        self.agent.save_config(agent_token)
    
    def save_proxy(self, login: str, proxy: str) -> None:
        """Сохранить прокси."""
        self.agent.save_proxy(login, proxy)
        
        # Обновляем список аккаунтов
        accounts = self.agent.get_accounts_with_proxies()
        self.gui.update_accounts_list(accounts)
    
    def remove_proxy(self, login: str) -> None:
        """Удалить прокси."""
        self.agent.remove_proxy(login)
        
        # Обновляем список аккаунтов
        accounts = self.agent.get_accounts_with_proxies()
        self.gui.update_accounts_list(accounts)
    
    def save_account_credentials(self, login: str, password: str, mafile_path: str, api_key: str) -> bool:
        """Сохранить данные аккаунта и обновить список в UI."""
        is_saved = self.agent.save_account_credentials(login, password, mafile_path, api_key)
        if not is_saved:
            return False
        self.trigger_ingestion()
        return True
    
    def delete_account(self, login: str) -> None:
        """Удалить аккаунт и обновить список в UI."""
        self.agent.delete_account(login)
        
        accounts = self.agent.get_accounts_with_proxies()
        self.gui.update_accounts_list(accounts)
    
    def on_status_change(self, connected: bool) -> None:
        """Callback изменения статуса."""
        # Обновляем GUI (thread-safe через after)
        self.gui.after(0, lambda: self.gui.update_connection_status(connected))
    
    def on_log(self, message: str) -> None:
        """Callback логирования."""
        # Обновляем GUI (thread-safe через after)
        self.gui.after(0, lambda: self.gui.add_log(message))
    
    def on_closing(self) -> None:
        """Обработчик закрытия окна."""
        # Останавливаем агента если запущен
        if self.agent_thread and self.agent_thread.is_alive():
            self.stop_agent()
        
        # Вызываем callback для шифрования (если передан из launcher)
        if self.on_close_callback:
            self.on_close_callback()
        
        # Закрываем окно
        self.gui.destroy()
    
    def run(self) -> None:
        """Запустить приложение."""
        self.gui.mainloop()


if __name__ == "__main__":
    raise RuntimeError("Запускайте приложение через launcher.py")

