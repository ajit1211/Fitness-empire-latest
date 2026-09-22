"""Template context shared by every page.

The navbar shows a cart badge on all pages. Previously it read `products` from
the view context, so the count was only correct on the two views that happened
to define that name and was blank everywhere else.
"""

from django.conf import settings
from django.db.models import Sum

from .models import Wishlist, cart


def cart_summary(request):
    """Expose the navbar counters and the set of saved product ids.

    `wishlist_ids` lets any product card render its heart in the right state
    without a per-card query.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"cart_count": 0, "wishlist_count": 0, "wishlist_ids": set()}

    total = cart.objects.filter(userid=user).aggregate(n=Sum("quantity"))["n"]
    saved = set(
        Wishlist.objects.filter(user=user).values_list("product_id", flat=True)
    )
    return {
        "cart_count": total or 0,
        "wishlist_count": len(saved),
        "wishlist_ids": saved,
    }


def demo_notice(request):
    """Expose whether the deployment is running on configuration fallbacks.

    A site running without a real database looks completely normal, right up
    until someone places an order that quietly disappears. The banner this
    feeds is the only thing standing between that and a confused customer, so
    it is wired into every page rather than a single template.
    """
    return {
        "demo_mode": getattr(settings, "DEMO_MODE", False),
        "demo_reasons": getattr(settings, "DEMO_REASONS", []),
    }
