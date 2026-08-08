"""
Блог: адмінка (CRUD + AI-генерація за планом), публічні сторінки, і фонова
автоматизація (APScheduler) - авто-генерація за BlogPlan та авто-публікація
запланованих статей.

Винесено з app.py (раніше - останній розділ create_app(), ~930 рядків) як
частину Phase 2 плану (SWOT 2026-08-08): app.py був монолітом на 6640+
рядків, блог - найбільш самодостатній розділ (власні моделі, мінімум
залежностей від checkout-критичного шляху), тому перший кандидат на винос.

start_blog_scheduler(app) викликається один раз з create_app() ПІСЛЯ
реєстрації цього blueprint - і саме тому приймає app явним параметром
(на момент запуску ще немає активного app/request контексту, тож
current_app там не спрацював би).
"""
import os
import uuid
from datetime import datetime, date as date_cls

from flask import (
    Blueprint, request, redirect, url_for, flash, render_template,
    jsonify, abort, g, current_app,
)
from flask_babel import gettext as _

from extensions import db
from models.blog import BlogPost, BlogPlan, AISettings, BlogPostStatus
from models.settings import SiteSettings
from services.admin_auth import admin_required
from services.openai_client import get_openai_client, OPENAI_AVAILABLE
from services.image_storage import delete_old_image

blog_bp = Blueprint("blog", __name__)


# =====================================================================
# BLOG ADMIN ROUTES
# =====================================================================

