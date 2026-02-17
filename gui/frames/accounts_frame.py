"""
Фрейм управления аккаунтами и прокси.
"""
import customtkinter as ctk
from pathlib import Path
from typing import Callable, List, Dict, Optional
import json
import shutil

from tkinterdnd2 import DND_FILES  # type: ignore


class AccountsFrame(ctk.CTkFrame):
    """Управление аккаунтами, паролями и привязками прокси."""
    
    def __init__(
        self,
        master,
        mafiles_dir: Path,
        on_save_proxy: Callable,
        on_remove_proxy: Callable,
        on_save_account_credentials: Callable
    ):
        super().__init__(master, fg_color="transparent")
        
        self.mafiles_dir = mafiles_dir
        self.on_save_proxy = on_save_proxy
        self.on_remove_proxy = on_remove_proxy
        self.on_save_account_credentials = on_save_account_credentials
        
        self.accounts: List[Dict[str, str]] = []
        self.selected_account: Optional[str] = None
        self.account_buttons: Dict[str, ctk.CTkButton] = {}

        self.dropped_mafile_path: Optional[Path] = None
        self.dropped_login: Optional[str] = None
        
        self._create_widgets()
    
    def _create_widgets(self) -> None:
        """Создать виджеты."""
        # Блок добавления аккаунтов
        title_label = ctk.CTkLabel(
            self,
            text="Добавление аккаунтов",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_label.pack(pady=(0, 10))
        
        info_label = ctk.CTkLabel(
            self,
            text="Перетащите файл .maFile в зону ниже и введите пароль аккаунта",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        info_label.pack(pady=(0, 10))

        self.drop_frame = ctk.CTkFrame(self, corner_radius=10, border_width=2)
        self.drop_frame.pack(padx=20, pady=(0, 10), fill="x")

        self.drop_label = ctk.CTkLabel(
            self.drop_frame,
            text="🛈 Перетащите сюда .maFile из Steam Desktop Authenticator",
            font=ctk.CTkFont(size=13)
        )
        self.drop_label.pack(pady=20, padx=20)

        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind("<<Drop>>", self._on_drop_mafile)

        password_frame = ctk.CTkFrame(self, fg_color="transparent")
        password_frame.pack(padx=20, pady=(0, 10), fill="x")

        ctk.CTkLabel(
            password_frame,
            text="Пароль аккаунта:",
            font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=(0, 10))

        self.password_entry = ctk.CTkEntry(
            password_frame,
            show="*",
            font=ctk.CTkFont(size=12)
        )
        self.password_entry.pack(side="left", fill="x", expand=True)

        self.add_account_btn = ctk.CTkButton(
            self,
            text="➕ Сохранить аккаунт",
            command=self._save_account_credentials,
            fg_color="#00AA00",
            hover_color="#008800",
            width=180
        )
        self.add_account_btn.pack(pady=(0, 20))

        # Блок управления прокси
        proxy_title_label = ctk.CTkLabel(
            self,
            text="Управление Прокси",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        proxy_title_label.pack(pady=(0, 10))
        
        proxy_info_label = ctk.CTkLabel(
            self,
            text="Выберите аккаунт из списка ниже, чтобы настроить прокси",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        proxy_info_label.pack(pady=(0, 20))
        
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
        
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.account_buttons.clear()
        
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
            
            status_text = "🌐 Proxy" if proxy else "🏠 Direct IP"
            
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
        
        self.proxy_entry.delete(0, "end")
        if proxy:
            self.proxy_entry.insert(0, proxy)
        
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
    
    def _on_drop_mafile(self, event) -> None:
        """Обработчик перетаскивания maFile в зону drop."""
        raw_data = event.data
        if not raw_data:
            return

        cleaned = raw_data.strip()
        if cleaned.startswith("{") and cleaned.endswith("}"):
            cleaned = cleaned[1:-1]

        source_path = Path(cleaned)
        if source_path.suffix != ".maFile":
            return

        self.mafiles_dir.mkdir(parents=True, exist_ok=True)
        destination_path = self.mafiles_dir / source_path.name

        shutil.copy2(str(source_path), str(destination_path))

        try:
            with open(destination_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            self.drop_label.configure(text="❌ Не удалось прочитать maFile")
            return

        login = data.get("account_name")
        if not login:
            self.drop_label.configure(text="❌ maFile не содержит account_name")
            return

        self.dropped_mafile_path = destination_path
        self.dropped_login = login

        self.drop_label.configure(
            text=f"✅ Файл: {destination_path.name}  •  Логин: {login}"
        )
    
    def _save_account_credentials(self) -> None:
        """Сохранить пароль и maFile для добавленного аккаунта."""
        if self.dropped_mafile_path is None:
            return
        if self.dropped_login is None:
            return

        password = self.password_entry.get()
        if not password:
            return

        self.on_save_account_credentials(
            self.dropped_login,
            password,
            str(self.dropped_mafile_path)
        )

        self.password_entry.delete(0, "end")
        self.dropped_mafile_path = None
        self.dropped_login = None
        self.drop_label.configure(
            text="🛈 Перетащите сюда .maFile из Steam Desktop Authenticator"
        )
