"""
Главный файл приложения агента.
Точка входа.
"""
import asyncio
import logging
import threading
from pathlib import Path
import sys

# Создаем необходимые папки ДО настройки логирования
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
    
    def __init__(self):
        # Пути
        self.base_dir = Path(__file__).parent
        self.config_path = self.base_dir / "config" / "config.json"
        self.proxies_path = self.base_dir / "config" / "proxies.json"
        self.mafiles_dir = self.base_dir / "maFiles"
        
        # Агент
        self.agent = Agent(
            str(self.config_path),
            str(self.proxies_path),
            str(self.mafiles_dir)
        )
        
        # GUI
        self.gui = AgentGUI(
            on_start_agent=self.start_agent,
            on_stop_agent=self.stop_agent,
            on_trigger_ingestion=self.trigger_ingestion,
            on_save_config=self.save_config,
            on_save_proxy=self.save_proxy,
            on_remove_proxy=self.remove_proxy
        )
        
        # Настраиваем callback'и агента
        self.agent.set_callbacks(
            on_status_change=self.on_status_change,
            on_log=self.on_log
        )
        
        # Asyncio loop для агента
        self.loop = None
        self.agent_thread = None
        
        # Загружаем данные в GUI
        self._load_initial_data()
    
    def _load_initial_data(self) -> None:
        """Загрузить начальные данные в GUI."""
        # Конфиг
        config = self.agent.get_config()
        self.gui.update_config_fields(
            config["server_ip"],
            config["agent_token"]
        )
        
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
        """Запустить ingestion."""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.agent.trigger_ingestion(), self.loop)
        else:
            # Если агент не запущен, запускаем ingestion в новом loop
            asyncio.run(self.agent.trigger_ingestion())
        
        # Обновляем список аккаунтов
        accounts = self.agent.get_accounts_with_proxies()
        self.gui.update_accounts_list(accounts)
    
    def save_config(self, server_ip: str, agent_token: str) -> None:
        """Сохранить конфигурацию."""
        self.agent.save_config(server_ip, agent_token)
    
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
    
    def on_status_change(self, connected: bool) -> None:
        """Callback изменения статуса."""
        # Обновляем GUI (thread-safe через after)
        self.gui.after(0, lambda: self.gui.update_connection_status(connected))
    
    def on_log(self, message: str) -> None:
        """Callback логирования."""
        # Обновляем GUI (thread-safe через after)
        self.gui.after(0, lambda: self.gui.add_log(message))
    
    def run(self) -> None:
        """Запустить приложение."""
        self.gui.mainloop()


if __name__ == "__main__":
    app = Application()
    try:
        app.run()
    except KeyboardInterrupt:
        logging.info("Приложение остановлено пользователем")
        sys.exit(0)