@blog_bp.route("/admin/blog")
@admin_required
def admin_blog():
    """Список статей блогу."""
    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "")
    per_page = 20

    query = BlogPost.query.filter_by(store_id=g.store.id)

    if status_filter:
        query = query.filter(BlogPost.status == status_filter)

    query = query.order_by(BlogPost.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    posts = pagination.items

    stats = {
        "total": BlogPost.query.filter_by(store_id=g.store.id).count(),
        "published": BlogPost.query.filter_by(status=BlogPostStatus.PUBLISHED, store_id=g.store.id).count(),
        "scheduled": BlogPost.query.filter_by(status=BlogPostStatus.SCHEDULED, store_id=g.store.id).count(),
        "draft": BlogPost.query.filter_by(status=BlogPostStatus.DRAFT, store_id=g.store.id).count(),
    }

    return render_template(
        "admin/blog.html",
        posts=posts,
        pagination=pagination,
        stats=stats,
        status_filter=status_filter,
        page=page,
        total_pages=pagination.pages,
    )


@blog_bp.route("/admin/blog/new", methods=["GET", "POST"])
@admin_required
def admin_blog_new():
    """Створення нової статті."""
    if request.method == "POST":
        action = request.form.get("action", "save")

        title = request.form.get("title", "").strip()
        slug = request.form.get("slug", "").strip() or BlogPost.generate_slug(title)

        existing = BlogPost.get_by_slug(slug, store_id=g.store.id)
        if existing:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        post = BlogPost(
            store_id=g.store.id,
            title=title,
            slug=slug,
            excerpt=request.form.get("excerpt", "").strip() or None,
            content=request.form.get("content", "").strip() or None,
            featured_image=request.form.get("featured_image", "").strip() or None,
            meta_title=request.form.get("meta_title", "").strip() or None,
            meta_description=request.form.get("meta_description", "").strip() or None,
            meta_keywords=request.form.get("meta_keywords", "").strip() or None,
            tags=request.form.get("tags", "").strip() or None,
            category=request.form.get("category", "").strip() or None,
            author=request.form.get("author", "AI").strip(),
            ai_topic=request.form.get("ai_topic", "").strip() or None,
            title_en=request.form.get("title_en", "").strip() or None,
            title_de=request.form.get("title_de", "").strip() or None,
            excerpt_en=request.form.get("excerpt_en", "").strip() or None,
            excerpt_de=request.form.get("excerpt_de", "").strip() or None,
            content_en=request.form.get("content_en", "").strip() or None,
            content_de=request.form.get("content_de", "").strip() or None,
        )

        if action == "publish":
            post.status = BlogPostStatus.PUBLISHED
            post.publish_date = datetime.utcnow()
        else:
            post.status = request.form.get("status", BlogPostStatus.DRAFT)
            publish_date = request.form.get("publish_date", "")
            if publish_date:
                try:
                    post.publish_date = datetime.fromisoformat(publish_date)
                except ValueError:
                    pass

        db.session.add(post)
        db.session.commit()

        flash(_("✅ Статтю створено!"), "success")
        return redirect(url_for(".admin_blog_edit", id=post.id))

    return render_template("admin/blog_edit.html", post=None)


@blog_bp.route("/admin/blog/<int:id>", methods=["GET", "POST"])
@admin_required
def admin_blog_edit(id):
    """Редагування статті."""
    post = BlogPost.query.filter_by(id=id, store_id=g.store.id).first_or_404()

    if request.method == "POST":
        action = request.form.get("action", "save")

        post.title = request.form.get("title", "").strip()

        new_slug = request.form.get("slug", "").strip() or BlogPost.generate_slug(post.title)
        if new_slug != post.slug:
            existing = BlogPost.query.filter(
                BlogPost.slug == new_slug, BlogPost.store_id == g.store.id, BlogPost.id != id
            ).first()
            if existing:
                new_slug = f"{new_slug}-{uuid.uuid4().hex[:6]}"
            post.slug = new_slug

        post.excerpt = request.form.get("excerpt", "").strip() or None
        post.content = request.form.get("content", "").strip() or None

        new_featured_image = request.form.get("featured_image", "").strip() or None
        if new_featured_image and new_featured_image != post.featured_image:
            delete_old_image(post.featured_image)
        post.featured_image = new_featured_image

        post.meta_title = request.form.get("meta_title", "").strip() or None
        post.meta_description = request.form.get("meta_description", "").strip() or None
        post.meta_keywords = request.form.get("meta_keywords", "").strip() or None
        post.tags = request.form.get("tags", "").strip() or None
        post.category = request.form.get("category", "").strip() or None
        post.author = request.form.get("author", "AI").strip()
        post.ai_topic = request.form.get("ai_topic", "").strip() or None

        post.title_en = request.form.get("title_en", "").strip() or None
        post.title_de = request.form.get("title_de", "").strip() or None
        post.excerpt_en = request.form.get("excerpt_en", "").strip() or None
        post.excerpt_de = request.form.get("excerpt_de", "").strip() or None
        post.content_en = request.form.get("content_en", "").strip() or None
        post.content_de = request.form.get("content_de", "").strip() or None

        if action == "publish":
            post.status = BlogPostStatus.PUBLISHED
            if not post.publish_date:
                post.publish_date = datetime.utcnow()
        else:
            post.status = request.form.get("status", BlogPostStatus.DRAFT)
            publish_date = request.form.get("publish_date", "")
            if publish_date:
                try:
                    post.publish_date = datetime.fromisoformat(publish_date)
                except ValueError:
                    pass

        db.session.commit()
        flash(_("✅ Статтю оновлено!"), "success")
        return redirect(url_for(".admin_blog_edit", id=id))

    return render_template("admin/blog_edit.html", post=post)


@blog_bp.route("/admin/blog/<int:id>/delete", methods=["POST"])
@admin_required
def admin_blog_delete(id):
    """Видалення статті."""
    post = BlogPost.query.filter_by(id=id, store_id=g.store.id).first_or_404()

    if post.featured_image:
        delete_old_image(post.featured_image)

    db.session.delete(post)
    db.session.commit()
    flash(_("Статтю видалено."), "info")
    return redirect(url_for(".admin_blog"))


@blog_bp.route("/admin/blog/<int:id>/publish", methods=["POST"])
@admin_required
def admin_blog_publish(id):
    """Швидка публікація статті."""
    post = BlogPost.query.filter_by(id=id, store_id=g.store.id).first_or_404()
    post.status = BlogPostStatus.PUBLISHED
    if not post.publish_date or post.publish_date > datetime.utcnow():
        post.publish_date = datetime.utcnow()
    db.session.commit()
    flash(_("✅ Статтю '%(title)s' опубліковано!") % {"title": post.title}, "success")
    return redirect(url_for(".admin_blog"))


@blog_bp.route("/admin/blog/plan", methods=["GET", "POST"])
@admin_required
def admin_blog_plan():
    """План публікацій на 7 днів."""
    from datetime import timedelta

    if request.method == "POST":
        topics_list = []
        target_audience = request.form.get("target_audience", "")
        additional_instructions = request.form.get("additional_instructions", "")

        for i in range(7):
            topic = request.form.get(f"topic_{i}", "").strip()
            if topic:
                topics_list.append({
                    "topic": topic,
                    "keywords": request.form.get(f"keywords_{i}", "").strip(),
                    "audience": target_audience,
                    "instructions": additional_instructions,
                })

        if topics_list:
            BlogPlan.create_weekly_plan(topics_list, store_id=g.store.id)
            flash(_("✅ Створено план на %(count)s днів!") % {"count": len(topics_list)}, "success")
        else:
            flash(_("Введіть хоча б одну тему."), "warning")

        return redirect(url_for(".admin_blog_plan"))

    today = date_cls.today()
    week_days = []
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]

    for i in range(7):
        current_date = today + timedelta(days=i)
        plan = BlogPlan.query.filter_by(plan_date=current_date, store_id=g.store.id).first()

        week_days.append({
            "date": current_date,
            "day_name": day_names[current_date.weekday()],
            "is_today": current_date == today,
            "is_past": current_date < today,
            "plan": plan,
        })

    all_plans = BlogPlan.query.filter_by(store_id=g.store.id).order_by(BlogPlan.plan_date.desc()).limit(30).all()

    return render_template(
        "admin/blog_plan.html",
        week_days=week_days,
        all_plans=all_plans,
    )


