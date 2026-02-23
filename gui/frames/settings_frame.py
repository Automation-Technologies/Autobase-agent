"""
Фрейм настроек.
"""
import customtkinter as ctk
from typing import Callable

from core.server_settings import ServerSettings


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

        # Agent Token
        ctk.CTkLabel(
            form_frame,
            text="Agent Token:",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        ).pack(pady=(30, 5), padx=30, fill="x")
        
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
            text="💡 Выдача токена происходит по команде /token в тг-боте @TAsteamBot",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        info_label.pack(pady=(0, 20))
    
    def _save_config(self) -> None:
        """Сохранить конфигурацию."""
        token = self.token_entry.get().strip()
        
        if not token:
            return
        
        self.on_save(token)
    
    def set_fields(self, token: str) -> None:
        """Установить значения полей."""
        self.token_entry.delete(0, "end")
        self.token_entry.insert(0, token)

