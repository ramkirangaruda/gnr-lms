from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

MAX_IMAGE_MB = 10

# Worksheets, slides, code and models. No .html/.svg/.js: those could run script on the LMS's own address.
ATTACHMENT_EXTENSIONS = ["pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "odt", "odp", "ods", "txt", "csv", "md",
                         "zip", "ino", "py", "c", "cpp", "h", "hpp", "java", "json", "sb3", "stl", "step", "stp",
                         "fzz", "png", "jpg", "jpeg", "gif", "webp", "mp3", "wav"]
attachment_extension = FileExtensionValidator(ATTACHMENT_EXTENSIONS)


def image_size(f):
    if f and getattr(f, "size", 0) > MAX_IMAGE_MB * 1024 * 1024:
        raise ValidationError(f"Please upload a picture smaller than {MAX_IMAGE_MB} MB.")
