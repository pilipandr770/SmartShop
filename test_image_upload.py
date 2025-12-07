"""
Тестовий скрипт для перевірки завантаження зображень
"""
import os
from app import create_app
from extensions import db
from models.product import Image

def test_image_storage():
    """Перевірка зберігання та відображення зображень."""
    app = create_app()
    
    with app.app_context():
        # Перевірка таблиці images
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        
        print("\n🔍 Перевірка структури бази даних:")
        print(f"Схема: {app.config.get('DB_SCHEMA', 'public')}")
        
        # Отримуємо список таблиць
        tables = inspector.get_table_names(schema=app.config.get('DB_SCHEMA'))
        print(f"\n📋 Таблиці в базі даних ({len(tables)}):")
        for table in tables:
            print(f"  ✓ {table}")
        
        if 'images' in tables:
            print("\n✅ Таблиця 'images' існує!")
            
            # Перевірка структури таблиці
            columns = inspector.get_columns('images', schema=app.config.get('DB_SCHEMA'))
            print("\n📊 Структура таблиці 'images':")
            for col in columns:
                print(f"  - {col['name']}: {col['type']}")
            
            # Перевірка існуючих зображень
            image_count = Image.query.count()
            print(f"\n📸 Кількість зображень в БД: {image_count}")
            
            if image_count > 0:
                print("\n🖼️  Список зображень:")
                images = Image.query.limit(10).all()
                for img in images:
                    print(f"  - {img.filename} ({img.size} bytes, {img.mime_type})")
            
            # Перевірка конфігурації
            print(f"\n⚙️  IMAGE_STORAGE: {app.config.get('IMAGE_STORAGE')}")
            print(f"⚙️  UPLOAD_FOLDER: {app.config.get('UPLOAD_FOLDER')}")
            print(f"⚙️  MAX_CONTENT_LENGTH: {app.config.get('MAX_CONTENT_LENGTH') / 1024 / 1024} MB")
            
        else:
            print("\n❌ Таблиця 'images' не знайдена!")
            print("Запустіть app.py для створення таблиць")

if __name__ == '__main__':
    test_image_storage()
