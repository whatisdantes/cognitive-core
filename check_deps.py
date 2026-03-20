"""Проверка установленных зависимостей для искусственного мозга."""

import sys
import importlib

print(f"Python: {sys.version}")
print(f"Путь: {sys.executable}")
print()

deps = [
    ("torch",                "PyTorch (CPU-only)"),
    ("numpy",                "NumPy"),
    ("jsonlines",            "jsonlines"),
    ("pymorphy3",            "pymorphy3"),
    ("razdel",               "razdel"),
    ("nltk",                 "NLTK"),
    ("navec",                "navec"),
    ("sentence_transformers","sentence-transformers"),
    ("open_clip",            "open-clip-torch (CLIP)"),
    ("PIL",                  "Pillow"),
    ("whisper",              "openai-whisper"),
    ("fitz",                 "pymupdf"),
    ("docx",                 "python-docx"),
    ("psutil",               "psutil"),
    ("tqdm",                 "tqdm"),
]

ok = []
fail = []

for module, name in deps:
    try:
        mod = importlib.import_module(module)
        version = getattr(mod, "__version__", "?")
        ok.append((name, version))
    except ImportError:
        fail.append(name)

print("=" * 52)
print("  ✅  УСТАНОВЛЕНО:")
print("=" * 52)
for name, ver in ok:
    print(f"  {name:<30} v{ver}")

if fail:
    print()
    print("=" * 52)
    print("  ❌  НЕ НАЙДЕНО:")
    print("=" * 52)
    for name in fail:
        print(f"  {name}")
else:
    print()
    print("  Все зависимости установлены корректно!")

# Проверка PyTorch CPU/CUDA
try:
    import torch
    print()
    print("=" * 52)
    print("  🔍  PyTorch детали:")
    print("=" * 52)
    print(f"  Версия:       {torch.__version__}")
    print(f"  CUDA доступна: {torch.cuda.is_available()}")
    print(f"  CPU потоков:  {torch.get_num_threads()}")
    # Быстрый тест
    x = torch.randn(3, 3)
    y = torch.mm(x, x)
    print(f"  Тест матрицы: OK (3x3 mm)")
except Exception as e:
    print(f"  PyTorch тест: ОШИБКА — {e}")

print()
