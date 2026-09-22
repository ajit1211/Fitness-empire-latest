"""Template context shared by every page.

The navbar shows a cart badge on all pages. Previously it read `products` from
the view context, so the count was only correct on the two views that happened
to define that name and was blank everywhere else.
"""

from django.db.models import Sum

from .models import cart


def cart_summary(request):
    """Expose `cart_count` (total item quantity) to every template."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"cart_count": 0}

    total = cart.objects.filter(userid=user).aggregate(n=Sum("quantity"))["n"]
    return {"cart_count": total or 0}
