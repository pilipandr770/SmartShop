# SmartShop i18n Deployment Guide

## Phase D: Deploy to VPS

### VPS Deployment Steps

```bash
# SSH into VPS
ssh root@YOUR_VPS_IP

# Navigate to project
cd /path/to/SmartShop

# Pull latest changes
git pull origin main

# Rebuild Docker containers
docker compose up -d --build web

# Verify migration & deployment
docker compose logs web | tail -20

# Check if .mo files are in container
docker exec smartshop-web-1 ls -lh translations/*/LC_MESSAGES/*.mo
```

### What was deployed:

**Phase A - Foundations:**
- ✅ Order.locale column added (tracks customer's UI language at checkout)
- ✅ Email locale support (transactional emails send in customer's selected language)
- ✅ 127+ flash() messages wrapped in _() for translation
- ✅ Language switcher added to admin panel and landing page

**Phase B - Template Wrapping:**
- ✅ ~50 templates wrapped with {{ _('...') }} calls
- ✅ 164 flash/validation messages in routes wrapped
- ✅ Jinja2 gettext integration working

**Phase C - Translation Catalogs:**
- ✅ 164 German translations compiled to messages.mo
- ✅ 118 English translations compiled to messages.mo  
- ✅ Ukrainian: 100% complete (1415 strings native)
- ✅ Babel extract/update/compile pipeline verified

### Post-Deployment Testing

1. **Test language switching on live site:**
```bash
curl -s "https://smartshop.de/?lang=de" | grep -o '<html lang="[^"]*"'
curl -s "https://smartshop.de/?lang=en" | grep -o '<html lang="[^"]*"'
curl -s "https://smartshop.de/?lang=uk" | grep -o '<html lang="[^"]*"'
```

2. **Test admin panel (if accessible):**
   - Login to admin
   - Navigate to Settings
   - Click language flags (🇺🇦 🇬🇧 🇩🇪)
   - Verify UI text changes

3. **Test customer cabinet:**
   - Login as customer
   - Place test order
   - Switch languages via flags
   - Verify cart/checkout text translates

4. **Test emails:**
   - Place order with German locale selected
   - Check order confirmation email language

### Monitoring

```bash
# Check logs for translation errors
docker compose logs web | grep -i "babel\|gettext\|locale"

# Monitor Flask startup
docker compose logs web | grep "✅" | head -20
```

### Known Limitations

- ~1250 msgids per locale are untranslated (fallback to Ukrainian msgid text)
- Page titles/meta tags remain Ukrainian (not wrapped in i18n yet)
- Legal pages (Datenschutz/AGB/Impressum) stay German-only (by design)

### Rollback (if needed)

```bash
git revert 6ead2b9
docker compose up -d --build web
```

---

**Deployment Date:** 2026-07-29
**Deployed By:** Claude Code  
**Status:** Ready for production testing