# =====================================================================
# BLOG API ROUTES (AI Generation)
# =====================================================================

@blog_bp.route("/api/blog/generate", methods=["POST"])
@admin_required
def api_blog_generate():
    """API генерації статті через AI."""
    openai_client = get_openai_client()
    if not OPENAI_AVAILABLE or not openai_client:
        return jsonify({"error": _("AI не налаштовано")}), 400

    data = request.get_json()
    topic = data.get("topic", "").strip()
    keywords = data.get("keywords", "").strip()

    if not topic:
        return jsonify({"error": _("Тема обов'язкова")}), 400

    ai_settings = AISettings.get_or_create(g.store.id)

    try:
        prompt = ai_settings.get_blogger_prompt(topic, keywords)

        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": f"""Ти - досвідчений контент-райтер та SEO-спеціаліст.
Пиши мовою: {ai_settings.blogger_language}
Стиль: {ai_settings.blogger_style}
Обсяг: {ai_settings.blogger_min_words}-{ai_settings.blogger_max_words} слів

Результат у форматі JSON:
{{
  "title": "SEO-оптимізований заголовок",
  "excerpt": "Короткий опис до 200 символів",
  "content": "Повний текст статті з HTML форматуванням (h2, h3, p, ul, li)",
  "meta_title": "Meta title до 60 символів",
  "meta_description": "Meta description до 160 символів",
  "tags": "тег1, тег2, тег3"
}}"""},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
            temperature=0.7,
        )

        content = response.choices[0].message.content

        import json
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result = json.loads(content.strip())
            result["success"] = True
            return jsonify(result)
        except json.JSONDecodeError:
            return jsonify({
                "success": True,
                "title": topic,
                "content": content,
                "excerpt": content[:200] if content else "",
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _generate_post_from_plan(plan):
    """
    Генерує BlogPost з BlogPlan через OpenAI (текст + SEO meta + опційно
    зображення й автопереклад). Викликається і з адмін-роута (клік
    адміна), і з фонового планувальника (_run_blog_automation нижче) -
    працює виключно з plan.store_id, без залежності від g.store/request,
    тож придатна для виклику поза HTTP-запитом (лише в app-контексті).
    """
    openai_client = get_openai_client()
    if not OPENAI_AVAILABLE or not openai_client:
        raise RuntimeError("AI не налаштовано")

    store_id = plan.store_id

    old_post = None
    if plan.blog_post_id:
        old_post = BlogPost.query.get(plan.blog_post_id)
        if old_post and old_post.featured_image:
            current_app.logger.info(f"🔄 Regenerating post, will delete old image: {old_post.featured_image}")

    if plan.status != "pending":
        raise ValueError("План вже оброблено")

    ai_settings = AISettings.get_or_create(store_id)

    topic = plan.topic
    keywords = plan.keywords or ""

    if plan.additional_instructions:
        keywords += f"\n\nДодаткові інструкції: {plan.additional_instructions}"

    prompt = ai_settings.get_blogger_prompt(topic, keywords)

    response = openai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": f"""Ти - досвідчений контент-райтер та SEO-спеціаліст.
