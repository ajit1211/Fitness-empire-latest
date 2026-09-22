"""URL configuration for FitnessEmpire."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('FitnessGYM.urls')),
    # django-paypal maps its IPN view to r'^$'. Mounted at the project root it
    # collided with the homepage, which FitnessGYM.urls already claims, so every
    # server-to-server notification from PayPal landed on the home view and was
    # silently dropped. It needs a prefix of its own.
    path('paypal/', include('paypal.standard.ipn.urls')),
    path('', include('rest_framework.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.SERVE_MEDIA_FILES:
    # Product images ship with the repository, and the deployed host has no web
    # server in front of Django to hand them out. Django's own file server is
    # normally a bad idea in production, but here it is serving a fixed set of
    # committed images on a read-only filesystem, and the alternative is broken
    # pictures. Move MEDIA_ROOT to object storage and switch
    # SERVE_MEDIA_FILES off once uploads need to persist.
    urlpatterns += [
        path(
            'media/<path:path>',
            serve,
            {'document_root': settings.MEDIA_ROOT},
            name='media',
        ),
    ]
