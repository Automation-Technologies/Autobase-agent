"""
Launcher для приложения с защитой мастер-паролем.
Обеспечивает шифрование/расшифровку папки maFiles.
"""
import os
import sys
import tkinter as tk
from tkinter import simpledialog, messagebox
import base64
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet, InvalidToken
import atexit
import signal

# --- НАСТРОЙКИ ---
TARGET_FOLDER = 'maFiles'
SALT_FILE = 'security.salt'
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
    """Функция для автоматического шифрования при выходе."""
    global _encryption_key
    if _encryption_key and TARGET_PATH.exists():
        try:
            print("\nЗавершение работы. Шифрование данных...")
            process_folder(TARGET_PATH, _encryption_key, encrypt=True)
            print("Данные защищены.")
        except Exception as e:
            print(f"Ошибка при шифровании при выходе: {e}")


def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения."""
    encrypt_on_exit()
    sys.exit(0)


def run_bot():
    """
    Запускает основное приложение.
    Эта функция будет импортирована из main.py
    """
    from main import Application
    
    # Передаем callback для шифрования при закрытии
    app = Application(on_close_callback=encrypt_on_exit)
    try:
        app.run()
    except KeyboardInterrupt:
        print("Приложение остановлено пользователем")
    except Exception as e:
        print(f"Ошибка приложения: {e}")
        raise


if __name__ == "__main__":
    # Регистрируем обработчики для автоматического шифрования при выходе
    atexit.register(encrypt_on_exit)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 1. Проверяем, первый ли это запуск
    first_run = not SALT_PATH.exists()
    
    # 2. Проверяем, зашифрована ли папка
    folder_encrypted = is_folder_encrypted(TARGET_PATH)
    
    # 3. Если это не первый запуск, но папка не зашифрована - это странно
    if not first_run and not folder_encrypted:
        # Возможно, пользователь удалил .enc файлы вручную
        # Считаем это первым запуском
        first_run = True
        if SALT_PATH.exists():
            SALT_PATH.unlink()
    
    # 4. Спрашиваем пароль через GUI
    pwd = ask_password(first_run)
    
    if not pwd:
        sys.exit(0)
    
    # 5. Генерируем ключ
    key = get_key(pwd, load_existing_salt=not first_run)
    
    if not key:
        messagebox.showerror("Ошибка", "Не удалось создать ключ.")
        sys.exit(1)
    
    # Сохраняем ключ глобально для шифрования при выходе
    _encryption_key = key
    
    # 6. Обработка шифрования/расшифровки
    if first_run:
        # Первый запуск: шифруем папку если она существует и не зашифрована
        if TARGET_PATH.exists() and not folder_encrypted:
            print("Шифрование данных...")
            if not process_folder(TARGET_PATH, key, encrypt=True):
                messagebox.showerror("Ошибка", "Не удалось зашифровать данные!")
                sys.exit(1)
            print("Данные зашифрованы.")
    else:
        # Последующие запуски: расшифровываем
        if folder_encrypted:
            print("Расшифровка данных...")
            if not process_folder(TARGET_PATH, key, encrypt=False):
                messagebox.showerror("Ошибка", "Неверный пароль или данные повреждены!")
                sys.exit(1)
            print("Данные расшифрованы.")
    
    # 7. Запускаем основное приложение
    try:
        print("Пароль принят. Запуск приложения...")
        run_bot()
    except Exception as e:
        messagebox.showerror("Ошибка приложения", f"Произошла ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 8. При выходе шифруем обратно
        encrypt_on_exit()