Пиши мовою: {ai_settings.blogger_language}
Стиль: {ai_settings.blogger_style}
Обсяг: {ai_settings.blogger_min_words}-{ai_settings.blogger_max_words} слів

Результат у форматі JSON:
{{
  "title": "SEO-оптимізований заголовок",
  "excerpt": "Короткий опис до 200 символів",
  "content": "Повний текст статті з HTML форматуванням (h2, h3, p, ul, li)",
  "meta_title": "Meta title до 60 символів",
  "meta_description": "Meta description до 160 символів",
  "tags": "тег1, тег2, тег3"
}}"""},
            {"role": "user", "content": prompt},
        ],
        max_tokens=2000,
        temperature=0.7,
    )

    content = response.choices[0].message.content

    import json
    try:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        result = json.loads(content.strip())
    except json.JSONDecodeError:
        result = {
            "title": topic,
            "content": content,
            "excerpt": content[:200] if content else "",
        }

    featured_image_url = None
    if ai_settings.generate_images:
        try:
            image_style = ai_settings.image_style or "professional photography, realistic, high quality"

            image_prompt_response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": f"""Ти - експерт з створення промптів для генерації зображень.
Створи короткий промпт (до 200 символів) англійською мовою для DALL-E, щоб згенерувати реалістичне фото для статті блогу.
Промпт має описувати:
- Головний об'єкт/сцену що відповідає темі
- Стиль: {image_style}
- Світло та композицію
Відповідай ТІЛЬКИ промптом, без додаткового тексту."""},
                    {"role": "user", "content": f"Тема статті: {result.get('title', topic)}\n\nКороткий опис: {result.get('excerpt', '')[:200]}"},
                ],
                max_tokens=100,
                temperature=0.7,
            )

            image_prompt = image_prompt_response.choices[0].message.content.strip()
            print(f"🎨 Генерую зображення: {image_prompt[:80]}...")

            image_response = openai_client.images.generate(
                model="dall-e-3",
                prompt=image_prompt,
                size="1792x1024",
                quality="standard",
                n=1,
            )

            image_url = image_response.data[0].url

            import requests as req
            img_response = req.get(image_url, timeout=30)
            if img_response.status_code == 200:
                from models.product import Image

                image_filename = f"blog_{uuid.uuid4().hex}.png"

                if current_app.config["IMAGE_STORAGE"] == "database":
                    image_data = img_response.content

                    existing_image = Image.query.filter_by(filename=image_filename).first()
                    if not existing_image:
                        new_image = Image(
                            store_id=store_id,
                            filename=image_filename,
                            data=image_data,
                            mime_type='image/png',
                            size=len(image_data)
                        )
                        db.session.add(new_image)
                        db.session.commit()
                        print(f"💾 Зображення збережено в БД: {image_filename} ({len(image_data)} bytes)")

                    featured_image_url = f"/images/{image_filename}"
                else:
                    image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], image_filename)

                    with open(image_path, 'wb') as f:
                        f.write(img_response.content)

                    featured_image_url = f"/static/uploads/{image_filename}"

                print(f"✅ Зображення збережено: {featured_image_url}")

        except Exception as img_error:
            print(f"⚠️ Помилка генерації зображення: {img_error}")

    slug = BlogPost.generate_slug(result.get("title", topic))
    existing = BlogPost.get_by_slug(slug, store_id=store_id)
    if existing:
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    publish_datetime = datetime.combine(plan.plan_date, datetime.strptime(ai_settings.publish_time, "%H:%M").time())

    if ai_settings.auto_publish:
        if publish_datetime <= datetime.utcnow():
            post_status = BlogPostStatus.PUBLISHED
        else:
            post_status = BlogPostStatus.SCHEDULED
    else:
        post_status = BlogPostStatus.DRAFT

    post = BlogPost(
        store_id=store_id,
        title=result.get("title", topic),
        slug=slug,
        excerpt=result.get("excerpt", ""),
        content=result.get("content", ""),
        featured_image=featured_image_url,
        meta_title=result.get("meta_title", ""),
        meta_description=result.get("meta_description", ""),
        tags=result.get("tags", ""),
        status=post_status,
        publish_date=publish_datetime,
        is_ai_generated=True,
        ai_topic=topic,
        blog_plan_id=plan.id,
        author=ai_settings.blogger_name or "AI",
    )
    db.session.add(post)
    db.session.flush()

    if old_post and old_post.featured_image and featured_image_url:
        delete_old_image(old_post.featured_image)

    plan.status = "generated"
    plan.blog_post_id = post.id

    db.session.commit()

    if ai_settings.auto_translate:
        try:
            translate_languages = (ai_settings.auto_translate_languages or "en,de").split(",")
            for lang in translate_languages:
                lang = lang.strip()
                if lang not in ["en", "de"]:
                    continue

                lang_name = "English" if lang == "en" else "German"

                title_resp = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": f"Translate from Ukrainian to {lang_name}. Return ONLY translated text."},
                        {"role": "user", "content": post.title},
                    ],
                    max_tokens=200,
                    temperature=0.3,
                )

                excerpt_resp = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": f"Translate from Ukrainian to {lang_name}. Return ONLY translated text."},
                        {"role": "user", "content": post.excerpt or ""},
                    ],
                    max_tokens=300,
                    temperature=0.3,
                )

                content_resp = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": f"Translate this HTML content from Ukrainian to {lang_name}. Keep all HTML tags. Return ONLY translated HTML."},
                        {"role": "user", "content": post.content or ""},
                    ],
                    max_tokens=3000,
                    temperature=0.3,
                )

                if lang == "en":
                    post.title_en = title_resp.choices[0].message.content.strip()
                    post.excerpt_en = excerpt_resp.choices[0].message.content.strip()
                    post.content_en = content_resp.choices[0].message.content.strip()
                elif lang == "de":
                    post.title_de = title_resp.choices[0].message.content.strip()
                    post.excerpt_de = excerpt_resp.choices[0].message.content.strip()
                    post.content_de = content_resp.choices[0].message.content.strip()

            db.session.commit()
        except Exception as translate_error:
            print(f"Auto-translate error: {translate_error}")

    return post


@blog_bp.route("/api/blog/generate-from-plan/<int:plan_id>", methods=["POST"])
@admin_required
def api_blog_generate_from_plan(plan_id):
    """Генерація статті з плану (ручний запуск адміном)."""
    plan = BlogPlan.query.filter_by(id=plan_id, store_id=g.store.id).first_or_404()
    if plan.status != "pending":
        return jsonify({"error": _("План вже оброблено")}), 400
    try:
        post = _generate_post_from_plan(plan)
        return jsonify({"success": True, "post_id": post.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@blog_bp.route("/api/blog/generate-all-pending", methods=["POST"])
@admin_required
def api_blog_generate_all_pending():
    """Генерація всіх pending статей."""
    pending_plans = BlogPlan.get_pending_for_date(store_id=g.store.id)
    generated = 0

    for plan in pending_plans:
        try:
            with current_app.test_client() as client:
                response = client.post(
                    f"/api/blog/generate-from-plan/{plan.id}",
                    headers={"Cookie": request.headers.get("Cookie", "")},
                )
                if response.status_code == 200:
                    generated += 1
        except Exception as e:
            print(f"Error generating plan {plan.id}: {e}")
            continue

    return jsonify({"success": True, "generated": generated})


@blog_bp.route("/api/blog/auto-publish", methods=["POST"])
@admin_required
def api_blog_auto_publish():
    """Автоматична публікація scheduled постів, час яких настав."""
    try:
        scheduled_posts = BlogPost.query.filter(
            BlogPost.status == BlogPostStatus.SCHEDULED,
            BlogPost.publish_date <= datetime.utcnow(),
            BlogPost.store_id == g.store.id,
        ).all()

        published_count = 0
        for post in scheduled_posts:
            post.status = BlogPostStatus.PUBLISHED
            published_count += 1
            current_app.logger.info(f"📰 Auto-published: {post.title}")

        if published_count > 0:
            db.session.commit()

        return jsonify({
            "success": True,
            "published": published_count,
            "message": f"Опубліковано {published_count} статей"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@blog_bp.route("/api/blog/plan/<int:plan_id>", methods=["DELETE"])
@admin_required
def api_blog_plan_delete(plan_id):
    """Видалення плану."""
    plan = BlogPlan.query.filter_by(id=plan_id, store_id=g.store.id).first_or_404()
    db.session.delete(plan)
    db.session.commit()
    return jsonify({"success": True})


@blog_bp.route("/api/blog/translate/<int:post_id>", methods=["POST"])
@admin_required
def api_blog_translate(post_id):
    """Автоматичний переклад статті на інші мови."""
    openai_client = get_openai_client()
    if not OPENAI_AVAILABLE or not openai_client:
        return jsonify({"error": _("AI не налаштовано. Додайте OPENAI_API_KEY")}), 400

    post = BlogPost.query.filter_by(id=post_id, store_id=g.store.id).first_or_404()
    data = request.get_json() or {}
    languages = data.get("languages", ["en", "de"])

    if not post.title or not post.content:
        return jsonify({"error": _("Стаття не має контенту для перекладу")}), 400

    translated = {}

    try:
        for lang in languages:
            if lang not in ["en", "de"]:
                continue

            lang_name = "English" if lang == "en" else "German"

            title_response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": f"You are a professional translator. Translate the following text from Ukrainian to {lang_name}. Keep the same style and tone. Return ONLY the translated text, nothing else."},
                    {"role": "user", "content": post.title},
                ],
                max_tokens=200,
                temperature=0.3,
            )
            translated_title = title_response.choices[0].message.content.strip()

            translated_excerpt = None
            if post.excerpt:
                excerpt_response = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": f"You are a professional translator. Translate the following text from Ukrainian to {lang_name}. Keep the same style and tone. Return ONLY the translated text, nothing else."},
                        {"role": "user", "content": post.excerpt},
                    ],
                    max_tokens=300,
                    temperature=0.3,
                )
                translated_excerpt = excerpt_response.choices[0].message.content.strip()

            content_response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": f"You are a professional translator. Translate the following HTML content from Ukrainian to {lang_name}. Keep all HTML tags intact. Maintain the same formatting and structure. Return ONLY the translated HTML, nothing else."},
                    {"role": "user", "content": post.content},
                ],
                max_tokens=3000,
                temperature=0.3,
            )
            translated_content = content_response.choices[0].message.content.strip()

            if lang == "en":
                post.title_en = translated_title
                post.excerpt_en = translated_excerpt
                post.content_en = translated_content
            elif lang == "de":
                post.title_de = translated_title
                post.excerpt_de = translated_excerpt
                post.content_de = translated_content

            translated[lang] = {
                "title": translated_title,
                "excerpt": translated_excerpt,
                "content_preview": translated_content[:200] + "..." if len(translated_content) > 200 else translated_content
            }

        db.session.commit()

        return jsonify({
            "success": True,
            "translated": translated,
            "message": f"Стаття перекладена на {len(translated)} мов(и)"
        })

    except Exception as e:
        return jsonify({"error": f"Помилка перекладу: {str(e)}"}), 500


# =====================================================================
# PUBLIC BLOG ROUTES
# =====================================================================

@blog_bp.route("/blog")
def blog_page():
    """Публічна сторінка блогу."""
    settings = SiteSettings.get_or_create(g.store.id)
    page = request.args.get("page", 1, type=int)
    per_page = 9

    query = BlogPost.query.filter(
        BlogPost.status == BlogPostStatus.PUBLISHED,
        BlogPost.store_id == g.store.id,
        db.or_(
            BlogPost.publish_date.is_(None),
            BlogPost.publish_date <= datetime.utcnow()
        )
    ).order_by(BlogPost.publish_date.desc(), BlogPost.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    posts = pagination.items

    featured_post = posts[0] if posts else None
    other_posts = posts[1:] if len(posts) > 1 else []

    return render_template(
        "pages/blog.html",
        settings=settings,
        featured_post=featured_post,
        posts=other_posts,
        pagination=pagination,
        page=page,
        total_pages=pagination.pages,
    )


@blog_bp.route("/blog/<slug>")
def blog_post_page(slug):
    """Сторінка окремого посту."""
    settings = SiteSettings.get_or_create(g.store.id)
    post = BlogPost.get_by_slug(slug, store_id=g.store.id)

    if not post or not post.is_published:
        abort(404)

    post.increment_views()

    related = []
    if post.category:
        related = BlogPost.query.filter(
            BlogPost.status == BlogPostStatus.PUBLISHED,
            BlogPost.category == post.category,
            BlogPost.store_id == g.store.id,
            BlogPost.id != post.id,
        ).limit(3).all()

    if not related:
        related = BlogPost.query.filter(
            BlogPost.status == BlogPostStatus.PUBLISHED,
            BlogPost.store_id == g.store.id,
            BlogPost.id != post.id,
        ).order_by(BlogPost.views.desc()).limit(3).all()

    return render_template(
        "pages/blog_post.html",
        settings=settings,
        post=post,
        related=related,
    )


# =====================================================================
# ФОНОВА АВТОМАТИЗАЦІЯ (APScheduler)
# =====================================================================

def _run_blog_automation():
    """
    Фонова робота блогера: генерує статті з BlogPlan, дата яких настала
    (лише для магазинів з увімкненим AISettings.blogger_auto_generate),
    і публікує BlogPost зі статусом SCHEDULED, час яких настав.
    """
    try:
        due_plans = BlogPlan.get_pending_for_date(target_date=date_cls.today())
        for plan in due_plans:
            try:
                ai_settings = AISettings.get_or_create(plan.store_id)
                if not ai_settings.blogger_auto_generate:
                    continue
                post = _generate_post_from_plan(plan)
                current_app.logger.info(f"🤖 Auto-generated blog post #{post.id} from plan #{plan.id} (store {plan.store_id})")
            except Exception as e:
                db.session.rollback()
                current_app.logger.warning(f"Blog auto-generation failed for plan #{plan.id}: {e}")
    except Exception as e:
        current_app.logger.error(f"Blog automation (generate) job failed: {e}")

    try:
        due_posts = BlogPost.query.filter(
            BlogPost.status == BlogPostStatus.SCHEDULED,
            BlogPost.publish_date <= datetime.utcnow(),
        ).all()
        published_count = 0
        for post in due_posts:
            post.status = BlogPostStatus.PUBLISHED
            published_count += 1
        if published_count:
            db.session.commit()
            current_app.logger.info(f"📰 Auto-published {published_count} scheduled blog post(s)")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Blog automation (auto-publish) job failed: {e}")


def start_blog_scheduler(app, demo_mode):
    """
    Запускає фонове завдання блогера кожні 15 хв. Gunicorn піднімає
    декілька worker-процесів - кожен запустив би свій BackgroundScheduler,
    що призвело б до дублювання генерації/публікації. Тому кожен тік
    спершу бере Postgres advisory lock: лише той worker, що встиг його
    захопити, реально виконує роботу, інші миттєво виходять.

    Приймає app явним параметром (а не через current_app) - викликається
    один раз при старті, коли ще немає активного app/request контексту.
    """
    if demo_mode or os.environ.get("DISABLE_SCHEDULER") == "1":
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        import sqlalchemy as sa

        LOCK_KEY = 928374651  # довільне, але стабільне число для цього job'а

        def guarded_job():
            with app.app_context():
                got_lock = True
                is_postgres = db.engine.url.get_backend_name().startswith("postgres")
                if is_postgres:
                    try:
                        got_lock = bool(db.session.execute(
                            sa.text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY}
                        ).scalar())
                    except Exception:
                        got_lock = True
                if not got_lock:
                    return
                try:
                    _run_blog_automation()
                finally:
                    if is_postgres:
                        try:
                            db.session.execute(sa.text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
                            db.session.commit()
                        except Exception:
                            db.session.rollback()

        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            func=guarded_job,
            trigger="interval",
            minutes=15,
            id="blog_automation",
            replace_existing=True,
            next_run_time=datetime.utcnow(),
        )
        scheduler.start()
        app.logger.info("📅 Blog automation scheduler started (every 15 min)")
    except Exception as e:
        app.logger.warning(f"Could not start blog scheduler: {e}")
