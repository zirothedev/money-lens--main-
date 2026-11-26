from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom user model (set up now so it never needs a painful swap later)."""
