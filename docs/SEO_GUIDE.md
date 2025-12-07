# 🔍 SEO Оптимізація SmartShop AI

## Статус Впровадження

✅ **robots.txt** - Налаштовано для всіх пошукових систем  
✅ **sitemap.xml** - Динамічна генерація для всіх сторінок  
✅ **Open Graph** - Meta tags для соціальних мереж  
✅ **Twitter Cards** - Оптимізація для Twitter/X  
✅ **JSON-LD** - Structured data для Google Rich Results  
✅ **Canonical URLs** - Уникнення дублювання контенту  
✅ **Multilingual** - hreflang tags для мультимовності  

---

## 1. robots.txt

### Розташування
`/static/robots.txt` → доступний за URL `/robots.txt`

### Основні правила:

```txt
User-agent: *
Allow: /

Disallow: /admin/
Disallow: /checkout/process
Disallow: /cart/add

Sitemap: https://smartshop-ai.onrender.com/sitemap.xml
```

### Дозволені AI боти:
- ✅ **GPTBot** (OpenAI)
- ✅ **ChatGPT-User** 
- ✅ **CCBot** (Common Crawl)
- ✅ **anthropic-ai** (Claude)
- ✅ **Claude-Web**

### Заблоковані боти:
- ❌ **MJ12bot** (Majestic crawler)
- ❌ **AhrefsBot** (SEO tool)
- ⏱️ **SemrushBot** (Crawl-delay: 10s)

### Оновлення:

```bash
# Локально
nano static/robots.txt

# На Render - автоматично після git push
git add static/robots.txt
git commit -m "Update robots.txt"
git push origin main
```

---

## 2. Sitemap.xml

### Доступні Sitemap:

| URL | Опис | Оновлення |
|-----|------|-----------|
| `/sitemap.xml` | Головний sitemap (всі сторінки) | Динамічно |
| `/sitemap-products.xml` | Тільки товари | Динамічно |
| `/sitemap-blog.xml` | Тільки блог пости | Динамічно |

### Генерація:

Sitemap генерується **динамічно** при кожному запиті з поточного стану БД:

```python
# services/seo_service.py
class SEOService:
    @staticmethod
    def generate_sitemap():
        # Включає:
        # - Головну сторінку
        # - /shop, /blog, /about, /contact
        # - Всі активні категорії
        # - Всі активні товари
        # - Всі опубліковані пости блогу
```

### Приклад структури:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
  <url>
    <loc>https://smartshop-ai.onrender.com/product/laptop-pro</loc>
    <lastmod>2025-12-07</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
    <image:image>
      <image:loc>https://cdn.smartshop.com/laptop.jpg</image:loc>
    </image:image>
  </url>
</urlset>
```

### Пріоритети:

| Тип сторінки | Priority | Change Frequency |
|--------------|----------|------------------|
| Головна | 1.0 | daily |
| Товари | 0.9 | weekly |
| Категорії | 0.8 | weekly |
| Магазин | 0.9 | daily |
| Блог | 0.8 | daily |
| Пости блогу | 0.7 | monthly |
| Статичні | 0.7 | monthly |

### Реєстрація в Google:

1. Відкрийте [Google Search Console](https://search.google.com/search-console)
2. Додайте сайт `smartshop-ai.onrender.com`
3. Перевірте власність (HTML tag або DNS)
4. Додайте sitemap: `https://smartshop-ai.onrender.com/sitemap.xml`
5. Зачекайте 24-48 годин для індексації

---

## 3. Open Graph Meta Tags

### Базові теги (всі сторінки):

```html
<meta property="og:type" content="website">
<meta property="og:url" content="{{ request.url }}">
<meta property="og:title" content="SmartShop AI">
<meta property="og:description" content="AI-powered shopping">
<meta property="og:image" content="{{ request.url_root }}static/images/og-default.jpg">
<meta property="og:site_name" content="SmartShop AI">
<meta property="og:locale" content="en_US">
```

### Товари (product.html):

```html
<meta property="og:type" content="product">
<meta property="og:title" content="{{ product.name }} - €{{ product.price }}">
<meta property="og:description" content="{{ product.description[:200] }}">
<meta property="og:image" content="{{ product.image_url }}">
<meta property="product:price:amount" content="{{ product.price }}">
<meta property="product:price:currency" content="EUR">
```

