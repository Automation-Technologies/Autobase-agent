"""
Фрейм дашборда.
"""
import customtkinter as ctk
from typing import Callable


class DashboardFrame(ctk.CTkFrame):
    """Главный дашборд агента."""
    
    def __init__(self, master, on_start: Callable, on_stop: Callable, on_ingest: Callable):
        super().__init__(master, fg_color="transparent")
        
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_ingest = on_ingest
        
        self.is_running = False
        
        self._create_widgets()
    
    def _create_widgets(self) -> None:
        """Создать виджеты."""
        # Контейнер для статуса
        status_frame = ctk.CTkFrame(self, corner_radius=10)
        status_frame.pack(pady=(0, 20), padx=20, fill="x")
        
        # Статус подключения
        self.status_label = ctk.CTkLabel(
            status_frame,
            text="● ОТКЛЮЧЕНО",
            text_color="#FF4444",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        self.status_label.pack(pady=20)
        
        # Кнопка запуска/остановки
        self.toggle_btn = ctk.CTkButton(
            self,
            text="▶ ЗАПУСТИТЬ АГЕНТА",
            height=60,
            fg_color="#00AA00",
            hover_color="#008800",
            font=ctk.CTkFont(size=18, weight="bold"),
            command=self._toggle_agent
        )
        self.toggle_btn.pack(pady=10, padx=50, fill="x")
        
        # Кнопка добавления аккаунтов
        self.ingest_btn = ctk.CTkButton(
            self,
            text="➕ Добавить новые аккаунты (Ingestion)",
            height=40,
            fg_color="#0066CC",
            hover_color="#0055AA",
            font=ctk.CTkFont(size=14),
            command=self._trigger_ingestion
        )
        self.ingest_btn.pack(pady=5, padx=50, fill="x")
        
        # Лог событий
        log_label = ctk.CTkLabel(
            self,
            text="Журнал событий:",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        log_label.pack(pady=(20, 5), padx=20, fill="x")
        
        self.log_box = ctk.CTkTextbox(self, height=250, font=ctk.CTkFont(size=11))
        self.log_box.pack(pady=(0, 20), padx=20, fill="both", expand=True)
        self.log_box.insert("0.0", "🟢 Система готова к работе.\n")
        self.log_box.configure(state="disabled")
    
    def _toggle_agent(self) -> None:
        """Переключить состояние агента."""
        if self.is_running:
            self.on_stop()
        else:
            self.on_start()
    
    def _trigger_ingestion(self) -> None:
        """Запустить процесс добавления аккаунтов."""
        self.on_ingest()
    
    def update_status(self, connected: bool) -> None:
        """Обновить статус подключения."""
        self.is_running = connected
        
        if connected:
            self.status_label.configure(
                text="● ПОДКЛЮЧЕНО",
                text_color="#00FF00"
            )
            self.toggle_btn.configure(
                text="■ ОСТАНОВИТЬ АГЕНТА",
                fg_color="#DD0000",
                hover_color="#BB0000"
            )
        else:
            self.status_label.configure(
                text="● ОТКЛЮЧЕНО",
                text_color="#FF4444"
            )
            self.toggle_btn.configure(
                text="▶ ЗАПУСТИТЬ АГЕНТА",
                fg_color="#00AA00",
                hover_color="#008800"
            )
    
    def add_log(self, message: str) -> None:
        """Добавить сообщение в лог."""
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

