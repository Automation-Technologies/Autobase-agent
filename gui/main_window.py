"""
Главное окно GUI агента.
"""
import customtkinter as ctk
from typing import Callable, List, Dict
from pathlib import Path

from tkinterdnd2 import TkinterDnD  # type: ignore


class AgentGUI(TkinterDnD.Tk):
    """Главное окно приложения."""
    
    def __init__(
        self,
        mafiles_dir: str,
        on_start_agent: Callable,
        on_stop_agent: Callable,
        on_save_config: Callable,
        on_save_proxy: Callable,
        on_remove_proxy: Callable,
        on_save_account_credentials: Callable,
        on_delete_account: Callable
    ):
        super().__init__()
        
        # Callbacks
        self.mafiles_dir = Path(mafiles_dir)
        self.on_start_agent = on_start_agent
        self.on_stop_agent = on_stop_agent
        self.on_save_config = on_save_config
        self.on_save_proxy = on_save_proxy
        self.on_remove_proxy = on_remove_proxy
        self.on_save_account_credentials = on_save_account_credentials
        self.on_delete_account = on_delete_account
        
        # Настройки окна
        self.title("TA Agent")
        self.geometry("900x800")
        self.minsize(900, 800)
        self.resizable(True, True)
        
        # Устанавливаем иконку
        icon_path = Path(__file__).parent.parent / "assets" / "icon.ico"
        if icon_path.exists():
            self.iconbitmap(str(icon_path))
        
        # Тема
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        
        # Фон корневого окна берём из темы CTk,
        # чтобы визуально совпадать с вариантом root=CTk.
        self._apply_root_background_from_theme()
        self._bind_text_shortcuts()
        
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
            on_stop=self.on_stop_agent
        )
        
        self.frame_accounts = AccountsFrame(
            self.main_frame,
            mafiles_dir=self.mafiles_dir,
            on_save_proxy=self.on_save_proxy,
            on_remove_proxy=self.on_remove_proxy,
            on_save_account_credentials=self.on_save_account_credentials,
            on_delete_account=self.on_delete_account
        )
        
        self.frame_settings = SettingsFrame(
            self.main_frame,
            on_save=self.on_save_config
        )
        
        # Показываем дашборд по умолчанию
        self.show_dashboard()
    
    def _apply_root_background_from_theme(self) -> None:
        """Установить фон root в соответствии с текущей темой CTk."""
        theme = ctk.ThemeManager.theme
        fg_color = theme["CTk"]["fg_color"]
        appearance_mode = ctk.get_appearance_mode()

        if isinstance(fg_color, (list, tuple)) and len(fg_color) >= 2:
            if appearance_mode == "Dark":
                bg_color = fg_color[1]
            else:
                bg_color = fg_color[0]
        else:
            bg_color = fg_color

        self.configure(bg=bg_color)
    
    def _create_sidebar(self) -> None:
        """Создать боковую панель навигации."""
        self.sidebar_frame = ctk.CTkFrame(self, width=180, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)
        
        # Логотип
        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame,
            text="🤖\nTA Agent",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(30, 20))
        
        # Кнопки навигации
        self.btn_dashboard = ctk.CTkButton(
            self.sidebar_frame,
            text="📊 Главная",
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
            text=self._get_app_version_text(),
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        self.version_label.grid(row=5, column=0, padx=20, pady=(0, 20))

    def _get_app_version_text(self) -> str:
        version_path = Path(__file__).resolve().parents[1] / "version.txt"
        version_raw = version_path.read_text(encoding="utf-8").strip()
        if version_raw == "":
            raise ValueError("version.txt пустой.")
        if not version_raw.startswith("v"):
            raise ValueError("version.txt должен быть в формате vX.Y.Z (например, v1.0.0).")
        return version_raw
    
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
    
    def update_config_fields(self, agent_token: str) -> None:
        """Обновить поля конфигурации."""
        self.frame_settings.set_fields(agent_token)

    # === Глобальные бинды для текстовых полей ===

    def _bind_text_shortcuts(self) -> None:
        """Назначить хоткеи Ctrl+V/C/X/A/Z/Y для всех CTkEntry."""
        # paste / copy / cut
        self.bind_all("<Control-v>", self._on_ctrl_v, add="+")
        self.bind_all("<Control-V>", self._on_ctrl_v, add="+")
        self.bind_all("<Control-c>", self._on_ctrl_c, add="+")
        self.bind_all("<Control-C>", self._on_ctrl_c, add="+")
        self.bind_all("<Control-x>", self._on_ctrl_x, add="+")
        self.bind_all("<Control-X>", self._on_ctrl_x, add="+")

        # select all
        self.bind_all("<Control-a>", self._on_ctrl_a, add="+")
        self.bind_all("<Control-A>", self._on_ctrl_a, add="+")

        # undo / redo
        self.bind_all("<Control-z>", self._on_ctrl_z, add="+")
        self.bind_all("<Control-Z>", self._on_ctrl_z, add="+")
        self.bind_all("<Control-y>", self._on_ctrl_y, add="+")
        self.bind_all("<Control-Y>", self._on_ctrl_y, add="+")

    def _is_entry_widget(self, widget) -> bool:
        """Проверка, что виджет — CTkEntry (или его наследник)."""
        return isinstance(widget, ctk.CTkEntry)

    def _on_ctrl_v(self, event):
        widget = event.widget
        if not self._is_entry_widget(widget):
            return
        widget.event_generate("<<Paste>>")
        return "break"

    def _on_ctrl_c(self, event):
        widget = event.widget
        if not self._is_entry_widget(widget):
            return
        widget.event_generate("<<Copy>>")
        return "break"

    def _on_ctrl_x(self, event):
        widget = event.widget
        if not self._is_entry_widget(widget):
            return
        widget.event_generate("<<Cut>>")
        return "break"

    def _on_ctrl_a(self, event):
        widget = event.widget
        if not self._is_entry_widget(widget):
            return
        try:
            widget.select_range(0, "end")
            widget.icursor("end")
        except Exception:
            return
        return "break"

    def _on_ctrl_z(self, event):
        widget = event.widget
        if not self._is_entry_widget(widget):
            return
        widget.event_generate("<<Undo>>")
        return "break"

    def _on_ctrl_y(self, event):
        widget = event.widget
        if not self._is_entry_widget(widget):
            return
        widget.event_generate("<<Redo>>")
        return "break"

