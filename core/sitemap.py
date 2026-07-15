"""
Dynamic XML sitemap for the public Vue frontend's own routes - not the Django API's routes,
which is why URLs here are built off settings.FRONTEND_URL rather than request.build_absolute_uri().
django.contrib.sitemaps isn't used: that framework resolves its domain via django.contrib.sites
(or the request host), both of which would point at this API's own host - wrong, since the pages
search engines actually need to index are served by the separate frontend origin.

Served at the site's own domain root (/sitemap.xml, wired outside the api/ prefix in
silverlake/urls.py), not under /api/ - that's where crawlers and Search Console expect it. In
production this requires the reverse proxy/static host in front of the frontend build to forward
GET /sitemap.xml through to this Django backend rather than 404ing on it as a missing static file.
"""
from django.conf import settings
from django.http import HttpResponse

from blog.models import BlogPost
from fleet.models import visible_vehicles

# path, changefreq, priority - content that rarely changes and isn't backed by a queryset below.
STATIC_PAGES = [
    ('/', 'weekly', '1.0'),
    ('/fleet', 'daily', '0.9'),
    ('/drivers', 'weekly', '0.6'),
    ('/reviews', 'weekly', '0.6'),
    ('/blog', 'daily', '0.7'),
    ('/become-a-driver', 'monthly', '0.5'),
    ('/contact', 'monthly', '0.4'),
    ('/terms', 'yearly', '0.2'),
    ('/privacy', 'yearly', '0.2'),
    ('/refund-policy', 'yearly', '0.2'),
]


def _url_entry(loc, lastmod=None, changefreq=None, priority=None):
    parts = [f'  <url>\n    <loc>{loc}</loc>\n']
    if lastmod:
        parts.append(f'    <lastmod>{lastmod.strftime("%Y-%m-%d")}</lastmod>\n')
    if changefreq:
        parts.append(f'    <changefreq>{changefreq}</changefreq>\n')
    if priority:
        parts.append(f'    <priority>{priority}</priority>\n')
    parts.append('  </url>\n')
    return ''.join(parts)


def sitemap_view(request):
    base = settings.FRONTEND_URL.rstrip('/')
    entries = [
        _url_entry(f'{base}{path}', changefreq=changefreq, priority=priority)
        for path, changefreq, priority in STATIC_PAGES
    ]
    entries += [
        _url_entry(f'{base}/fleet/{vehicle.id}', lastmod=vehicle.updated_at, changefreq='weekly', priority='0.8')
        for vehicle in visible_vehicles().only('id', 'updated_at')
    ]
    entries += [
        _url_entry(f'{base}/blog/{post.slug}', lastmod=post.updated_at, changefreq='monthly', priority='0.6')
        for post in BlogPost.objects.filter(is_published=True).only('slug', 'updated_at')
    ]

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + ''.join(entries) +
        '</urlset>\n'
    )
    return HttpResponse(xml, content_type='application/xml')
