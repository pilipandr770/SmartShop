"""
Видалення старих зображень (з БД або файлової системи) при заміні/видаленні
контенту, що на них посилався (товар, стаття блогу, налаштування сайту).

Раніше жила як closure всередині create_app() (app.py) - винесено сюди, щоб
blueprints могли її імпортувати без циклічного імпорту з app.py.
"""
import os
from urllib.parse import urlparse

from flask import current_app

from extensions import db


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
