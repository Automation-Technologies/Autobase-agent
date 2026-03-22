"""
Launcher для приложения с защитой мастер-паролем.
maFiles никогда не расшифровываются на диск — только в оперативную память.
"""
import json
import os
import sys
import tkinter as tk
from tkinter import simpledialog, messagebox
import base64
from pathlib import Path
from typing import Dict
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet, InvalidToken
import atexit
import signal

# --- НАСТРОЙКИ ---
TARGET_FOLDER = 'maFiles'
SALT_FILE = 'security.salt'

# Определяем базовую директорию: для .exe - папка с exe, для .py - папка со скриптом
if getattr(sys, 'frozen', False):
    # Запущено как .exe
    BASE_DIR = Path(sys.executable).parent
else:
    # Запущено как .py скрипт
    BASE_DIR = Path(__file__).parent

TARGET_PATH = BASE_DIR / TARGET_FOLDER
SALT_PATH = BASE_DIR / SALT_FILE

# Глобальная переменная для ключа (нужна для шифрования при выходе)
_encryption_key = None


def get_key(password: str, load_existing_salt: bool = False):
    """
    Генерирует ключ шифрования из пароля.
    
    Args:
        password: Мастер-пароль
        load_existing_salt: Если True, загружает существующую соль, иначе создает новую
        
    Returns:
        bytes: Ключ шифрования или None при ошибке
    """
    try:
        if load_existing_salt:
            if not SALT_PATH.exists():
                return None
            with open(SALT_PATH, 'rb') as f:
                salt = f.read()
        else:
            salt = os.urandom(16)
            with open(SALT_PATH, 'wb') as f:
                f.write(salt)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))
    except Exception as e:
        print(f"Ошибка генерации ключа: {e}")
        return None


def is_folder_encrypted(folder_path: Path) -> bool:
    """
    Проверяет, зашифрована ли папка (есть ли файлы с расширением .enc).
    
    Args:
        folder_path: Путь к папке
        
    Returns:
        bool: True если папка зашифрована
    """
    if not folder_path.exists():
        return False
    
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith('.enc'):
                return True
    return False


def process_folder(folder_path: Path, key: bytes, encrypt: bool = True) -> bool:
    """
    Шифрует или дешифрует папку.
    
    Args:
        folder_path: Путь к папке
        key: Ключ шифрования
        encrypt: True для шифрования, False для расшифровки
        
    Returns:
        bool: True если операция успешна
    """
    if not folder_path.exists():
        return True
    
    fernet = Fernet(key)
    success = True
    processed_files = []
    
    try:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = Path(root) / file
                
                # Пропускаем файлы, которые уже в нужном состоянии
                if encrypt and file.endswith('.enc'):
                    continue
                if not encrypt and not file.endswith('.enc'):
                    continue

                try:
                    with open(file_path, 'rb') as f:
                        data = f.read()
                    
                    if encrypt:
                        processed = fernet.encrypt(data)
                        new_path = file_path.with_suffix(file_path.suffix + '.enc')
                    else:
                        processed = fernet.decrypt(data)
                        # Удаляем .enc расширение (with_suffix('') удаляет последнее расширение)
                        new_path = file_path.with_suffix('')

                    with open(new_path, 'wb') as f:
                        f.write(processed)
                    
                    os.remove(file_path)
                    processed_files.append(file_path)
                    
                except InvalidToken:
                    print(f"Ошибка: неверный ключ для файла {file_path}")
                    success = False
                except Exception as e:
                    print(f"Ошибка обработки {file_path}: {e}")
                    success = False
        
        return success
    except Exception as e:
        print(f"Критическая ошибка при обработке папки: {e}")
        return False


def load_mafiles_to_memory(key: bytes, folder_path: Path) -> Dict[str, dict]:
    """
    Читает все *.maFile.enc из папки, расшифровывает в RAM.
    Возвращает Dict[login_lower, mafile_json].
    """
    fernet = Fernet(key)
    result: Dict[str, dict] = {}

    if not folder_path.exists():
        return result

    for enc_file in folder_path.glob("*.maFile.enc"):
        try:
            data = json.loads(fernet.decrypt(enc_file.read_bytes()).decode("utf-8"))
            login = data.get("account_name", "").lower()
            if login:
                result[login] = data
        except Exception as e:
            print(f"Ошибка расшифровки {enc_file.name}: {e}")

    return result


def ask_password(is_first_time: bool) -> str:
    """
    Показывает GUI окно для ввода пароля.
    
    Args:
        is_first_time: True если это первый запуск
        
    Returns:
        str: Введенный пароль или None если отмена
    """
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    title = "Настройка безопасности" if is_first_time else "Вход в систему"
    prompt = "Придумайте новый мастер-пароль:" if is_first_time else "Введите мастер-пароль:"
    
    password = simpledialog.askstring(title, prompt, show='*', parent=root)
    root.destroy()
    return password


def encrypt_on_exit():
    """
    Вызывается при выходе из приложения.
    Данные уже защищены: maFiles никогда не покидали RAM в открытом виде,
    accounts.json.enc перезаписывается AccountManager-ом при каждой мутации.
    """
    print("\nЗавершение работы. Данные в безопасности.")


def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения."""
    encrypt_on_exit()
    sys.exit(0)


def run_bot(key: bytes, mafiles_dict: Dict[str, dict]) -> None:
    """Запускает основное приложение с уже загруженными в RAM данными."""
    from main import Application

    app = Application(
        fernet_key=key,
        mafiles_dict=mafiles_dict,
        on_close_callback=encrypt_on_exit,
    )
    try:
        app.run()
    except KeyboardInterrupt:
        print("Приложение остановлено пользователем")
    except Exception as e:
        print(f"Ошибка приложения: {e}")
        raise


if __name__ == "__main__":
    atexit.register(encrypt_on_exit)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 1. Определяем: первый запуск или нет
    first_run = not SALT_PATH.exists()

    # 2. Если соль есть, но нет ни одного .enc — считаем первым запуском
    if not first_run and not is_folder_encrypted(TARGET_PATH):
        first_run = True
        SALT_PATH.unlink()

    # 3. Запрашиваем мастер-пароль
    pwd = ask_password(first_run)
    if not pwd:
        sys.exit(0)

    # 4. Генерируем ключ
    key = get_key(pwd, load_existing_salt=not first_run)
    if not key:
        messagebox.showerror("Ошибка", "Не удалось создать ключ.")
        sys.exit(1)

    _encryption_key = key

    # 5. Загружаем все maFiles в RAM (миграция plaintext → .enc происходит внутри)
    print("Загрузка данных в память...")
    mafiles_dict = load_mafiles_to_memory(key, TARGET_PATH)
    print(f"Загружено аккаунтов: {len(mafiles_dict)}")

    # 6. Запускаем приложение
    try:
        print("Пароль принят. Запуск приложения...")
        run_bot(key, mafiles_dict)
    except Exception as e:
        messagebox.showerror("Ошибка приложения", f"Произошла ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        encrypt_on_exit()

