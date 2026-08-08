"""
Видалення старих зображень (з БД або файлової системи) при заміні/видаленні
контенту, що на них посилався (товар, стаття блогу, налаштування сайту).

Раніше жила як closure всередині create_app() (app.py) - винесено сюди, щоб
blueprints могли її імпортувати без циклічного імпорту з app.py.
"""
import os
from urllib.parse import urlparse

from flask import current_app
from werkzeug.utils import secure_filename

from extensions import db

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_MIME_TYPES = {
    'image/png',
    'image/jpeg',
    'image/gif',
    'image/webp',
}


def allowed_file(filename, content_type=None):
    """Validate file extension and optionally MIME type."""
    if not filename or '.' not in filename:
        return False

    filename = secure_filename(filename)

    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False

    if content_type and content_type not in ALLOWED_MIME_TYPES:
        return False

    return True


def delete_old_image(old_image_url):
    """Видаляє старе зображення з бази даних або файлової системи.

    old_image_url може бути як відносним шляхом ('/images/xxx.png'),
    так і повним URL ('http://host/images/xxx.png' - саме так їх
    повертає /admin/upload через url_for(..., _external=True)), тому
    порівнюємо лише шлях (без хоста/схеми), а не сирий рядок цілком.
    """
    if not old_image_url:
        return False

    from models.product import Image

    path = urlparse(old_image_url).path

    try:
        if path.startswith("/images/"):
            filename = path.split("/images/")[-1]
            old_image = Image.query.filter_by(filename=filename).first()

            if old_image:
                db.session.delete(old_image)
                db.session.commit()
                current_app.logger.info(f"🗑️ Deleted old image from database: {filename}")
                return True

        elif path.startswith("/static/uploads/"):
            filename = path.split("/static/uploads/")[-1]
            file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)

            if os.path.exists(file_path):
                os.remove(file_path)
                current_app.logger.info(f"🗑️ Deleted old local file: {filename}")
                return True

    except Exception as e:
        current_app.logger.warning(f"⚠️ Could not delete old image {old_image_url}: {e}")

    return False
