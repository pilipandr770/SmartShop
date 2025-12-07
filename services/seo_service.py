"""
SEO Service: Sitemap generation, meta tags, structured data
"""
from datetime import datetime
from flask import url_for, request
from extensions import db
from models.product import Product, Category
from models.blog import BlogPost
import xml.etree.ElementTree as ET
from xml.dom import minidom


class SEOService:
    """Service for SEO optimization tasks."""
    
    @staticmethod
    def generate_sitemap():
        """
        Generate XML sitemap for all public pages.
        
        Returns:
            str: XML sitemap content
        """
        urlset = ET.Element('urlset')
        urlset.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
        urlset.set('xmlns:xhtml', 'http://www.w3.org/1999/xhtml')
        urlset.set('xmlns:image', 'http://www.google.com/schemas/sitemap-image/1.1')
        
        base_url = request.url_root.rstrip('/')
        
        # Homepage
        SEOService._add_url(urlset, f"{base_url}/", priority='1.0', changefreq='daily')
        
        # Static pages
        static_pages = [
            ('/shop', '0.9', 'daily'),
            ('/blog', '0.8', 'daily'),
            ('/about', '0.7', 'weekly'),
            ('/contact', '0.7', 'monthly'),
            ('/ai-assistant', '0.8', 'weekly'),
        ]
        
        for path, priority, changefreq in static_pages:
            SEOService._add_url(urlset, f"{base_url}{path}", priority=priority, changefreq=changefreq)
        
        # Categories
        categories = Category.query.filter_by(is_active=True).all()
        for category in categories:
            url = f"{base_url}/category/{category.slug}"
            SEOService._add_url(urlset, url, priority='0.8', changefreq='weekly')
        
        # Products
        products = Product.query.filter_by(is_active=True).all()
        for product in products:
            url = f"{base_url}/product/{product.id}"
            lastmod = product.updated_at or product.created_at
            SEOService._add_url(
                urlset, url, 
                priority='0.9', 
                changefreq='weekly',
                lastmod=lastmod,
                image_url=product.image_url
            )
        
        # Blog posts
        posts = BlogPost.query.filter_by(is_published=True).all()
        for post in posts:
            url = f"{base_url}/blog/{post.slug}"
            SEOService._add_url(
                urlset, url,
                priority='0.7',
                changefreq='monthly',
                lastmod=post.updated_at or post.created_at,
                image_url=post.featured_image
            )
        
        return SEOService._prettify_xml(urlset)
    
    @staticmethod
    def generate_products_sitemap():
        """Generate dedicated sitemap for products only."""
        urlset = ET.Element('urlset')
        urlset.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
        urlset.set('xmlns:image', 'http://www.google.com/schemas/sitemap-image/1.1')
        
        base_url = request.url_root.rstrip('/')
        products = Product.query.filter_by(is_active=True).all()
        
        for product in products:
            url = f"{base_url}/product/{product.id}"
            lastmod = product.updated_at or product.created_at
            SEOService._add_url(
                urlset, url,
                priority='1.0',
                changefreq='daily',
                lastmod=lastmod,
                image_url=product.image_url
            )
        
        return SEOService._prettify_xml(urlset)
    
    @staticmethod
    def generate_blog_sitemap():
        """Generate dedicated sitemap for blog posts."""
        urlset = ET.Element('urlset')
        urlset.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')
        urlset.set('xmlns:image', 'http://www.google.com/schemas/sitemap-image/1.1')
        
        base_url = request.url_root.rstrip('/')
        posts = BlogPost.query.filter_by(is_published=True).all()
        
        for post in posts:
            url = f"{base_url}/blog/{post.slug}"
            SEOService._add_url(
                urlset, url,
                priority='0.8',
                changefreq='weekly',
                lastmod=post.updated_at or post.created_at,
                image_url=post.featured_image
            )
        
        return SEOService._prettify_xml(urlset)
    
    @staticmethod
    def _add_url(parent, loc, priority='0.5', changefreq='weekly', lastmod=None, image_url=None):
        """Add URL entry to sitemap."""
        url = ET.SubElement(parent, 'url')
        
        loc_elem = ET.SubElement(url, 'loc')
        loc_elem.text = loc
        
        if lastmod:
            lastmod_elem = ET.SubElement(url, 'lastmod')
            if isinstance(lastmod, datetime):
                lastmod_elem.text = lastmod.strftime('%Y-%m-%d')
            else:
                lastmod_elem.text = str(lastmod)
        
        changefreq_elem = ET.SubElement(url, 'changefreq')
        changefreq_elem.text = changefreq
        
        priority_elem = ET.SubElement(url, 'priority')
        priority_elem.text = priority
        
        # Add image if provided
        if image_url:
            image_elem = ET.SubElement(url, '{http://www.google.com/schemas/sitemap-image/1.1}image')
            image_loc = ET.SubElement(image_elem, '{http://www.google.com/schemas/sitemap-image/1.1}loc')
            image_loc.text = image_url
    
    @staticmethod
    def _prettify_xml(elem):
        """Return a pretty-printed XML string."""
        rough_string = ET.tostring(elem, encoding='utf-8', method='xml')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ", encoding='utf-8').decode('utf-8')
    
    @staticmethod
    def generate_product_schema(product):
        """
        Generate JSON-LD structured data for product.
        
        Args:
            product: Product model instance
            
        Returns:
            dict: Schema.org Product structured data
        """
        schema = {
            "@context": "https://schema.org/",
            "@type": "Product",
            "name": product.name,
            "description": product.description or f"Buy {product.name} online at SmartShop",
            "sku": product.sku or f"PROD-{product.id}",
            "image": product.image_url,
            "brand": {
                "@type": "Brand",
                "name": "SmartShop"
            },
            "offers": {
                "@type": "Offer",
                "url": url_for('product_page', product_id=product.id, _external=True),
                "priceCurrency": "EUR",
                "price": float(product.price),
                "availability": "https://schema.org/InStock" if product.stock > 0 else "https://schema.org/OutOfStock",
                "itemCondition": "https://schema.org/NewCondition"
            }
        }
        
        # Add rating if available (placeholder - implement reviews later)
        if hasattr(product, 'rating') and product.rating:
            schema["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": product.rating,
                "bestRating": "5",
                "worstRating": "1",
                "ratingCount": getattr(product, 'review_count', 1)
            }
        
        return schema
    
    @staticmethod
    def generate_organization_schema():
        """Generate JSON-LD for Organization."""
        return {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "SmartShop AI",
            "url": request.url_root.rstrip('/'),
            "logo": f"{request.url_root}static/images/logo.png",
            "description": "AI-powered online shopping platform with intelligent product recommendations",
            "contactPoint": {
                "@type": "ContactPoint",
                "telephone": "+49-XXX-XXXXXXX",
                "contactType": "Customer Service",
                "areaServed": ["DE", "EU"],
                "availableLanguage": ["en", "de", "uk"]
            },
            "sameAs": [
                "https://facebook.com/smartshop",
                "https://twitter.com/smartshop",
                "https://instagram.com/smartshop"
            ]
        }
    
    @staticmethod
    def generate_breadcrumb_schema(breadcrumbs):
        """
        Generate JSON-LD breadcrumb structured data.
        
        Args:
            breadcrumbs: List of tuples [(name, url), ...]
            
        Returns:
            dict: Schema.org BreadcrumbList
        """
        items = []
        for position, (name, url) in enumerate(breadcrumbs, start=1):
            items.append({
                "@type": "ListItem",
                "position": position,
                "name": name,
                "item": url
            })
        
        return {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": items
        }
    
    @staticmethod
    def generate_blog_schema(post):
        """Generate JSON-LD for blog post."""
        schema = {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": post.title,
            "description": post.excerpt or post.title,
            "image": post.featured_image,
            "datePublished": post.created_at.isoformat() if post.created_at else None,
            "dateModified": post.updated_at.isoformat() if post.updated_at else post.created_at.isoformat(),
            "author": {
                "@type": "Person",
                "name": "SmartShop Editorial Team"
            },
            "publisher": {
                "@type": "Organization",
                "name": "SmartShop AI",
                "logo": {
                    "@type": "ImageObject",
                    "url": f"{request.url_root}static/images/logo.png"
                }
            }
        }
        
        return schema
    
    @staticmethod
    def generate_local_business_schema():
        """Generate JSON-LD for LocalBusiness (if applicable)."""
        return {
            "@context": "https://schema.org",
            "@type": "OnlineStore",
            "name": "SmartShop AI",
            "description": "AI-powered online shopping with smart product recommendations",
            "url": request.url_root.rstrip('/'),
            "telephone": "+49-XXX-XXXXXXX",
            "email": "info@smartshop.com",
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
                "dayOfWeek": [
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday"
                ],
                "opens": "09:00",
                "closes": "18:00"
            },
            "priceRange": "€€",
            "currenciesAccepted": "EUR",
            "paymentAccepted": "Credit Card, PayPal, Stripe"
        }
    
    @staticmethod
    def generate_meta_tags(page_type='default', title=None, description=None, image=None, url=None):
        """
        Generate meta tags for SEO and social sharing.
        
        Args:
            page_type: Type of page (default, product, blog, etc.)
            title: Page title
            description: Page description
            image: Image URL for social sharing
            url: Canonical URL
            
        Returns:
            dict: Meta tags data
        """
        base_url = request.url_root.rstrip('/')
        default_image = f"{base_url}/static/images/og-default.jpg"
        
        # Defaults
        meta = {
            'title': title or 'SmartShop AI - Intelligent Online Shopping',
            'description': description or 'AI-powered online shopping platform with smart product recommendations. Find the best products with our intelligent assistant.',
            'image': image or default_image,
            'url': url or request.url,
            'site_name': 'SmartShop AI',
            'locale': 'en_US',
            'type': 'website' if page_type == 'default' else page_type
        }
        
        # Twitter Card
        meta['twitter_card'] = 'summary_large_image'
        meta['twitter_site'] = '@smartshop'
        meta['twitter_creator'] = '@smartshop'
        
        return meta
