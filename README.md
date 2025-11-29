# SmartShop AI (Flask магазин-конструктор)

Готовий мінімальний проєкт магазину на Flask з адмінкою:

- головна сторінка з динамічними блоками;
- адмін-панель для редагування блоків, соцмереж, інструкцій ІІ-продавця;
- створення категорій і товарів;
- базова статистика магазину на основі таблиці `orders` (для подальшої інтеграції зі Stripe).

## Запуск локально (Windows + PowerShell)

```powershell
cd C:\Users\ПК
# розпакуйте архів smartshop_ai.zip в цю папку

cd .\smartshop_ai

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r .\requirements.txt

# створіть файл .env на основі .env.example
# і при бажанні змініть ADMIN_USERNAME / ADMIN_PASSWORD

python .\app.py
```

Потім відкрийте в браузері:

- сайт: http://127.0.0.1:5000/
- адмінка: http://127.0.0.1:5000/admin/login
