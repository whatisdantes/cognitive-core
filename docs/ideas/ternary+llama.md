# 💡 IDEAS — Идеи для Cognitive Core

---

## 1. Тернарные микро-сети для лёгких модулей

### Суть
Написать собственные нейросети с тернарными весами (-1, 0, +1) для модулей Cognitive Core, которым не нужна полноценная LLM — только быстрое принятие решений.

### Зачем
- ⚡ Отклик ~1 мс вместо секунд через LLM
- 🧬 Биологически корректно: тернарные веса = возбуждение / торможение / покой нейрона
- 📦 Микро-размер: ~5-20 KB на модуль
- 🔋 Нулевая нагрузка на систему
- 🎛️ Полный контроль — можно обучать на своих данных без GPU

### Какие модули

| Модуль | Задача | Размер сети | Обучение |
|---|---|---|---|
| 🧭 Router (таламус) | Классификация входа → какой модуль обработает | ~5K весов | На синтетических примерах |
| 🎭 Амигдала | Определение эмоциональной окраски | ~10K весов | На размеченных данных с эмоциями |
| ⚡ Приоритизация | Ранжирование задач по важности | ~3K весов | На парах «задача — приоритет» |
| 🔍 Внимание | Scoring релевантности контекста | ~3K весов | На парах «запрос — контекст» |

### Реализация

```python
import numpy as np

class TernaryLinear:
    """Линейный слой с весами -1, 0, +1"""
    
    def __init__(self, in_features, out_features):
        self.weights = np.random.choice([-1, 0, 1], 
                                         size=(out_features, in_features))
    
    def forward(self, x):
        # Без умножений — только сложения и вычитания
        positive = np.dot((self.weights == 1).astype(np.float32), x)
        negative = np.dot((self.weights == -1).astype(np.float32), x)
        return positive - negative


class TernaryNetwork:
    def __init__(self, layer_sizes):
        self.layers = []
        for i in range(len(layer_sizes) - 1):
            self.layers.append(TernaryLinear(layer_sizes[i], layer_sizes[i+1]))
    
    def forward(self, x):
        for layer in self.layers:
            x = layer.forward(x)
            x = np.maximum(x, 0)  # ReLU
        return x

    def save(self, path):
        """Сохранение: 2 бита на вес, ~KB на модуль"""
        packed = np.array([l.weights for l in self.layers], dtype=object)
        np.save(path, packed)

    def load(self, path):
        packed = np.load(path, allow_pickle=True)
        for layer, w in zip(self.layers, packed):
            layer.weights = w
```

### Обучение маленьких сетей (на ноутбуке)

```python
class TernaryTrainer:
    def train(self, network, X, y, epochs=200, lr_flip_prob=0.05):
        best_loss = float('inf')
        best_weights = None
        
        for epoch in range(epochs):
            loss = self._compute_loss(network, X, y)
            
            if loss < best_loss:
                best_loss = loss
                best_weights = self._snapshot(network)
            
            # Мутация: случайно переключаем небольшой % весов
            for layer in network.layers:
                mask = np.random.random(layer.weights.shape) < lr_flip_prob
                flips = np.random.choice([-1, 0, 1], size=layer.weights.shape)
                layer.weights[mask] = flips[mask]
        
        self._restore(network, best_weights)
        return best_loss
```

### Шаги
1. Реализовать `TernaryNetwork` как базовый класс в Cognitive Core
2. Создать тернарный Router — первый модуль, маршрутизация входных сигналов
3. Подготовить синтетические данные для обучения роутера
4. Обучить и протестировать: вход → правильный модуль?
5. Повторить для амигдалы и приоритизации

---

## 2. Внедрение Llama через llama.cpp для reasoning-модулей

### Суть
Использовать квантованные модели (Llama 3 8B, Mistral 7B и др.) через `llama.cpp` для модулей, которым нужно настоящее языковое мышление — reasoning, генерация текста, суммаризация.

### Зачем
- 🧠 Работает **сейчас**, не нужно ждать BitNet 7B+ от Microsoft
- 💻 4-bit квантизация: Llama 8B ≈ 4.5 GB RAM, работает на CPU
- 🗣️ Реальный reasoning, генерация связного текста, понимание контекста
- 🔄 Абстракция `LLM Bridge` позволит заменить движок в будущем

### Какие модули

| Модуль | Задача | Почему LLM |
|---|---|---|
| 🧠 Префронтальная кора | Рассуждения, планирование, принятие решений | Нужна цепочка мыслей (CoT) |
| 💬 Зона Брока | Генерация текстового ответа | Нужна связная речь |
| 📖 Зона Вернике | Глубокое понимание запроса | Нужна семантика |
| 🧭 Гиппокамп (консолидация) | Суммаризация и сжатие воспоминаний | Нужно обобщение |

