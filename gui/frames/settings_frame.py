"""
Фрейм настроек.
"""
import customtkinter as ctk
from typing import Callable


class SettingsFrame(ctk.CTkFrame):
    """Настройки подключения к серверу."""
    
    def __init__(self, master, on_save: Callable):
        super().__init__(master, fg_color="transparent")
        
        self.on_save = on_save
        
        self._create_widgets()
    
    def _create_widgets(self) -> None:
        """Создать виджеты."""
        # Заголовок
        title_label = ctk.CTkLabel(
            self,
            text="Настройки подключения",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_label.pack(pady=(0, 30))
        
        # Контейнер для полей
        form_frame = ctk.CTkFrame(self, corner_radius=10)
        form_frame.pack(pady=20, padx=50, fill="both", expand=True)
        
        # Server IP
        ctk.CTkLabel(
            form_frame,
            text="Server IP (WebSocket URL):",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        ).pack(pady=(30, 5), padx=30, fill="x")
        
        self.server_ip_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="ws://autobase.example.com:8080",
            height=40,
            font=ctk.CTkFont(size=13)
        )
        self.server_ip_entry.pack(pady=(0, 20), padx=30, fill="x")
        
        # Agent Token
        ctk.CTkLabel(
            form_frame,
            text="Agent Token (UUID):",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        ).pack(pady=(10, 5), padx=30, fill="x")
        
        self.token_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            height=40,
            font=ctk.CTkFont(size=13)
        )
        self.token_entry.pack(pady=(0, 20), padx=30, fill="x")
        
        # Кнопка сохранения
        self.save_btn = ctk.CTkButton(
            form_frame,
            text="💾 Сохранить настройки",
            height=50,
            fg_color="#00AA00",
            hover_color="#008800",
            font=ctk.CTkFont(size=16, weight="bold"),
            command=self._save_config
        )
        self.save_btn.pack(pady=(20, 30), padx=30, fill="x")
        
        # Информация
        info_label = ctk.CTkLabel(
            form_frame,
            text="💡 Эти данные выдаются при регистрации агента в AutoBase",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        info_label.pack(pady=(0, 20))
    
    def _save_config(self) -> None:
        """Сохранить конфигурацию."""
        server_ip = self.server_ip_entry.get().strip()
        token = self.token_entry.get().strip()
        
        if not server_ip or not token:
            # TODO: показать сообщение об ошибке
            return
        
        self.on_save(server_ip, token)
    
    def set_fields(self, server_ip: str, token: str) -> None:
        """Установить значения полей."""
        self.server_ip_entry.delete(0, "end")
        self.server_ip_entry.insert(0, server_ip)
        
        self.token_entry.delete(0, "end")
        self.token_entry.insert(0, token)

