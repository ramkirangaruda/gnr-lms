from django.contrib.auth.hashers import PBKDF2PasswordHasher


class TemporaryPasswordHasher(PBKDF2PasswordHasher):
    """For auto-generated first passwords only (the student must replace it at first login).

    Bulk-creating 500 logins with the normal 1,000,000-iteration hash took ~90 s of CPU; this takes a few seconds.
    The random 8-character password (31^8 combinations) is still slow to crack, and Django re-hashes it at full
    strength on the first successful login, just before the forced password change replaces it.
    """
    algorithm = "pbkdf2_temp"
    iterations = 20_000