### Архитектура интеграции

```
┌─────────────── Cognitive Core ───────────────┐
│                                               │
│  Быстрый контур (тернарные микро-сети):       │
│  Router → Амигдала → Приоритеты → Внимание   │
│  Отклик: ~1-5 мс                             │
│           │                                   │
│           ▼                                   │
│  ┌─────────────────────────────┐             │
│  │      LLM Bridge (абстракция)│             │
│  ├─────────────────────────────┤             │
│  │  Реализация: llama.cpp      │             │
│  │  Модель: Llama 3.1 8B Q4_K_M│             │
│  │  RAM: ~4.5 GB               │             │
│  │  Отклик: ~2-10 сек (CPU)    │             │
│  └─────────────────────────────┘             │
│                                               │
│  Итого: ~4.5 GB RAM, 0 GPU                  │
└───────────────────────────────────────────────┘
```

### Реализация LLM Bridge

```python
from abc import ABC, abstractmethod
import subprocess
import json


class LLMBridge(ABC):
    """Абстрактный интерфейс — легко заменить движок в будущем"""
    
    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        pass
    
    @abstractmethod
    def reason(self, question: str, context: dict) -> str:
        pass
    
    @abstractmethod
    def summarize(self, text: str) -> str:
        pass


class LlamaCppBridge(LLMBridge):
    """Реализация через llama.cpp — работает сейчас"""
    
    def __init__(self, model_path: str, n_ctx: int = 2048):
        self.model_path = model_path
        self.n_ctx = n_ctx
        # Опционально: использовать llama-cpp-python для прямого биндинга
        # pip install llama-cpp-python
    
    def generate(self, prompt: str, max_tokens: int = 512) -> str:
        result = subprocess.run([
            'llama-cli',
            '-m', self.model_path,
            '-p', prompt,
            '-n', str(max_tokens),
            '--temp', '0.7',
            '-ngl', '0',  # 0 = только CPU
        ], capture_output=True, text=True)
        return result.stdout.strip()
    
    def reason(self, question: str, context: dict) -> str:
        prompt = self._build_reasoning_prompt(question, context)
        return self.generate(prompt, max_tokens=1024)
    
    def summarize(self, text: str) -> str:
        prompt = f"Summarize the following concisely:\n\n{text}\n\nSummary:"
        return self.generate(prompt, max_tokens=256)
    
    def _build_reasoning_prompt(self, question, context):
        return (
            f"Context:\n{json.dumps(context, indent=2)}\n\n"
            f"Question: {question}\n\n"
            f"Think step by step and provide your reasoning:\n"
        )


class FutureBitNetBridge(LLMBridge):
    """Заглушка на будущее — когда BitNet дозреет"""
    
    def generate(self, prompt, max_tokens=512):
        raise NotImplementedError("Ждём BitNet 7B+ от Microsoft 🙂")
```

### Рекомендуемые модели для старта

| Модель | Размер (Q4) | RAM | Качество reasoning | Рекомендация |
|---|---|---|---|---|
| Llama 3.1 8B | ~4.5 GB | ~5 GB | Хорошее | ⭐ Лучший баланс |
| Mistral 7B | ~4 GB | ~4.5 GB | Хорошее | Альтернатива |
| Phi-3 Mini 3.8B | ~2.2 GB | ~3 GB | Среднее | Для слабых машин |
| Qwen 2.5 7B | ~4 GB | ~4.5 GB | Хорошее | Хорош для рассуждений |

### Шаги
1. Установить `llama.cpp` и скачать модель Llama 3.1 8B Q4_K_M
2. Реализовать абстрактный `LLMBridge` в Cognitive Core
3. Написать `LlamaCppBridge` как первую реализацию
4. Подключить к модулю «Префронтальная кора» — reasoning
5. Подключить к «Зоне Брока» — генерация ответов
6. Добавить фоновую консолидацию памяти через `summarize()`

---

## Как идеи работают вместе

```
Запрос пользователя
       │
       ▼
 ┌─ Тернарный Router (~1 мс) ─────────────────────┐
 │  Классификация: это вопрос? команда? эмоция?     │
 └──────┬──────────────┬───────────────┬────────────┘
        │              │               │
   Простое          Эмоция         Сложное
        │              │               │
        ▼              ▼               ▼
   Шаблонный      Тернарная       LLM Bridge
   ответ          Амигдала        (llama.cpp)
   (~0 мс)        (~1 мс)         (~3-10 сек)
        │              │               │
        └──────────────┴───────────────┘
                       │
                       ▼
                   Ответ пользователю
```

**Принцип:** Не гонять всё через тяжёлую LLM. Тернарные микро-сети обрабатывают 70-80% запросов мгновенно, а LLM подключается только когда действительно нужно *думать*.

---

*Создано: 25 марта 2026*
