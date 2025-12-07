"""Тест чатбота и OpenAI клиента."""
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

print("=== Проверка OpenAI настроек ===\n")

# Проверка наличия API ключа
api_key = os.environ.get("OPENAI_API_KEY", "")
if api_key:
    print(f"✅ OPENAI_API_KEY найден (длина: {len(api_key)} символов)")
    print(f"   Начало: {api_key[:20]}...")
else:
    print("❌ OPENAI_API_KEY не найден в .env")
    exit(1)

# Проверка импорта OpenAI
try:
    from openai import OpenAI
    print("✅ Библиотека OpenAI успешно импортирована")
except ImportError as e:
    print(f"❌ Ошибка импорта OpenAI: {e}")
    exit(1)

# Проверка создания клиента
try:
    client = OpenAI(api_key=api_key)
    print("✅ OpenAI клиент создан успешно")
except Exception as e:
    print(f"❌ Ошибка создания клиента: {e}")
    exit(1)

# Проверка работы API
print("\n=== Тестовый запрос к OpenAI API ===\n")
try:
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Ти — ввічливий помічник магазину."},
            {"role": "user", "content": "Привіт! Як справи?"},
        ],
        max_tokens=50,
        temperature=0.7,
    )
    
    message = response.choices[0].message.content
    print(f"✅ OpenAI API відповів успішно:")
    print(f"   Відповідь: {message}\n")
    
except Exception as e:
    print(f"❌ Помилка запиту до OpenAI API: {e}\n")
    import traceback
    traceback.print_exc()
    exit(1)

# Проверка настроек AI в базе данных
print("=== Проверка настроек AI в базе данных ===\n")
try:
    from extensions import db
    from models.blog import AISettings
    from app import create_app
    
    app = create_app()
    with app.app_context():
        ai_settings = AISettings.query.first()
        
        if ai_settings:
            print(f"✅ AISettings найдены в БД:")
            print(f"   - Чатбот включен: {ai_settings.chatbot_enabled}")
            print(f"   - Имя чатбота: {ai_settings.chatbot_name}")
            print(f"   - Max tokens: {ai_settings.chatbot_max_tokens}")
            print(f"   - Temperature: {ai_settings.chatbot_temperature}")
            
            if not ai_settings.chatbot_enabled:
                print("\n⚠️  ВНИМАНИЕ: Чатбот ВЫКЛЮЧЕН в настройках!")
                print("   Включите его в админке: /admin/ai")
        else:
            print("⚠️  AISettings не найдены в БД. Будут созданы при первом запросе.")
            
except Exception as e:
    print(f"❌ Ошибка проверки БД: {e}")
    import traceback
    traceback.print_exc()

print("\n=== Итог ===")
print("✅ Все проверки пройдены! Чатбот должен работать.")
print("   Если чатбот не отвечает, проверьте:")
print("   1. Открыта ли кнопка чата (🤖) в правом нижнем углу")
print("   2. Нет ли ошибок в консоли браузера (F12)")
print("   3. Включен ли чатбот в админке (/admin/ai)")
