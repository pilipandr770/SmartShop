"""
Моделі для блогу та плану публікацій
"""
from datetime import datetime, date, timedelta
from extensions import db
import re


class BlogPostStatus:
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class BlogPost(db.Model):
    """Публікація блогу з SEO-оптимізацією."""
    __tablename__ = "blog_posts"
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Основний контент
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False)
    excerpt = db.Column(db.String(500), nullable=True)  # Короткий опис для картки
    content = db.Column(db.Text, nullable=True)  # Повний текст статті
    
    # Мультимовність
    title_en = db.Column(db.String(255), nullable=True)
    title_de = db.Column(db.String(255), nullable=True)
    excerpt_en = db.Column(db.String(500), nullable=True)
    excerpt_de = db.Column(db.String(500), nullable=True)
    content_en = db.Column(db.Text, nullable=True)
    content_de = db.Column(db.Text, nullable=True)
    
    # Медіа
    featured_image = db.Column(db.String(500), nullable=True)
    
    # SEO
    meta_title = db.Column(db.String(100), nullable=True)
    meta_description = db.Column(db.String(200), nullable=True)
    meta_keywords = db.Column(db.String(255), nullable=True)
    
    # Теги та категорії
    tags = db.Column(db.String(255), nullable=True)  # Через кому
    category = db.Column(db.String(100), nullable=True)
    
    # Статус і дати
    status = db.Column(db.String(20), default=BlogPostStatus.DRAFT)
    publish_date = db.Column(db.DateTime, nullable=True)  # Дата публікації (планова)
    
    # AI
    is_ai_generated = db.Column(db.Boolean, default=False)
    ai_topic = db.Column(db.String(255), nullable=True)  # Тема для генерації
    blog_plan_id = db.Column(db.Integer, db.ForeignKey('blog_plans.id'), nullable=True)
    
    # Метадані
    author = db.Column(db.String(100), default="AI")
    views = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<BlogPost {self.title[:30]}>"
    
    @property
    def is_published(self):
        """Чи опублікована стаття."""
        if self.status != BlogPostStatus.PUBLISHED:
            return False
        if self.publish_date and self.publish_date > datetime.utcnow():
            return False
        return True
    
    @property
    def tags_list(self):
        """Повертає теги як список."""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(',') if t.strip()]
    
    @staticmethod
    def generate_slug(title):
        """Генерує slug з заголовка."""
        # Транслітерація українських символів
        translit_map = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'ґ': 'g', 'д': 'd', 'е': 'e',
            'є': 'ye', 'ж': 'zh', 'з': 'z', 'и': 'y', 'і': 'i', 'ї': 'yi', 'й': 'y',
            'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
            'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch',
            'ш': 'sh', 'щ': 'shch', 'ь': '', 'ю': 'yu', 'я': 'ya', 'ы': 'y', 'э': 'e',
            'ё': 'yo', 'ъ': ''
        }
        
        slug = title.lower()
        for ukr, lat in translit_map.items():
            slug = slug.replace(ukr, lat)
        
        # Залишаємо тільки букви, цифри, дефіси
        slug = re.sub(r'[^a-z0-9\-]', '-', slug)
        slug = re.sub(r'-+', '-', slug)  # Прибираємо повтори дефісів
        slug = slug.strip('-')
        
        return slug[:200] if slug else 'post'
    
    def increment_views(self):
        """Збільшує кількість переглядів."""
        self.views += 1
        db.session.commit()
    
    @classmethod
    def get_published(cls, limit=None):
        """Отримати опубліковані пости."""
        query = cls.query.filter(
            cls.status == BlogPostStatus.PUBLISHED,
            db.or_(
                cls.publish_date.is_(None),
                cls.publish_date <= datetime.utcnow()
            )
        ).order_by(cls.publish_date.desc(), cls.created_at.desc())
        
        if limit:
            return query.limit(limit).all()
        return query.all()
    
    @classmethod
    def get_by_slug(cls, slug):
        """Знайти пост за slug."""
        return cls.query.filter_by(slug=slug).first()
    
    def get_title(self, locale='uk'):
        """Повертає заголовок відповідно до мови."""
        if locale == 'en' and self.title_en:
            return self.title_en
        elif locale == 'de' and self.title_de:
            return self.title_de
        return self.title
    
    def get_excerpt(self, locale='uk'):
        """Повертає уривок відповідно до мови."""
        if locale == 'en' and self.excerpt_en:
            return self.excerpt_en
        elif locale == 'de' and self.excerpt_de:
            return self.excerpt_de
        return self.excerpt or ''
    
    def get_content(self, locale='uk'):
        """Повертає контент відповідно до мови."""
        if locale == 'en' and self.content_en:
            return self.content_en
        elif locale == 'de' and self.content_de:
            return self.content_de
        return self.content or ''


