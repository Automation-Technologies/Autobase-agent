"""
Фрейм управления аккаунтами и прокси.
"""
import customtkinter as ctk
from typing import Callable, List, Dict, Optional


class AccountsFrame(ctk.CTkFrame):
    """Управление аккаунтами и привязками прокси."""
    
    def __init__(self, master, on_save_proxy: Callable, on_remove_proxy: Callable):
        super().__init__(master, fg_color="transparent")
        
        self.on_save_proxy = on_save_proxy
        self.on_remove_proxy = on_remove_proxy
        
        self.accounts: List[Dict[str, str]] = []
        self.selected_account: Optional[str] = None
        self.account_buttons: Dict[str, ctk.CTkButton] = {}
        
        self._create_widgets()
    
    def _create_widgets(self) -> None:
        """Создать виджеты."""
        # Заголовок
        title_label = ctk.CTkLabel(
            self,
            text="Управление Прокси",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_label.pack(pady=(0, 10))
        
        # Инструкция
        info_label = ctk.CTkLabel(
            self,
            text="Выберите аккаунт из списка ниже, чтобы настроить прокси",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        info_label.pack(pady=(0, 20))
        
        # Список аккаунтов (Scrollable Frame)
        accounts_label = ctk.CTkLabel(
            self,
            text="Аккаунты:",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        accounts_label.pack(pady=(0, 5), padx=20, fill="x")
        
        self.scroll_frame = ctk.CTkScrollableFrame(self, height=250)
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        # Панель редактирования прокси
        self.edit_frame = ctk.CTkFrame(self, corner_radius=10)
        self.edit_frame.pack(pady=(0, 20), padx=20, fill="x")
        
        self.selected_label = ctk.CTkLabel(
            self.edit_frame,
            text="Выберите аккаунт из списка выше",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.selected_label.pack(pady=(15, 10))
        
        # Поле ввода прокси
        proxy_frame = ctk.CTkFrame(self.edit_frame, fg_color="transparent")
        proxy_frame.pack(pady=10, padx=20, fill="x")
        
        ctk.CTkLabel(
            proxy_frame,
            text="Прокси:",
            font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=(0, 10))
        
        self.proxy_entry = ctk.CTkEntry(
            proxy_frame,
            placeholder_text="http://user:pass@ip:port или socks5://ip:port",
            font=ctk.CTkFont(size=12)
        )
        self.proxy_entry.pack(side="left", fill="x", expand=True)
        
        # Кнопки управления
        buttons_frame = ctk.CTkFrame(self.edit_frame, fg_color="transparent")
        buttons_frame.pack(pady=(0, 15), padx=20)
        
        self.save_btn = ctk.CTkButton(
            buttons_frame,
            text="💾 Сохранить прокси",
            command=self._save_proxy,
            fg_color="#00AA00",
            hover_color="#008800",
            width=150
        )
        self.save_btn.pack(side="left", padx=5)
        
        self.remove_btn = ctk.CTkButton(
            buttons_frame,
            text="🗑️ Убрать прокси (Direct)",
            command=self._remove_proxy,
            fg_color="#DD0000",
            hover_color="#BB0000",
            width=180
        )
        self.remove_btn.pack(side="left", padx=5)
    
    def update_accounts(self, accounts: List[Dict[str, str]]) -> None:
        """
        Обновить список аккаунтов.
        accounts: [{"login": "vasya", "steamid": "...", "proxy": "http://...", "filepath": "..."}]
        """
        self.accounts = accounts
        
        # Очищаем список
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.account_buttons.clear()
        
        # Заполняем список
        if not accounts:
            no_accounts_label = ctk.CTkLabel(
                self.scroll_frame,
                text="Нет аккаунтов в папке maFiles",
                font=ctk.CTkFont(size=12),
                text_color="gray"
            )
            no_accounts_label.pack(pady=20)
            return
        
        for account in accounts:
            login = account["login"]
            proxy = account.get("proxy")
            
            # Статус прокси
            status_text = "🌐 Proxy" if proxy else "🏠 Direct IP"
            status_color = "#00AA00" if proxy else "#888888"
            
            # Кнопка аккаунта
            btn_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            btn_frame.pack(fill="x", pady=2)
            
            btn = ctk.CTkButton(
                btn_frame,
                text=f"{login}  •  {status_text}",
                fg_color="gray30",
                hover_color="gray20",
                anchor="w",
                command=lambda l=login, p=proxy: self._select_account(l, p)
            )
            btn.pack(side="left", fill="x", expand=True)
            
            self.account_buttons[login] = btn
    
    def _select_account(self, login: str, proxy: Optional[str]) -> None:
        """Выбрать аккаунт для редактирования."""
        self.selected_account = login
        self.selected_label.configure(text=f"Редактирование: {login}")
        
        # Заполняем поле прокси
        self.proxy_entry.delete(0, "end")
        if proxy:
            self.proxy_entry.insert(0, proxy)
        
        # Подсвечиваем выбранную кнопку
        for btn_login, btn in self.account_buttons.items():
            if btn_login == login:
                btn.configure(fg_color="#0066CC")
            else:
                btn.configure(fg_color="gray30")
    
    def _save_proxy(self) -> None:
        """Сохранить прокси для выбранного аккаунта."""
        if not self.selected_account:
            return
        
        proxy = self.proxy_entry.get().strip()
        if not proxy:
            return
        
        self.on_save_proxy(self.selected_account, proxy)
    
    def _remove_proxy(self) -> None:
        """Удалить прокси (перейти на Direct IP)."""
        if not self.selected_account:
            return
        
        self.on_remove_proxy(self.selected_account)

