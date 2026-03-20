@echo off
chcp 65001 >nul
echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║     🧠  УСТАНОВКА ЗАВИСИМОСТЕЙ ИСКУССТВЕННОГО МОЗГА  ║
echo ║         AMD Ryzen 7 5700X + 32GB RAM (CPU-only)      ║
echo ╚══════════════════════════════════════════════════════╝
echo.

:: ─── Проверка Python ─────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден. Установите Python 3.10+ и добавьте в PATH.
    pause
    exit /b 1
)
echo [OK] Python найден:
python --version
echo.

:: ─── Создание виртуального окружения ─────────────────────────────────────────
if not exist "venv" (
    echo [1/8] Создание виртуального окружения venv...
    python -m venv venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать venv.
        pause
        exit /b 1
    )
    echo [OK] venv создан.
) else (
    echo [1/8] venv уже существует, пропускаем.
)
echo.

:: ─── Активация venv ──────────────────────────────────────────────────────────
echo [2/8] Активация виртуального окружения...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ОШИБКА] Не удалось активировать venv.
    pause
    exit /b 1
)
echo [OK] venv активирован.
echo.

:: ─── Обновление pip ──────────────────────────────────────────────────────────
echo [3/8] Обновление pip...
python -m pip install --upgrade pip --quiet
echo [OK] pip обновлён.
echo.

:: ─── PyTorch CPU-only ────────────────────────────────────────────────────────
echo [4/8] Установка PyTorch (CPU-only build)...
echo       Размер: ~200 MB. Используется CPU-индекс PyTorch.
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить PyTorch.
    pause
    exit /b 1
)
echo [OK] PyTorch (CPU-only) установлен.
echo.

:: ─── Базовые зависимости ─────────────────────────────────────────────────────
echo [5/8] Установка базовых зависимостей...
echo       (numpy, jsonlines, pymorphy3, razdel, nltk, navec, pillow, psutil, tqdm, pymupdf, python-docx)
pip install ^
    numpy>=1.26.0 ^
    jsonlines>=4.0.0 ^
    pymorphy3>=1.0.0 ^
    razdel>=0.5.0 ^
    nltk>=3.8.0 ^
    navec>=0.10.0 ^
    pillow>=10.0.0 ^
    psutil>=5.9.0 ^
    tqdm>=4.66.0 ^
    pymupdf>=1.24.0 ^
    python-docx>=1.1.0
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить базовые зависимости.
    pause
    exit /b 1
)
echo [OK] Базовые зависимости установлены.
echo.

:: ─── Sentence Transformers (Text Encoder ~1.3 GB) ────────────────────────────
echo [6/8] Установка sentence-transformers (Text Encoder)...
echo       Размер пакета: ~50 MB. Модель (~1.3 GB) загружается при первом запуске.
pip install sentence-transformers>=2.7.0
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить sentence-transformers.
    pause
    exit /b 1
)
echo [OK] sentence-transformers установлен.
echo.

:: ─── OpenCLIP (Vision Encoder ~600 MB) ───────────────────────────────────────
echo [7/8] Установка open-clip-torch (Vision Encoder)...
echo       Размер пакета: ~30 MB. Модель CLIP ViT-B/32 (~600 MB) загружается при первом запуске.
pip install open-clip-torch>=2.24.0
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить open-clip-torch.
    pause
    exit /b 1
)
echo [OK] open-clip-torch установлен.
echo.

:: ─── OpenAI Whisper (Audio ASR ~1.5 GB) ──────────────────────────────────────
echo [8/8] Установка openai-whisper (Audio Encoder)...
echo       Размер пакета: ~10 MB. Модель Whisper medium (~1.5 GB) загружается при первом запуске.
pip install openai-whisper>=20231117
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить openai-whisper.
    pause
    exit /b 1
)
echo [OK] openai-whisper установлен.
echo.

:: ─── NLTK данные ─────────────────────────────────────────────────────────────
echo Загрузка NLTK данных (punkt, stopwords)...
python -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('stopwords', quiet=True); nltk.download('punkt_tab', quiet=True); print('[OK] NLTK данные загружены.')"
echo.

:: ─── Итог ────────────────────────────────────────────────────────────────────
echo ╔══════════════════════════════════════════════════════╗
echo ║              ✅  УСТАНОВКА ЗАВЕРШЕНА                 ║
echo ╠══════════════════════════════════════════════════════╣
echo ║  Установлено:                                        ║
echo ║   • PyTorch (CPU-only)                               ║
echo ║   • sentence-transformers  (модель ~1.3 GB при запуске) ║
echo ║   • open-clip-torch CLIP   (модель ~600 MB при запуске) ║
echo ║   • openai-whisper medium  (модель ~1.5 GB при запуске) ║
echo ║   • pymorphy3, razdel, navec, nltk                   ║
echo ║   • pymupdf, python-docx, pillow                     ║
echo ║   • psutil, tqdm, jsonlines, numpy                   ║
echo ╠══════════════════════════════════════════════════════╣
echo ║  ⚠  Модели (~3.4 GB суммарно) загрузятся            ║
echo ║     автоматически при первом запуске мозга.          ║
echo ║                                                      ║
echo ║  Для запуска:                                        ║
echo ║    venv\Scripts\activate                             ║
echo ║    python main.py                                    ║
echo ╚══════════════════════════════════════════════════════╝
echo.
pause
