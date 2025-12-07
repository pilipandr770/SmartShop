# 📸 Керівництво: Зберігання Зображень в SmartShop

## Статус
✅ **Зображення зберігаються в PostgreSQL база даних**
✅ **Зображення НЕ зникають після передеплою на Render**
✅ **Безкоштовно - використовує існуючу БД**

---

## Як Працює

SmartShop зберігає зображення в таблиці `images` в PostgreSQL БД з наступними полями:

```sql
CREATE TABLE images (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) UNIQUE,
    data BYTEA,                  -- Binary image data
    mime_type VARCHAR(50),       -- image/jpeg, image/png
    size INTEGER,                -- File size in bytes
    created_at TIMESTAMP
);
```

---

## Завантаження Зображень

### 1. Через Адмін Панель

**Додавання нового товару:**
1. Відкрийте http://localhost:5000/admin/products
2. Натисніть "➕ Додати товар"
3. Завантажте зображення двома способами:
   - **Файл:** Натисніть "Обрати файл" і виберіть зображення (PNG, JPG, GIF, WEBP)
   - **URL:** Вставте URL зображення з інтернету

**Редагування товару:**
1. Натисніть "✏️" біля товару
2. Оновіть зображення через файл або URL
3. Збережіть зміни

### 2. Підтримувані Формати

- ✅ PNG (image/png)
- ✅ JPEG/JPG (image/jpeg)
- ✅ GIF (image/gif)
- ✅ WEBP (image/webp)

**Обмеження:**
- Максимальний розмір: **16 MB**
- MIME type validation для безпеки

---

## Відображення Зображень

### В Шаблонах

Зображення відображаються через спеціальний endpoint `/images/<filename>`:

```html
<!-- Автоматично генерується -->
<img src="/images/15d6a55325aa4e19a2edf7f8bcb74181.png" alt="Product">
```

### Fallback Зображення

Якщо зображення відсутнє, показується placeholder з Pexels:

```html
<img src="{{ product.image_url or 'https://images.pexels.com/photos/3965545/pexels-photo-3965545.jpeg' }}">
```

---

## API Endpoints

### POST `/admin/upload`

Завантаження зображення (потрібна авторизація адміна):

```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const response = await fetch('/admin/upload', {
    method: 'POST',
    body: formData
});

const data = await response.json();
// { success: true, url: "/images/abc123.png", filename: "abc123.png", storage: "database" }
```

### GET `/images/<filename>`

Віддає зображення з бази даних:

```
GET /images/15d6a55325aa4e19a2edf7f8bcb74181.png
Content-Type: image/png
Content-Length: 1959969

[Binary image data]
```

---

## Налаштування

### .env Конфігурація

```bash
# Режим зберігання зображень
IMAGE_STORAGE=database    # PostgreSQL (рекомендовано)
# IMAGE_STORAGE=cloudinary  # Cloudinary CDN (потрібна реєстрація)
# IMAGE_STORAGE=local       # Local files (зникають на Render)

# Максимальний розмір файлу
MAX_CONTENT_LENGTH=16777216  # 16 MB в байтах
```

### Альтернатива: Cloudinary

Якщо потрібен CDN для швидшої доставки зображень:

1. Зареєструйтеся на https://cloudinary.com (безкоштовно 25GB)
2. Отримайте credentials в Dashboard
3. Додайте в `.env`:

```bash
IMAGE_STORAGE=cloudinary
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

4. Додайте ті самі змінні в Render Environment Variables

---

## Діагностика

### Перевірка Стану БД

Запустіть тестовий скрипт:

```bash
python test_image_upload.py
```

Виведе:
```
✅ Таблиця 'images' існує!
📸 Кількість зображень в БД: 15
🖼️  Список зображень:
  - abc123.png (1959969 bytes, image/png)
  - def456.jpg (845321 bytes, image/jpeg)