class BlogPlan(db.Model):
    """План публікацій на 7 днів."""
    __tablename__ = "blog_plans"
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Дата плану
    plan_date = db.Column(db.Date, nullable=False)
    
    # Тема для генерації
    topic = db.Column(db.String(255), nullable=False)
    keywords = db.Column(db.String(255), nullable=True)  # SEO ключові слова
    
    # Статус
    status = db.Column(db.String(20), default="pending")  # pending, generated, published
    
    # Зв'язок з постом
    blog_post_id = db.Column(db.Integer, db.ForeignKey('blog_posts.id'), nullable=True)
    blog_post = db.relationship('BlogPost', backref='plan', foreign_keys=[blog_post_id])
    
    # Додаткові інструкції
    additional_instructions = db.Column(db.Text, nullable=True)
    target_audience = db.Column(db.String(255), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<BlogPlan {self.plan_date} - {self.topic[:30]}>"
    
    @property
    def is_overdue(self):
        """Чи прострочений план."""
        return self.status == "pending" and self.plan_date < date.today()
    
    @classmethod
    def create_weekly_plan(cls, topics_list):
        """
        Створює план на 7 днів.
        topics_list: список словників з topic, keywords, etc.
        """
        plans = []
        today = date.today()
        
        for i, topic_data in enumerate(topics_list[:7]):
            plan_date = today + timedelta(days=i)
            
            plan = cls(
                plan_date=plan_date,
                topic=topic_data.get('topic', f'Тема {i+1}'),
                keywords=topic_data.get('keywords', ''),
                additional_instructions=topic_data.get('instructions', ''),
                target_audience=topic_data.get('audience', ''),
            )
            db.session.add(plan)
            plans.append(plan)
        
        db.session.commit()
        return plans
    
    @classmethod
    def get_pending_for_date(cls, target_date=None):
        """Отримати pending плани для дати."""
        if target_date is None:
            target_date = date.today()
        
        return cls.query.filter(
            cls.plan_date <= target_date,
            cls.status == "pending"
        ).order_by(cls.plan_date.asc()).all()
    
    @classmethod
    def get_current_week(cls):
        """Отримати план на поточний тиждень."""
        today = date.today()
        week_start = today - timedelta(days=today.weekday())  # Понеділок
        week_end = week_start + timedelta(days=6)
        
        return cls.query.filter(
            cls.plan_date >= week_start,
            cls.plan_date <= week_end
        ).order_by(cls.plan_date.asc()).all()


class AISettings(db.Model):
    """Налаштування ІІ: чатбот та блогер."""
    __tablename__ = "ai_settings"
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    
    # === ЧАТБОТ ===
    chatbot_enabled = db.Column(db.Boolean, default=True)
    chatbot_name = db.Column(db.String(100), default="ІІ-продавець")
    
    # Базові інструкції (система)
    chatbot_system_prompt = db.Column(db.Text, nullable=True)
    
    # Кастомні інструкції від адміна
    chatbot_custom_instructions = db.Column(db.Text, nullable=True)
    
    # Тон спілкування
    chatbot_tone = db.Column(db.String(50), default="friendly")  # friendly, professional, casual
    
    # Обмеження
    chatbot_max_tokens = db.Column(db.Integer, default=500)
    chatbot_temperature = db.Column(db.Float, default=0.7)
    
    # Заборонені теми
    chatbot_forbidden_topics = db.Column(db.Text, nullable=True)
    
    # === БЛОГЕР ===
    blogger_enabled = db.Column(db.Boolean, default=True)
    blogger_name = db.Column(db.String(100), default="AI Блогер")
    
    # Стиль написання
    blogger_style = db.Column(db.String(50), default="informative")  # informative, entertaining, professional
    blogger_language = db.Column(db.String(10), default="uk")  # uk, en, de
    
    # SEO налаштування
    blogger_default_keywords = db.Column(db.Text, nullable=True)
    blogger_seo_instructions = db.Column(db.Text, nullable=True)
    
    # Структура статті
    blogger_article_structure = db.Column(db.Text, nullable=True)  # JSON або текст
    blogger_min_words = db.Column(db.Integer, default=500)
    blogger_max_words = db.Column(db.Integer, default=1500)
    
    # Автоматична публікація
    auto_publish = db.Column(db.Boolean, default=False)
    publish_time = db.Column(db.String(5), default="10:00")  # HH:MM
    
    # Генерація зображень
    generate_images = db.Column(db.Boolean, default=True)
    image_style = db.Column(db.String(100), default="professional photography, realistic, high quality")
    
    # Метадані
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<AISettings id={self.id}>"
    
    @staticmethod
    def get_or_create():
        """Отримує або створює налаштування AI."""
        settings = AISettings.query.first()
        if not settings:
            settings = AISettings(
                chatbot_system_prompt="""Ти — ввічливий продавець цього магазину. Твоє завдання:
- Допомогти клієнту обрати товар
- Ставити уточнюючі запитання  
- Пропонувати релевантні позиції з каталогу
- Не вигадувати товарів, яких немає на сайті
- Відповідати українською мовою""",
                chatbot_custom_instructions="",
                blogger_seo_instructions="""При написанні статей:
- Використовуй ключові слова органічно в тексті
- Заголовок має містити головне ключове слово
- Перший абзац повинен захопити увагу
- Додавай підзаголовки H2, H3 для структури
- Використовуй списки де доречно
- Закінчуй заклик до дії"""
            )
            db.session.add(settings)
            db.session.commit()
        return settings
    
    def get_full_chatbot_prompt(self, catalog_info=""):
        """Формує повний промпт для чатбота."""
        parts = []
        
        if self.chatbot_system_prompt:
            parts.append(self.chatbot_system_prompt)
        
        if self.chatbot_custom_instructions:
            parts.append(f"\nДодаткові інструкції від адміна:\n{self.chatbot_custom_instructions}")
        
        if catalog_info:
            parts.append(f"\n{catalog_info}")
        
        if self.chatbot_forbidden_topics:
            parts.append(f"\nТеми, на які не можна відповідати:\n{self.chatbot_forbidden_topics}")
        
        return "\n".join(parts)
    
    def get_blogger_prompt(self, topic, keywords=""):
        """Формує промпт для генерації статті."""
        parts = []
        
        parts.append(f"Напиши статтю для блогу на тему: {topic}")
        
        if keywords:
            parts.append(f"SEO ключові слова для використання: {keywords}")
        elif self.blogger_default_keywords:
            parts.append(f"Загальні ключові слова: {self.blogger_default_keywords}")
        
        if self.blogger_seo_instructions:
            parts.append(f"\nІнструкції з SEO:\n{self.blogger_seo_instructions}")
        
        parts.append(f"\nМова: {self.blogger_language}")
        parts.append(f"Стиль: {self.blogger_style}")
        parts.append(f"Обсяг: {self.blogger_min_words}-{self.blogger_max_words} слів")
        
        if self.blogger_article_structure:
            parts.append(f"\nСтруктура статті:\n{self.blogger_article_structure}")
        else:
            parts.append("""
Структура статті:
1. Захоплюючий заголовок з ключовим словом
2. Вступ (2-3 речення, про що стаття)
3. Основна частина з підзаголовками H2
4. Практичні поради або приклади
5. Висновок з закликом до дії""")
        
        return "\n".join(parts)