### Тестування:

- [Facebook Debugger](https://developers.facebook.com/tools/debug/)
- [LinkedIn Post Inspector](https://www.linkedin.com/post-inspector/)
- [Twitter Card Validator](https://cards-dev.twitter.com/validator)

Вставте URL сторінки для перевірки preview.

---

## 4. Twitter Cards

### Налаштовані теги:

```html
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@smartshop">
<meta name="twitter:creator" content="@smartshop">
<meta name="twitter:title" content="{{ title }}">
<meta name="twitter:description" content="{{ description }}">
<meta name="twitter:image" content="{{ image }}">
```

### Типи карток:

- **summary_large_image** - для товарів (велике зображення)
- **summary** - для статей блогу
- **app** - для майбутнього мобільного додатку

### Оновлення Twitter handle:

```python
# templates/base.html
<meta name="twitter:site" content="@your_twitter_handle">
```

---

## 5. JSON-LD Structured Data

### Типи structured data:

#### 5.1 Organization (base.html)

```json
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "SmartShop AI",
  "url": "https://smartshop-ai.onrender.com",
  "logo": "https://smartshop-ai.onrender.com/static/images/logo.png",
  "contactPoint": {
    "@type": "ContactPoint",
    "contactType": "Customer Service",
    "areaServed": ["DE", "EU"],
    "availableLanguage": ["en", "de", "uk"]
  }
}
```

#### 5.2 Product (product.html)

```json
{
  "@context": "https://schema.org/",
  "@type": "Product",
  "name": "Laptop Pro",
  "description": "High-performance laptop",
  "sku": "PROD-123",
  "image": "https://example.com/laptop.jpg",
  "brand": {
    "@type": "Brand",
    "name": "SmartShop"
  },
  "offers": {
    "@type": "Offer",
    "url": "https://smartshop-ai.onrender.com/product/laptop-pro",
    "priceCurrency": "EUR",
    "price": "999.99",
    "availability": "https://schema.org/InStock",
    "itemCondition": "https://schema.org/NewCondition"
  }
}
```

#### 5.3 BreadcrumbList (product.html)

```json
{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    {
      "@type": "ListItem",
      "position": 1,
      "name": "Home",
      "item": "https://smartshop-ai.onrender.com/"
    },
    {
      "@type": "ListItem",
      "position": 2,
      "name": "Shop",
      "item": "https://smartshop-ai.onrender.com/shop"
    }
  ]
}
```

#### 5.4 BlogPosting (blog_post.html - TODO)

```json
{
  "@context": "https://schema.org",
  "@type": "BlogPosting",
  "headline": "How to Choose Perfect Laptop",
  "image": "https://example.com/blog-image.jpg",
  "datePublished": "2025-12-07T10:00:00Z",
  "dateModified": "2025-12-07T15:30:00Z",
  "author": {
    "@type": "Person",
    "name": "SmartShop Editorial Team"
  },
  "publisher": {
    "@type": "Organization",
    "name": "SmartShop AI",
    "logo": {
      "@type": "ImageObject",
      "url": "https://smartshop-ai.onrender.com/static/images/logo.png"
    }
  }
}
```

#### 5.5 LocalBusiness (for physical stores - optional)

```json
{
  "@context": "https://schema.org",
  "@type": "OnlineStore",
  "name": "SmartShop AI",
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "Your Street 123",
    "addressLocality": "Berlin",
    "postalCode": "10115",
    "addressCountry": "DE"
  },
  "geo": {
    "@type": "GeoCoordinates",
    "latitude": 52.5200,
    "longitude": 13.4050
  },
  "openingHoursSpecification": {
    "@type": "OpeningHoursSpecification",
    "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    "opens": "09:00",
    "closes": "18:00"
  }
}
```

### Тестування:

1. [Google Rich Results Test](https://search.google.com/test/rich-results)
2. [Schema.org Validator](https://validator.schema.org/)
3. Вставте URL або код для перевірки

---

## 6. Canonical URLs

### Призначення:

Уникнення дублювання контенту через:
- Query parameters (`?page=2`, `?sort=price`)
- Різні протоколи (http vs https)
- Trailing slash (`/shop` vs `/shop/`)
- Мультимовність (`?lang=en`)

### Впровадження:

```html
<!-- base.html -->
<link rel="canonical" href="{% block canonical_url %}{{ request.url }}{% endblock %}">

<!-- product.html -->
{% block canonical_url %}{{ url_for('product_detail', slug=product.slug, _external=True) }}{% endblock %}
```

### Приклад:

```html
<!-- Всі ці URL вказують на один canonical -->
https://smartshop.com/product/laptop?ref=homepage
https://smartshop.com/product/laptop?utm_source=email
https://smartshop.com/product/laptop#reviews

<!-- Canonical URL -->
<link rel="canonical" href="https://smartshop.com/product/laptop">
```

---

## 7. Мультимовність (hreflang)

### Налаштовані мови:

```html
<link rel="alternate" hreflang="en" href="{{ request.base_url }}?lang=en">
<link rel="alternate" hreflang="de" href="{{ request.base_url }}?lang=de">
<link rel="alternate" hreflang="uk" href="{{ request.base_url }}?lang=uk">
<link rel="alternate" hreflang="x-default" href="{{ request.base_url }}">
```

### Структура:

| Code | Language | Region |
|------|----------|--------|
| `en` | English | Default |
| `de` | German | Germany |
| `uk` | Ukrainian | Ukraine |
| `x-default` | Default | Global |

### Майбутнє розширення:

```html
<!-- Додати для інших ринків -->
<link rel="alternate" hreflang="fr" href="...">  <!-- French -->
<link rel="alternate" hreflang="es" href="...">  <!-- Spanish -->
<link rel="alternate" hreflang="pl" href="...">  <!-- Polish -->
```

---

## 8. Geo-розмітка

### LocalBusiness Schema (для офлайн магазинів):

```json
{
  "@context": "https://schema.org",
  "@type": "Store",
  "name": "SmartShop Berlin",
  "image": "https://smartshop.com/store-berlin.jpg",
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "Alexanderplatz 1",
    "addressLocality": "Berlin",
    "postalCode": "10178",
    "addressCountry": "DE"
  },
  "geo": {
    "@type": "GeoCoordinates",
    "latitude": 52.5219,
    "longitude": 13.4132
  },
  "url": "https://smartshop-ai.onrender.com",
  "telephone": "+49-30-12345678",
  "openingHoursSpecification": [
    {
      "@type": "OpeningHoursSpecification",
      "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
      "opens": "09:00",
      "closes": "18:00"
    },
    {
      "@type": "OpeningHoursSpecification",
      "dayOfWeek": "Saturday",
      "opens": "10:00",
      "closes": "16:00"
    }
  ],
  "priceRange": "€€"
}
```

### Налаштування в коді:

```python
# services/seo_service.py
@staticmethod
def generate_local_business_schema():
    return {
        "@context": "https://schema.org",
        "@type": "OnlineStore",
        "address": {
            "streetAddress": os.environ.get("COMPANY_ADDRESS", ""),
            "addressLocality": os.environ.get("COMPANY_CITY", "Berlin"),
            "postalCode": os.environ.get("COMPANY_POSTAL", "10115"),
            "addressCountry": "DE"
        },
        "geo": {
            "latitude": float(os.environ.get("GEO_LAT", "52.5200")),
            "longitude": float(os.environ.get("GEO_LNG", "13.4050"))
        }
    }
```

### Додайте в .env:

```bash
COMPANY_ADDRESS=Your Street 123
COMPANY_CITY=Berlin
COMPANY_POSTAL=10115
GEO_LAT=52.5200
GEO_LNG=13.4050
```

---

## 9. Performance SEO

### Core Web Vitals:

✅ **LCP (Largest Contentful Paint)** - < 2.5s  
✅ **FID (First Input Delay)** - < 100ms  
✅ **CLS (Cumulative Layout Shift)** - < 0.1  

### Оптимізації:

1. **Зображення:**
   - WebP формат (менший розмір)
   - Lazy loading (`loading="lazy"`)
   - Responsive images (`srcset`)

2. **CSS/JS:**
   - Inline critical CSS
   - Async/defer для JS
   - Minification

3. **Caching:**
   - Redis для DB queries (TODO)
   - Browser caching (Cache-Control headers)

### Тестування:

- [PageSpeed Insights](https://pagespeed.web.dev/)
- [GTmetrix](https://gtmetrix.com/)
- [WebPageTest](https://www.webpagetest.org/)

---

## 10. Google Search Console

### Реєстрація:

1. Відкрийте https://search.google.com/search-console
2. Додайте сайт: `smartshop-ai.onrender.com`
3. Верифікація методом:
   - **HTML tag** (рекомендовано)
   - DNS record
   - Google Analytics

#### HTML Tag Verification:

```html
<!-- base.html <head> -->
<meta name="google-site-verification" content="YOUR_VERIFICATION_CODE" />
```

4. Додайте Sitemap:
   - URL: `https://smartshop-ai.onrender.com/sitemap.xml`
   - Натисніть "Submit"

5. Перевірте:
   - Coverage report
   - Performance
   - Mobile usability
   - Core Web Vitals

---

## 11. Bing Webmaster Tools

1. Відкрийте https://www.bing.com/webmasters
2. Додайте сайт
3. Імпортуйте з Google Search Console (швидше)
4. Або верифікація через HTML tag

---

## 12. AI Search Optimization

### ChatGPT, Claude, Perplexity:

Ці AI асистенти індексують вміст через:
- ✅ **Дозволені боти** в robots.txt
- ✅ **Structured data** (JSON-LD) для розуміння контексту
- ✅ **Чіткі описи** в meta description
- ✅ **Semantic HTML** для кращої інтерпретації

### Оптимізація контенту для AI:

1. **Чіткі заголовки** - H1, H2, H3 структура
2. **Короткі абзаци** - 2-3 речення
3. **Bullet points** - для списків характеристик
4. **FAQ секції** - питання/відповіді
5. **Structured data** - Product, FAQPage, HowTo

### Приклад FAQ Schema:

```json
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "What is the return policy?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "30-day money-back guarantee on all products."
      }
    }
  ]
}
```

---

## 13. Моніторинг SEO

### Щотижневі перевірки:

- [ ] Google Search Console - нові помилки?
- [ ] Sitemap.xml - всі сторінки індексовані?
- [ ] Organic traffic - зростає?
- [ ] Page speed - < 3s?
- [ ] Mobile usability - без помилок?

### Інструменти:

- [Ahrefs](https://ahrefs.com) - Backlinks, keywords
- [SEMrush](https://semrush.com) - Competitor analysis
- [Google Analytics 4](https://analytics.google.com) - Traffic
- [Screaming Frog](https://www.screamingfrogсеo.com) - Technical audit

---

## 14. TODO: Майбутні покращення

- [ ] Додати FAQ Schema для популярних питань
- [ ] Відгуки товарів з AggregateRating
- [ ] Video Schema для video reviews
- [ ] Recipe Schema (якщо будуть товари для кухні)
- [ ] Event Schema (для акцій/розпродажів)
- [ ] RSS feed для блогу (`/blog/rss.xml`)
- [ ] AMP версія сторінок (Mobile-first)
- [ ] Progressive Web App (PWA) manifest

---

## 15. Корисні посилання

- [Google SEO Starter Guide](https://developers.google.com/search/docs/fundamentals/seo-starter-guide)
- [Schema.org Types](https://schema.org/docs/schemas.html)
- [Open Graph Protocol](https://ogp.me/)
- [Twitter Cards Guide](https://developer.twitter.com/en/docs/twitter-for-websites/cards/overview/abouts-cards)
- [Google Rich Results Gallery](https://developers.google.com/search/docs/appearance/structured-data/search-gallery)

---

## Підсумок

✅ **Базова SEO** повністю налаштована  
✅ **Structured Data** для товарів та організації  
✅ **Social Sharing** оптимізовано (OG, Twitter)  
✅ **Sitemaps** генеруються динамічно  
✅ **Мультимовність** через hreflang  
✅ **AI-friendly** для ChatGPT, Claude, Perplexity  

**Очікуваний результат:** Індексація в Google за 1-2 тижні, поява в результатах пошуку за 1-2 місяці.
