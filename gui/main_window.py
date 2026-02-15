"""
Главное окно GUI агента.
"""
import customtkinter as ctk
from typing import Callable, List, Dict


class AgentGUI(ctk.CTk):
    """Главное окно приложения."""
    
    def __init__(
        self,
        on_start_agent: Callable,
        on_stop_agent: Callable,
        on_trigger_ingestion: Callable,
        on_save_config: Callable,
        on_save_proxy: Callable,
        on_remove_proxy: Callable
    ):
        super().__init__()
        
        # Callbacks
        self.on_start_agent = on_start_agent
        self.on_stop_agent = on_stop_agent
        self.on_trigger_ingestion = on_trigger_ingestion
        self.on_save_config = on_save_config
        self.on_save_proxy = on_save_proxy
        self.on_remove_proxy = on_remove_proxy
        
        # Настройки окна
        self.title("AutoBase Agent")
        self.geometry("900x650")
        self.resizable(True, True)
        
        # Тема
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        
        # Сетка
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # === ЛЕВАЯ ПАНЕЛЬ (Навигация) ===
        self._create_sidebar()
        
        # === ПРАВАЯ ЧАСТЬ (Контент) ===
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        # Инициализация фреймов
        from gui.frames.dashboard_frame import DashboardFrame
        from gui.frames.accounts_frame import AccountsFrame
        from gui.frames.settings_frame import SettingsFrame
        
        self.frame_dashboard = DashboardFrame(
            self.main_frame,
            on_start=self.on_start_agent,
            on_stop=self.on_stop_agent,
            on_ingest=self.on_trigger_ingestion
        )
        
        self.frame_accounts = AccountsFrame(
            self.main_frame,
            on_save_proxy=self.on_save_proxy,
            on_remove_proxy=self.on_remove_proxy
        )
        
        self.frame_settings = SettingsFrame(
            self.main_frame,
            on_save=self.on_save_config
        )
        
        # Показываем дашборд по умолчанию
        self.show_dashboard()
    
    def _create_sidebar(self) -> None:
        """Создать боковую панель навигации."""
        self.sidebar_frame = ctk.CTkFrame(self, width=180, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)
        
        # Логотип
        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="🤖\nAutoBase\nAgent",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 20))
        
        # Кнопки навигации
        self.btn_dashboard = ctk.CTkButton(
            self.sidebar_frame,
            text="📊 Дашборд",
            command=self.show_dashboard,
            height=40,
            font=ctk.CTkFont(size=14)
        )
        self.btn_dashboard.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        
        self.btn_accounts = ctk.CTkButton(
            self.sidebar_frame,
            text="🌐 Аккаунты / Прокси",
            command=self.show_accounts,
            height=40,
            font=ctk.CTkFont(size=14)
        )
        self.btn_accounts.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        
        self.btn_settings = ctk.CTkButton(
            self.sidebar_frame,
            text="⚙️ Настройки",
            command=self.show_settings,
            height=40,
            font=ctk.CTkFont(size=14)
        )
        self.btn_settings.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        
        # Версия внизу
        self.version_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="v1.0.0",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        self.version_label.grid(row=5, column=0, padx=20, pady=(0, 20))
    
    def show_dashboard(self) -> None:
        """Показать дашборд."""
        self._clear_main()
        self.frame_dashboard.pack(fill="both", expand=True)
        self._highlight_button(self.btn_dashboard)
    
    def show_accounts(self) -> None:
        """Показать управление аккаунтами."""
        self._clear_main()
        self.frame_accounts.pack(fill="both", expand=True)
        self._highlight_button(self.btn_accounts)
    
    def show_settings(self) -> None:
        """Показать настройки."""
        self._clear_main()
        self.frame_settings.pack(fill="both", expand=True)
        self._highlight_button(self.btn_settings)
    
    def _clear_main(self) -> None:
        """Очистить главную область."""
        for widget in self.main_frame.winfo_children():
            widget.pack_forget()
    
    def _highlight_button(self, button: ctk.CTkButton) -> None:
        """Подсветить активную кнопку."""
        for btn in [self.btn_dashboard, self.btn_accounts, self.btn_settings]:
            if btn != button:
                btn.configure(fg_color=("gray75", "gray25"))
            else:
                btn.configure(fg_color=["#3B8ED0", "#1F6AA5"])  # Цвет темы по умолчанию
    
    # === Публичные методы для обновления UI ===
    
    def update_connection_status(self, connected: bool) -> None:
        """Обновить статус подключения."""
        self.frame_dashboard.update_status(connected)
    
    def add_log(self, message: str) -> None:
        """Добавить сообщение в лог."""
        self.frame_dashboard.add_log(message)
    
    def update_accounts_list(self, accounts: List[Dict[str, str]]) -> None:
        """Обновить список аккаунтов."""
        self.frame_accounts.update_accounts(accounts)
    
    def update_config_fields(self, server_ip: str, agent_token: str) -> None:
        """Обновить поля конфигурации."""
        self.frame_settings.set_fields(server_ip, agent_token)

