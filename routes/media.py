"""
Завантаження зображень у БД (або Cloudinary, якщо налаштовано) + віддача
зображень, збережених у БД. Наскрізний сервіс - викликається з товарів,
категорій, блоків головної сторінки та загальних налаштувань сайту через
той самий /admin/upload (тому окремий blueprint, а не частина products.py
чи site_settings.py).

Винесено з app.py ("АДМІНКА: ЗАВАНТАЖЕННЯ ЗОБРАЖЕНЬ" + "СЕРВІС ЗОБРАЖЕНЬ
З БД") як частина Phase 2 плану (SWOT 2026-08-08).
"""
import io
import uuid

from flask import Blueprint, current_app, g, jsonify, request, send_file, url_for
from flask_babel import gettext as _
from werkzeug.utils import secure_filename

from extensions import db
from services.admin_auth import admin_required
from services.image_storage import allowed_file

try:
    import cloudinary
    import cloudinary.uploader
    CLOUDINARY_AVAILABLE = True
except ImportError:
    CLOUDINARY_AVAILABLE = False

media_bp = Blueprint("media", __name__)


@media_bp.route("/admin/upload", methods=["POST"])
@admin_required
def admin_upload():
    """Завантаження зображення в базу даних PostgreSQL."""
    if 'file' not in request.files:
        return jsonify({"error": _("Файл не обрано")}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": _("Файл не обрано")}), 400

    content_type = file.content_type

    if file and allowed_file(file.filename, content_type):
        from models.product import Image

        secured_name = secure_filename(file.filename)
        ext = secured_name.rsplit('.', 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"

        file_data = file.read()
        file_size = len(file_data)

        max_size = current_app.config.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024)
        if file_size > max_size:
            return jsonify({"error": f"Файл занадто великий (max {max_size // 1024 // 1024} MB)"}), 400

        if current_app.config.get("IMAGE_STORAGE") == "cloudinary" and CLOUDINARY_AVAILABLE:
            if all([current_app.config.get("CLOUDINARY_CLOUD_NAME"),
                   current_app.config.get("CLOUDINARY_API_KEY"),
                   current_app.config.get("CLOUDINARY_API_SECRET")]):
                try:
                    file.seek(0)
                    upload_result = cloudinary.uploader.upload(
                        file,
                        folder="smartshop",
                        public_id=filename.rsplit('.', 1)[0],
                        resource_type="image",
                        allowed_formats=['png', 'jpg', 'jpeg', 'gif', 'webp']
                    )

                    file_url = upload_result['secure_url']

                    return jsonify({
                        "success": True,
                        "url": file_url,
                        "filename": filename,
                        "storage": "cloudinary"
                    })

                except Exception as e:
                    print(f"Cloudinary upload error: {e}")
                    # Fallback to database

        try:
            existing_image = Image.query.filter_by(filename=filename).first()
            if existing_image:
                existing_image.data = file_data
                existing_image.mime_type = content_type
                existing_image.size = file_size
                image = existing_image
            else:
                image = Image(
                    store_id=g.store.id,
                    filename=filename,
                    data=file_data,
                    mime_type=content_type,
                    size=file_size
                )
                db.session.add(image)

            db.session.commit()

            file_url = url_for('.serve_image', filename=filename, _external=True)

            return jsonify({
                "success": True,
                "url": file_url,
                "filename": filename,
                "storage": "database",
                "size": file_size
            })

        except Exception as e:
            db.session.rollback()
            print(f"Database save error: {e}")
            return jsonify({"error": f"Помилка збереження: {str(e)}"}), 500

    return jsonify({"error": _("Недозволений тип файлу. Дозволено: png, jpg, jpeg, gif, webp")}), 400


@media_bp.route("/images/<filename>")
def serve_image(filename):
    """Віддає зображення з бази даних."""
    from models.product import Image

    try:
        image = Image.query.filter_by(filename=filename).first()

        if not image:
            current_app.logger.warning(f"❌ Image not found in database: {filename}")
            return send_file(
                io.BytesIO(b''),
                mimetype='image/png',
                as_attachment=False
            ), 404

        image_io = io.BytesIO(image.data)
        image_io.seek(0)

        current_app.logger.debug(f"✅ Serving image from database: {filename} ({image.size} bytes)")

        return send_file(
            image_io,
            mimetype=image.mime_type,
            as_attachment=False,
            download_name=image.filename
        )
    except Exception as e:
        current_app.logger.error(f"❌ Error serving image {filename}: {type(e).__name__}: {e}")
        return send_file(
            io.BytesIO(b''),
            mimetype='image/png',
            as_attachment=False
        ), 500
