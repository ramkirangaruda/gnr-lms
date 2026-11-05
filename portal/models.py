from django.conf import settings
from django.db import models
from django.utils import timezone


class Newsletter(models.Model):
    title = models.CharField(max_length=200)
    summary = models.CharField(max_length=300, blank=True)
    body = models.TextField(blank=True)
    cover = models.ImageField(upload_to="newsletters/", blank=True)
    pdf = models.FileField(upload_to="newsletters/pdf/", blank=True, help_text="Optional PDF edition")
    is_published = models.BooleanField(default=True)
    published_on = models.DateField(default=timezone.localdate)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-published_on", "-id"]

    def __str__(self):
        return self.title


class GalleryItem(models.Model):
    title = models.CharField(max_length=200)
    image = models.ImageField(upload_to="gallery/")
    caption = models.CharField(max_length=300, blank=True)
    event = models.CharField(max_length=150, blank=True, help_text="Group photos by event, e.g. 'RoboFest 2026'")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Competition(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    banner = models.ImageField(upload_to="competitions/", blank=True)
    event_date = models.DateField()
    registration_deadline = models.DateField(null=True, blank=True)
    venue = models.CharField(max_length=200, blank=True)
    eligibility = models.CharField(max_length=200, blank=True, help_text="e.g. Grades 6-10")
    prizes = models.TextField(blank=True)
    registration_link = models.URLField(blank=True)
    results = models.TextField(blank=True, help_text="Fill in after the event")
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-event_date"]

    @property
    def is_upcoming(self):
        return self.event_date >= timezone.localdate()

    def __str__(self):
        return self.title