```

### Перевірка Логів

Запустіть додаток і перевірте повідомлення:

```bash
python app.py
```

Очікувані повідомлення:
```
💾 Using PostgreSQL database for permanent image storage
✅ PostgreSQL схема 'smartshop' готова
✅ Таблиця 'images' готова для зберігання зображень
```

### Проблеми і Рішення

#### ❌ "Зображення не відображається"

**Причина:** URL не вказаний або файл не завантажився

**Рішення:**
1. Перевірте логи в консолі браузера (F12)
2. Перевірте, чи є зображення в БД: `python test_image_upload.py`
3. Спробуйте завантажити менший файл (< 5 MB)

#### ❌ "413 Request Entity Too Large"

**Причина:** Файл більший за 16 MB

**Рішення:**
1. Стисніть зображення за допомогою https://tinypng.com
2. Або збільште `MAX_CONTENT_LENGTH` в `.env`

#### ❌ "Table 'images' doesn't exist"

**Причина:** Міграція не відбулася

**Рішення:**
```bash
python app.py  # Автоматично створить таблиці
```

---

## Продуктивність

### Розмір БД

PostgreSQL free tier на Render: **512 MB**

Середній розмір зображення: **~500 KB**

Можлива кількість зображень: **~1000 товарів**

### Оптимізація

1. **Стискайте зображення** перед завантаженням:
   - https://tinypng.com
   - https://squoosh.app

2. **Використовуйте WebP формат** (краще стискання):
   ```bash
   # Конвертація JPG → WebP
   cwebp input.jpg -q 80 -o output.webp
   ```

3. **Для великих каталогів** (>1000 товарів) використовуйте Cloudinary

---

## Міграція з Local → Database

Якщо раніше використовували local storage:

```python
# Скрипт міграції (запустити один раз)
from app import create_app
from extensions import db
from models.product import Image, Product
import os

app = create_app()
with app.app_context():
    upload_folder = app.config['UPLOAD_FOLDER']
    
    for filename in os.listdir(upload_folder):
        if filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            filepath = os.path.join(upload_folder, filename)
            
            with open(filepath, 'rb') as f:
                data = f.read()
            
            mime_type = f"image/{filename.split('.')[-1]}"
            
            image = Image(
                filename=filename,
                data=data,
                mime_type=mime_type,
                size=len(data)
            )
            db.session.add(image)
    
    db.session.commit()
    print("✅ Міграція завершена!")
```

---

## Production Deployment (Render)

Зображення автоматично зберігаються в БД на Render:

```bash
# 1. Додайте змінні середовища в Render
IMAGE_STORAGE=database
MAX_CONTENT_LENGTH=16777216

# 2. Передеплойте
git push origin main

# 3. Render автоматично:
#    - Створить таблицю images
#    - Збереже всі завантаження в БД
#    - Зображення НЕ зникнуть після redeploy
```

### Backup

PostgreSQL БД на Render автоматично створює backup.

Для додаткового backup:

```bash
# Export бази даних
pg_dump postgresql://USER:PASS@HOST/DB > backup.sql

# Restore
psql postgresql://USER:PASS@HOST/DB < backup.sql
```

---

## Підсумок

| Режим | Переваги | Недоліки | Рекомендація |
|-------|----------|----------|--------------|
| **database** | ✅ Безкоштовно<br>✅ Постійне зберігання<br>✅ Не потрібна реєстрація | ⚠️ Обмеження БД (512MB)<br>⚠️ Повільніше для великих файлів | ✅ Для малих/середніх сайтів |
| **cloudinary** | ✅ CDN delivery<br>✅ 25GB free<br>✅ Швидко | ❌ Потрібна реєстрація<br>❌ Залежність від 3rd party | ✅ Для великих каталогів |
| **local** | ✅ Просто | ❌ Зникають на Render<br>❌ Не для production | ❌ Тільки для dev |

**Наша конфігурація: `database` (PostgreSQL)** ✅

---

## Додаткові Посилання

- [PostgreSQL BYTEA Documentation](https://www.postgresql.org/docs/current/datatype-binary.html)
- [Flask File Uploads](https://flask.palletsprojects.com/en/2.3.x/patterns/fileuploads/)
- [Cloudinary Setup Guide](./CLOUDINARY_SETUP.md)
- [Image Optimization Guide](https://web.dev/fast/#optimize-your-images)
