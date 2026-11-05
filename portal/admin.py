from django.contrib import admin

from .models import Competition, GalleryItem, Newsletter

admin.site.register([Newsletter, GalleryItem, Competition])
