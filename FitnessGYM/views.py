"""Views for the Fitness Empire storefront.

Notes on this revision:
* Duplicate view definitions were removed (``crud``, ``showdetails`` and
  ``register`` were each declared twice, so the first copy was dead code).
* Every view that reads ``request.user`` now requires a login; previously an
  anonymous visitor silently got an empty page instead of the sign-in screen.
* Cart/order queries use ``select_related`` so a page with N rows issues one
  query instead of N+1.
* Order status is stored using the model's own choice values, so the
  case-sensitive comparisons that never matched are gone.
"""

import datetime
import random
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from paypal.standard.forms import PayPalPaymentsForm
from rest_framework import status
from rest_framework.decorators import APIView
from rest_framework.response import Response

from .form import (
    RegisterForm,
    SupplementForm,
    UserProfileForm,
    membershipprocessedtocheckform,
    processedtocheckform,
    userAuthentication,
)
from .models import (
    Category,
    Customer,
    FitnessClass,
    FitnessProgram,
    Membership,
    Membershipmonth,
    Orders,
    Product,
    Supplement,
    SupplementCategory,
    Trainer,
    UserProfile,
    Wishlist,
    aboutus,
    cart,
    membershipprocessedtocheck,
    processedtocheck,
)
from .serializers import customerSerializer

GST_RATE = Decimal("0.18")

# A shopper may not stack more than this many units of one product in a single
# order. Enforced in the cart, in "Buy now" and on the quantity stepper.
MAX_QTY_PER_ITEM = 5

# Session key holding a pending "Buy now" purchase, so a direct buy can reach
# checkout without being mixed into (or wiping) whatever is in the cart.
BUY_NOW_KEY = "buy_now"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def delivery_charge_for(total):
    """Tiered delivery pricing, in one place instead of copy-pasted per view."""
    total = Decimal(total or 0)
    if total <= 0:
        return Decimal("0")
    if total <= 2000:
        return Decimal("120")
    if total <= 5000:
        return Decimal("70")
    return Decimal("0")


def cart_for(user):
    """Cart rows for a user, with the product joined in a single query."""
    return (
        cart.objects.filter(userid=user)
        .select_related("productid", "productid__supplementCategory")
        .order_by("id")
    )


def cart_totals(items):
    subtotal = sum(
        (row.productid.supplementPrice * row.quantity for row in items),
        Decimal("0"),
    )
    delivery = delivery_charge_for(subtotal)
    return {
        "total": subtotal,
        "delivery_charge": delivery,
        "grand_total": subtotal + delivery,
        "totalCount": sum(row.quantity for row in items),
    }


def to_usd(amount_inr):
    """Convert a rupee amount to the USD figure PayPal is actually charged.

    The button has always been submitted with ``currency_code="USD"`` while the
    rupee total was passed straight through, so a 6,450 rupee basket asked
    PayPal for 6,450 US dollars. Converting here keeps the sandbox amount
    plausible; set ``INR_TO_USD_RATE`` to whatever rate you want to quote.
    """
    rate = Decimal(str(getattr(settings, "INR_TO_USD_RATE", "0.012")))
    usd = (Decimal(amount_inr or 0) * rate).quantize(Decimal("0.01"))
    # PayPal rejects a zero-value order, so never fall below one cent.
    return max(usd, Decimal("0.01"))


def paypal_form(request, *, amount, item_name, return_url_name):
    """Build the PayPal button form used by the checkout screens."""
    host = request.get_host()
    scheme = "https" if request.is_secure() else "http"
    return PayPalPaymentsForm(
        initial={
            "business": settings.PAYPAL_RECEIVER_EMAIL,
            "amount": to_usd(amount),
            "item_name": item_name,
            "invoice": uuid.uuid4(),
            "currency_code": "USD",
            "notify_url": f"{scheme}://{host}{reverse('paypal-ipn')}",
            "return_url": f"{scheme}://{host}{reverse(return_url_name)}",
            "cancel_url": f"{scheme}://{host}{reverse('paymentfailed')}",
        }
    )


# ---------------------------------------------------------------------------
# "Buy now" - a single product taken to checkout without touching the cart
# ---------------------------------------------------------------------------
class DirectLine:
    """One product being bought directly.

    It exposes the same attribute names as a ``cart`` row (``productid``,
    ``quantity``) so every checkout template and total helper works on a direct
    purchase without a single template branch.
    """

    def __init__(self, product, quantity, user=None):
        self.id = None
        self.productid = product
        self.productid_id = product.id
        self.quantity = quantity
        self.userid = user

    def delete(self):
        """No-op: a direct line lives in the session, not the cart table."""


def clear_buy_now(request):
    """Drop any pending direct purchase."""
    if request.session.pop(BUY_NOW_KEY, None) is not None:
        request.session.modified = True


def set_buy_now(request, product, quantity):
    request.session[BUY_NOW_KEY] = {"product": product.id, "quantity": quantity}
    request.session.modified = True


def buy_now_line(request):
    """The pending direct purchase, or ``None``.

    Re-reads the product every time so a price change, a stock drop or a
    soft-delete between clicking "Buy now" and paying is picked up.
    """
    data = request.session.get(BUY_NOW_KEY)
    if not isinstance(data, dict):
        return None

    product = Supplement.objects.filter(
        id=data.get("product"), is_deleted=False
    ).select_related("supplementCategory").first()

    if product is None or product.stock <= 0:
        clear_buy_now(request)
        return None

    try:
        quantity = int(data.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1

    quantity = max(1, min(quantity, MAX_QTY_PER_ITEM, product.stock))
    return DirectLine(product, quantity, getattr(request, "user", None))


def checkout_lines(request):
    """What the shopper is about to pay for.

    Returns ``(lines, is_direct)``. A pending "Buy now" wins over the cart, so
    a direct purchase cannot accidentally bill the whole basket.
    """
    line = buy_now_line(request)
    if line is not None:
        return [line], True
    return list(cart_for(request.user)), False


def safe_redirect_target(request, fallback="wishlist"):
    """A caller-supplied return URL, but only if it stays on this site.

    `next` arrives in a form field and the referer in a header, so neither can
    be trusted to point at us; handing either straight to `redirect` would turn
    the view into an open redirect.
    """
    for candidate in (request.POST.get("next"), request.META.get("HTTP_REFERER")):
        if candidate and url_has_allowed_host_and_scheme(
            candidate,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return candidate
    return fallback


def wants_json(request):
    """True when the caller is our own fetch() rather than a form post."""
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def cart_badge(user):
    """Cart and wishlist counters, for the navbar badges in a JSON reply."""
    return {
        "cart_count": cart.objects.filter(userid=user).aggregate(n=Sum("quantity"))["n"]
        or 0,
        "wishlist_count": Wishlist.objects.filter(user=user).count(),
    }


# ---------------------------------------------------------------------------
# Membership tiers
#
# Plans form a ladder (Core, Premier, Executive) in each billing cycle. What a
# member may do with a given plan depends only on what they already hold, so
# that decision lives in `plan_offer()` and every membership view asks it
# rather than re-deriving the rules.
# ---------------------------------------------------------------------------
def member_record(user):
    """The membership row for a user, with both plans and both pendings joined."""
    if not user.is_authenticated:
        return None
    return (
        membershipprocessedtocheck.objects.filter(user=user)
        .select_related(
            "membership_yearly",
            "membership_monthly",
            "pending_yearly",
            "pending_monthly",
        )
        .first()
    )


def plan_offer(record, plan, cycle):
    """What this member can do with `plan`, and what it would cost.

    Returns a dict the plan templates render directly:
        state    one of buy / current / upgrade / lower / finish / locked
        cta      button wording, or None when there is nothing to click
        amount   price before tax, for buy and upgrade
        credit   unused value rolled into an upgrade
        note     why the plan is unavailable, when it is
        allowed  True when the member may start this purchase
    """
    def offer(state, cta=None, amount=None, credit=None, note="", allowed=False):
        return {
            "plan": plan,
            "cycle": cycle,
            "state": state,
            "cta": cta,
            "amount": amount,
            "credit": credit,
            "note": note,
            "allowed": allowed,
        }

    # Nobody signed in, or nothing on the account yet, or the last plan lapsed:
    # every plan is simply for sale.
    if record is None or not (record.is_active or record.awaiting_first_payment):
        return offer("buy", "Buy Now", amount=plan.price, allowed=True)

    # A first purchase was started but never paid for. Only that plan is live.
    if record.awaiting_first_payment:
        if record.cycle == cycle and record.plan.id == plan.id:
            return offer(
                "finish",
                "Complete Payment",
                amount=plan.price,
                note="You started this plan. Finish paying to activate it.",
                allowed=True,
            )
        return offer(
            "locked",
            note=f"Finish paying for {record.plan.name} before choosing another plan.",
        )

    # An upgrade is parked and waiting for payment.
    if record.has_pending_upgrade:
        if record.pending_cycle == cycle and record.pending_plan.id == plan.id:
            return offer(
                "finish",
                "Complete Upgrade",
                amount=record.pending_amount,
                credit=record.unused_credit(),
                note="Your upgrade is waiting for payment.",
                allowed=True,
            )
        if record.cycle == cycle and record.plan.id == plan.id:
            return offer("current", note="Your current plan.")
        return offer(
            "locked",
            note=f"You have an upgrade to {record.pending_plan.name} awaiting payment.",
        )

    # An active plan on the other billing cycle. Switching cycle mid-term is not
    # a tier change and is not priced here, so it stays closed.
    if record.cycle != cycle:
        other = "monthly" if cycle == "annual" else "annual"
        return offer(
            "locked",
            note=f"You are on the {other} plan {record.plan.name}. Upgrade within {other} billing.",
        )

    current = record.plan
    if plan.id == current.id:
        return offer("current", note="Your current plan.")

    if plan.tier > current.tier:
        return offer(
            "upgrade",
            f"Upgrade from {current.name}",
            amount=record.upgrade_cost(plan),
            credit=record.unused_credit(),
            allowed=True,
        )

    return offer("lower", note=f"{current.name} already covers everything here.")


def plan_offers(user, plans, cycle):
    """`plan_offer` across a whole tier ladder, for the plan listing pages."""
    record = member_record(user)
    offers = [plan_offer(record, plan, cycle) for plan in plans]

    # The middle tier carries the "Most popular" flag. Decided here because a
    # template cannot compare a loop counter inside an include.
    for position, offer in enumerate(offers):
        offer["featured"] = position == 1
    return offers


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------
def home(request):
    context = {
        "memberships": Membership.objects.all()[:3],
        "classes": FitnessClass.objects.select_related("category")[:10],
        "featured": Supplement.objects.filter(is_deleted=False).select_related(
            "supplementCategory"
        )[:4],
        "trainer_count": Trainer.objects.count(),
        "class_count": FitnessClass.objects.count(),
        "program_count": FitnessProgram.objects.count(),
    }
    return render(request, "index.html", context)


def about_us(request):
    success_message = ""
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        email = (request.POST.get("email") or "").strip()
        message = (request.POST.get("message") or "").strip()

        if name and email and message:
            aboutus.objects.create(name=name, email=email, message=message)
            success_message = "Thank you! Your message has been received."
            messages.success(request, success_message)
            return redirect("aboutus")
        messages.error(request, "Please fill in your name, email and message.")

    return render(request, "aboutus.html", {"success_message": success_message})


def careers(request):
    return render(request, "careers.html")


def training(request):
    return render(request, "training.html")


def diet_plan(request):
    return render(request, "dietplan.html")


def weightlossplan(request):
    return render(request, "weightlossplan.html")


def muselloss(request):
    return render(request, "musel.html")


def healthlyplan(request):
    return render(request, "healthlyplan.html")


def plantbasedplan(request):
    return render(request, "plantbasedplan.html")


# A single category tab shows at most this many classes. The "All" tab is
# never capped, so every class is always reachable from there.
CLASSES_PER_CATEGORY_MAX = 10


def fitness_classes(request, category_name=None):
    categories = Category.objects.all()
    classes = FitnessClass.objects.select_related("category")

    if category_name and category_name.lower() != "all":
        classes = classes.filter(category__name__iexact=category_name)[
            :CLASSES_PER_CATEGORY_MAX
        ]

    return render(
        request,
        "fitness_classes.html",
        {
            "categories": categories,
            "selected_category": category_name or "All",
            "classes": classes,
        },
    )


# ---------------------------------------------------------------------------
# Memberships
# ---------------------------------------------------------------------------
def memberships(request):
    plans = list(Membership.objects.all())
    return render(
        request,
        "membershipannual.html",
        {
            "memberships": plans,
            "offers": plan_offers(request.user, plans, "annual"),
            "record": member_record(request.user),
        },
    )


def membershipmonthly(request):
    plans = list(Membershipmonth.objects.all())
    return render(
        request,
        "membershipmonthly.html",
        {
            "Membershipmonth": plans,
            "offers": plan_offers(request.user, plans, "monthly"),
            "record": member_record(request.user),
        },
    )


def _choose_plan(request, plan, cycle, template, checkout_url_name):
    """Shared body of the yearly and monthly plan forms.

    Handles three cases behind one screen: a first purchase, an upgrade to a
    higher tier on the same billing cycle, and resuming a payment that was
    already started. Anything else is refused by `plan_offer`.
    """
    record = member_record(request.user)
    offer = plan_offer(record, plan, cycle)

    if not offer["allowed"]:
        messages.warning(
            request, offer["note"] or "That plan is not available on your account."
        )
        return redirect("profile")

    # Already chosen and waiting on payment: skip the form, go pay.
    if offer["state"] == "finish":
        return redirect(checkout_url_name, id=plan.id)

    is_upgrade = offer["state"] == "upgrade"
    amount = offer["amount"]
    total_price = amount + (amount * GST_RATE)

    if request.method == "POST":
        # Bind to the row already on the account when there is one. A member
        # whose plan lapsed still has a record, and the model is OneToOne with
        # the user, so inserting a second row would fail the unique constraint.
        form = membershipprocessedtocheckform(request.POST, instance=record)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.user = request.user

            if is_upgrade:
                # The live plan and its expiry stay exactly as they are until
                # the upgrade is paid for.
                saved.save()
                saved.start_upgrade(plan, cycle, amount)
                messages.success(
                    request, f"Pay the difference to move up to {plan.name}."
                )
            else:
                if cycle == "annual":
                    saved.membership_yearly = plan
                    saved.membership_monthly = None
                else:
                    saved.membership_monthly = plan
                    saved.membership_yearly = None
                # A lapsed membership being renewed needs a fresh term, and
                # save() only fills the expiry when it is empty.
                saved.plan_expiry = None
                saved.payment_status = False
                saved.save()
                messages.success(
                    request, "Proceed to payment to complete your membership."
                )
            return redirect(checkout_url_name, id=plan.id)
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = membershipprocessedtocheckform(
            instance=record,
            initial=None if record else _member_initial(request.user),
        )

    return render(
        request,
        template,
        {
            "form": form,
            "membership": plan,
            "total_price": total_price,
            "amount": amount,
            "is_upgrade": is_upgrade,
            "credit": offer["credit"],
            "current_plan": record.plan if is_upgrade else None,
        },
    )


@login_required(login_url="login")
def membership_processed_view(request, id):
    """Collect member details for a yearly plan."""
    return _choose_plan(
        request,
        get_object_or_404(Membership, id=id),
        "annual",
        "membership_form.html",
        "membershipprocessedtocheckouts",
    )


@login_required(login_url="login")
def membership_processed_view_month(request, id):
    """Collect member details for a monthly plan."""
    return _choose_plan(
        request,
        get_object_or_404(Membershipmonth, id=id),
        "monthly",
        "membership_form_month.html",
        "membershipprocessedtocheckout",
    )


def _member_initial(user):
    """Pre-fill the membership form from the user's profile."""
    profile = UserProfile.objects.filter(user=user).first()
    return {
        "full_name": (profile.full_name if profile else "") or user.get_full_name(),
        "email": (profile.email if profile else "") or user.email,
        "phone_number": profile.phone if profile else "",
    }


def _membership_payment(request, plan, cycle, template):
    """Payment screen for a plan, whether it is a first purchase or an upgrade.

    An upgrade bills the quoted difference rather than the sticker price, so
    the amount comes off the record instead of the plan.
    """
    record = member_record(request.user)
    if record is None:
        messages.warning(request, "No pending payment found.")
        return redirect("profile")

    is_upgrade = record.has_pending_upgrade and record.pending_plan.id == plan.id
    starting = record.awaiting_first_payment and record.plan_id_matches(plan, cycle)

    if not (is_upgrade or starting):
        messages.warning(request, "No pending payment found.")
        return redirect("profile")

    amount = record.pending_amount if is_upgrade else plan.price
    gst = amount * GST_RATE
    total_price = amount + gst

    return render(
        request,
        template,
        {
            "membership": plan,
            "record": record,
            "amount": amount,
            "gst": gst,
            "total_price": total_price,
            "is_upgrade": is_upgrade,
            "credit": record.unused_credit() if is_upgrade else None,
            "current_plan": record.plan if is_upgrade else None,
            "paypalpayment": paypal_form(
                request,
                # Previously this charged the pre-GST price while the page
                # displayed the GST-inclusive total.
                amount=total_price,
                item_name=(
                    f"Upgrade to {plan.name}" if is_upgrade else plan.name
                ),
                return_url_name="paymentmembership",
            ),
        },
    )


@login_required(login_url="login")
def membership_processedtocheckout(request, id):
    """Payment screen for a yearly plan."""
    return _membership_payment(
        request,
        get_object_or_404(Membership, id=id),
        "annual",
        "membershipprocessedtocheckout.html",
    )


@login_required(login_url="login")
def membership_processedtocheckout_monthly(request, id):
    """Payment screen for a monthly plan."""
    return _membership_payment(
        request,
        get_object_or_404(Membershipmonth, id=id),
        "monthly",
        "membershipprocessedtocheckoutmonthly.html",
    )


@login_required(login_url="login")
def cancel_membership_purchase(request):
    """Drop a membership that was chosen but never paid for.

    Only ever touches an unpaid selection. An active plan cannot be cancelled
    here, so a mistaken click can never delete a membership somebody is
    currently paying for.
    """
    record = member_record(request.user)

    if record is None or not record.awaiting_first_payment:
        messages.info(request, "There is no unpaid membership to cancel.")
        return redirect("profile")

    name = record.plan.name
    record.delete()
    messages.info(
        request, f"{name} cancelled. You have not been charged for it."
    )
    return redirect("profile")


@login_required(login_url="login")
def cancel_membership_upgrade(request):
    """Drop a parked upgrade and keep the plan already in force."""
    record = member_record(request.user)
    if record and record.has_pending_upgrade:
        name = record.pending_plan.name
        record.clear_pending_upgrade()
        messages.info(request, f"Upgrade to {name} cancelled. Your plan is unchanged.")
    return redirect("profile")


@login_required(login_url="login")
def paymentmembership(request):
    record = member_record(request.user)
    upgraded_from = None

    if record and record.has_pending_upgrade:
        # An upgrade: swap the parked tier in, keeping the term already running.
        upgraded_from = record.plan
        new_plan = record.pending_plan
        record.apply_pending_upgrade()
        messages.success(
            request,
            f"Payment successful! You are now on {new_plan.name}.",
        )
    elif record and not record.payment_status:
        record.payment_status = True
        record.save(update_fields=["payment_status"])
        messages.success(request, "Payment successful! Your membership is now active.")
    else:
        messages.warning(request, "No pending membership found.")

    return render(
        request,
        "finalthankyou.html",
        {"membership": record, "upgraded_from": upgraded_from},
    )


@login_required(login_url="login")
def profile_view(request):
    membership = member_record(request.user)
    pending_payment = bool(membership and membership.awaiting_first_payment)

    # The tiers above the one in force, so the member can move up without
    # hunting through the plan pages for which ones are even open to them.
    upgrades = []
    if membership and membership.is_active and not membership.has_pending_upgrade:
        cycle = membership.cycle
        ladder = (
            Membership.objects.filter(tier__gt=membership.plan.tier)
            if cycle == "annual"
            else Membershipmonth.objects.filter(tier__gt=membership.plan.tier)
        )
        upgrades = [
            plan_offer(membership, plan, cycle) for plan in ladder
        ]

    return render(
        request,
        "profile.html",
        {
            "membership": membership,
            "pending_payment": pending_payment,
            "upgrades": upgrades,
            "credit": membership.unused_credit() if membership else None,
        },
    )


# ---------------------------------------------------------------------------
# Shop
# ---------------------------------------------------------------------------
def products(request):
    return render(
        request,
        "protien.html",
        {
            "categories": SupplementCategory.objects.all(),
            "products": Supplement.objects.filter(is_deleted=False).select_related(
                "supplementCategory"
            ),
        },
    )


def category(request, id):
    selected = get_object_or_404(SupplementCategory, id=id)
    return render(
        request,
        "protien.html",
        {
            "categories": SupplementCategory.objects.all(),
            "products": Supplement.objects.filter(
                supplementCategory=selected, is_deleted=False
            ).select_related("supplementCategory"),
            "selected_category": selected,
        },
    )


def cards(request, id):
    product = get_object_or_404(
        Supplement.objects.select_related("supplementCategory"), id=id, is_deleted=False
    )
    related = (
        Supplement.objects.filter(
            supplementCategory=product.supplementCategory, is_deleted=False
        )
        .exclude(id=product.id)
        .select_related("supplementCategory")[:4]
    )

    # The primary action flips to "View cart" once this product is already in
    # the basket, so the page has to know the current line quantity.
    in_cart_qty = 0
    if request.user.is_authenticated:
        row = cart.objects.filter(userid=request.user, productid=product).first()
        in_cart_qty = row.quantity if row else 0

    return render(
        request,
        "cards.html",
        {
            "product": product,
            "related": related,
            "in_cart_qty": in_cart_qty,
            "max_qty": min(MAX_QTY_PER_ITEM, product.stock) or 1,
        },
    )


def searchdata(request):
    query = (request.GET.get("query") or "").strip()

    all_menu_items = [
        {"name": "Memberships", "url": "membershipannual"},
        {"name": "Diet Plan", "url": "dietplan"},
        {"name": "Classes", "url": "all_classes"},
        {"name": "Training", "url": "training"},
        {"name": "Products", "url": "protien"},
        {"name": "About Us", "url": "aboutus"},
        {"name": "Careers", "url": "careers"},
    ]

    results = Supplement.objects.none()
    categories = SupplementCategory.objects.all()
    menu_items = []

    if query:
        results = (
            Supplement.objects.filter(is_deleted=False)
            .filter(
                Q(supplementName__icontains=query)
                | Q(supplementDescription__icontains=query)
                | Q(supplementCategory__categoryName__icontains=query)
            )
            .select_related("supplementCategory")
            .distinct()
        )
        menu_items = [
            item for item in all_menu_items if query.lower() in item["name"].lower()
        ]

    return render(
        request,
        "protien.html",
        {
            "query": query,
            "products": results,
            "categories": categories,
            "menu_items": menu_items,
            "is_search": True,
            "no_results": query and not results.exists() and not menu_items,
        },
    )


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------
def requested_qty(request, product):
    """The quantity asked for, clamped to the stock and the per-item cap."""
    raw = request.POST.get("quantity") or request.GET.get("quantity") or 1
    try:
        qty = int(raw)
    except (TypeError, ValueError):
        qty = 1
    return max(1, min(qty, MAX_QTY_PER_ITEM, product.stock))


@login_required(login_url="login")
def addtocart(request, id):
    """Add a product to the cart.

    Answers JSON when called from the product page's fetch(), so the button can
    flip to "View cart" without a reload, and falls back to a redirect plus a
    flash message when JavaScript is unavailable.
    """
    product = get_object_or_404(Supplement, id=id, is_deleted=False)
    ajax = wants_json(request)

    def reply(ok, message, level="success", **extra):
        if ajax:
            payload = {"ok": ok, "message": message, "level": level}
            payload.update(cart_badge(request.user))
            payload.update(extra)
            return JsonResponse(payload)
        getattr(messages, "success" if ok else "warning")(request, message)
        return redirect("cards", id=product.id)

    if product.stock <= 0:
        return reply(False, f"{product.supplementName} is out of stock.", "warning",
                     in_cart=0)

    wanted = requested_qty(request, product)
    row, created = cart.objects.get_or_create(
        productid=product, userid=request.user, defaults={"quantity": wanted}
    )

    if created:
        return reply(
            True,
            f"{product.supplementName} added to your cart.",
            in_cart=row.quantity,
        )

    ceiling = min(MAX_QTY_PER_ITEM, product.stock)
    if row.quantity >= ceiling:
        reason = (
            f"You cannot add more than {MAX_QTY_PER_ITEM} units of one product."
            if row.quantity >= MAX_QTY_PER_ITEM
            else "No more units of this product are in stock."
        )
        return reply(False, reason, "warning", in_cart=row.quantity)

    # Recompute against the row that actually exists, so two quick clicks can
    # never push the line past the ceiling.
    row.quantity = min(row.quantity + wanted, ceiling)
    row.save(update_fields=["quantity"])
    return reply(
        True,
        f"Updated {product.supplementName} to {row.quantity} in your cart.",
        in_cart=row.quantity,
    )


@login_required(login_url="login")
def buynow(request, id):
    """Skip the cart and take one product straight to checkout."""
    product = get_object_or_404(Supplement, id=id, is_deleted=False)

    if product.stock <= 0:
        messages.warning(request, f"{product.supplementName} is out of stock.")
        return redirect("cards", id=product.id)

    set_buy_now(request, product, requested_qty(request, product))

    # An address already on file means there is nothing to fill in: go straight
    # to the pay screen, exactly like the cart flow does.
    if processedtocheck.objects.filter(user=request.user).exists():
        return redirect("makepayment")
    return redirect("checkout")


@login_required(login_url="login")
def viewcart(request):
    # Opening the cart is an explicit choice to buy the basket, so any pending
    # direct purchase is abandoned here rather than hijacking the next checkout.
    clear_buy_now(request)
    items = list(cart_for(request.user))
    context = {"products": items}
    context.update(cart_totals(items))
    return render(request, "viewcart.html", context)


@login_required(login_url="login")
def updateqty(request, qv, id):
    row = get_object_or_404(
        cart.objects.select_related("productid"), id=id, userid=request.user
    )

    if str(qv) == "1":
        if row.quantity >= MAX_QTY_PER_ITEM:
            messages.warning(
                request,
                f"You cannot add more than {MAX_QTY_PER_ITEM} units of one product.",
            )
        elif row.quantity >= row.productid.stock:
            messages.warning(request, "No more units of this product are in stock.")
        else:
            row.quantity += 1
            row.save(update_fields=["quantity"])
    else:
        if row.quantity > 1:
            row.quantity -= 1
            row.save(update_fields=["quantity"])
        else:
            row.delete()
            messages.info(request, "Item removed from your cart.")

    return redirect("viewcart")


@login_required(login_url="login")
def remove(request, id):
    deleted, _ = cart.objects.filter(id=id, userid=request.user).delete()
    if deleted:
        messages.info(request, "Item removed from your cart.")
    return redirect("viewcart")


# ---------------------------------------------------------------------------
# Wishlist
# ---------------------------------------------------------------------------
@login_required(login_url="login")
def wishlist(request):
    saved = (
        Wishlist.objects.filter(user=request.user)
        .select_related("product", "product__supplementCategory")
        .filter(product__is_deleted=False)
    )
    return render(request, "wishlist.html", {"saved": saved})


@login_required(login_url="login")
def wishlist_toggle(request, id):
    """Save or unsave a product.

    A POST toggles. A GET only ever *adds*, because the one way a GET reaches
    this view is the redirect that `login_required` performs after an anonymous
    visitor signs in - and an idempotent add is also safe for link prefetching.
    """
    product = get_object_or_404(Supplement, id=id, is_deleted=False)

    row = Wishlist.objects.filter(user=request.user, product=product).first()
    if row and request.method == "POST":
        row.delete()
        saved, message = False, f"{product.supplementName} removed from your wishlist."
    elif row:
        saved, message = True, f"{product.supplementName} is already in your wishlist."
    else:
        Wishlist.objects.create(user=request.user, product=product)
        saved, message = True, f"{product.supplementName} saved to your wishlist."

    if wants_json(request):
        payload = {"ok": True, "saved": saved, "message": message, "level": "success"}
        payload.update(cart_badge(request.user))
        return JsonResponse(payload)

    messages.success(request, message)
    return redirect(safe_redirect_target(request))


@login_required(login_url="login")
def wishlist_move_to_cart(request, id):
    """Move a saved product into the cart in one click."""
    product = get_object_or_404(Supplement, id=id, is_deleted=False)

    if product.stock <= 0:
        messages.warning(request, f"{product.supplementName} is out of stock.")
        return redirect("wishlist")

    row, created = cart.objects.get_or_create(
        productid=product, userid=request.user, defaults={"quantity": 1}
    )
    ceiling = min(MAX_QTY_PER_ITEM, product.stock)
    if not created and row.quantity < ceiling:
        row.quantity += 1
        row.save(update_fields=["quantity"])

    Wishlist.objects.filter(user=request.user, product=product).delete()
    messages.success(request, f"{product.supplementName} moved to your cart.")
    return redirect("wishlist")


# ---------------------------------------------------------------------------
# Checkout + orders
# ---------------------------------------------------------------------------
@login_required(login_url="login")
def Processedtocheck(request):
    items, is_direct = checkout_lines(request)
    if not items:
        messages.info(request, "Your cart is empty.")
        return redirect("viewcart")

    totals = cart_totals(items)
    existing = processedtocheck.objects.filter(user=request.user).first()

    if existing:
        return redirect("makepayment")

    if request.method == "POST":
        form = processedtocheckform(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.user = request.user
            record.save()
            return redirect("makepayment")
        messages.error(request, "Please correct the highlighted fields.")
    else:
        profile = UserProfile.objects.filter(user=request.user).first()
        form = processedtocheckform(
            initial={
                "full_name": (profile.full_name if profile else "")
                or request.user.get_full_name(),
                "email": (profile.email if profile else "") or request.user.email,
                "phone_number": profile.phone if profile else "",
                "country": "India",
            }
        )

    context = {
        "form": form,
        "form_filled": False,
        "is_direct": is_direct,
        "products": items,
    }
    context.update(totals)
    return render(request, "checkout.html", context)


@login_required(login_url="login")
def edit_address(request, id):
    record = get_object_or_404(processedtocheck, id=id, user=request.user)
    if request.method == "POST":
        form = processedtocheckform(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, "Address updated.")
            return redirect("makepayment")
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = processedtocheckform(instance=record)

    return render(request, "edit_address.html", {"form": form, "address": record})


@login_required(login_url="login")
def makepayment(request):
    items, is_direct = checkout_lines(request)
    if not items:
        messages.info(request, "Your cart is empty.")
        return redirect("viewcart")

    totals = cart_totals(items)
    address = processedtocheck.objects.filter(user=request.user).first()
    if not address:
        return redirect("checkout")

    item_name = (
        f"{items[0].productid.supplementName} x{items[0].quantity}"
        if is_direct
        else "Fitness Empire order"
    )

    context = {
        "products": items,
        "custformdetail": [address],
        "address": address,
        "is_direct": is_direct,
        "amount_usd": to_usd(totals["grand_total"]),
        "paypalpayment": paypal_form(
            request,
            amount=totals["grand_total"],
            item_name=item_name,
            return_url_name="paymentsuccess",
        ),
    }
    context.update(totals)
    return render(request, "processedtocheckout.html", context)


@login_required(login_url="login")
def paymentsuccess(request):
    items, is_direct = checkout_lines(request)

    order_list = []
    grand_total = Decimal("0")

    with transaction.atomic():
        for row in items:
            # Each order row stores its own line total. It previously stored a
            # running cumulative total, so the second item in a cart was
            # recorded at the price of every item before it combined.
            line_total = row.productid.supplementPrice * row.quantity
            grand_total += line_total

            order = Orders.objects.create(
                customer=row.userid or request.user,
                supplement=row.productid,
                quantity=row.quantity,
                total_price=line_total,
            )
            order_list.append(order)

            Supplement.objects.filter(id=row.productid_id, stock__gte=row.quantity).update(
                stock=F("stock") - row.quantity
            )
            row.delete()

    # A direct purchase never entered the cart, so clearing the session is what
    # "emptying the basket" means for it.
    clear_buy_now(request)

    if order_list:
        messages.success(request, "Payment received. Your order is confirmed.")

    return render(
        request,
        "paymentsuccess.html",
        {"orders": order_list, "grand_total": grand_total},
    )


def paymentfailed(request):
    # Cancelling at PayPal ends the direct purchase; without this the pending
    # item would still be in the session and would replace the cart next time
    # the shopper reached checkout.
    clear_buy_now(request)
    return render(request, "paymentfailed.html")


@login_required(login_url="login")
def orders(request):
    return render(
        request,
        "orders.html",
        {
            "orders": Orders.objects.filter(customer=request.user)
            .select_related("supplement")
            .order_by("-order_date")
        },
    )


@login_required(login_url="login")
def myorders(request):
    return render(
        request,
        "myorder.html",
        {
            "orders": Orders.objects.filter(customer=request.user)
            .select_related("supplement")
            .order_by("-order_date")
        },
    )


@login_required(login_url="login")
def remove_order(request, order_id):
    order = get_object_or_404(Orders, id=order_id, customer=request.user)

    # Status is stored as the uppercase choice value ("DELIVERED"), so the old
    # comparison against "Delivered" never matched and delivered orders could
    # be deleted.
    if order.status.upper() == "DELIVERED":
        messages.warning(request, "You cannot remove a delivered order.")
    else:
        order.delete()
        messages.success(request, "Order removed successfully.")

    return redirect("orders")


@login_required(login_url="login")
def cancel_order(request, order_id):
    order = get_object_or_404(Orders, id=order_id, customer=request.user)

    if order.status.upper() == "CANCELLED":
        messages.warning(request, "Order is already cancelled.")
    elif order.status.upper() in {"SHIPPED", "DELIVERED"}:
        messages.warning(
            request, "This order has already shipped and can no longer be cancelled."
        )
    else:
        order.status = "CANCELLED"
        order.save(update_fields=["status"])
        Supplement.objects.filter(id=order.supplement_id).update(
            stock=F("stock") + order.quantity
        )
        messages.success(request, "Your order has been cancelled successfully.")

    return redirect("orders")


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
def register(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        registerForm = RegisterForm(request.POST)
        if registerForm.is_valid():
            registerForm.save()
            messages.success(request, "Successfully registered, you can now log in.")
            return redirect("login")
        messages.error(request, "Please correct the errors below and try again.")
    else:
        registerForm = RegisterForm()

    return render(request, "register.html", {"registerForm": registerForm})


def loginuser(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        uname = (request.POST.get("username") or "").strip()
        upass = request.POST.get("password") or ""
        user = authenticate(request, username=uname, password=upass)

        if user is not None:
            auth_login(request, user)
            request.session["username"] = uname
            next_url = request.GET.get("next") or request.POST.get("next")
            response = redirect(next_url or "home")
            response.set_cookie("username", uname, samesite="Lax")
            response.set_cookie(
                "Time", datetime.datetime.now().isoformat(), samesite="Lax"
            )
            messages.success(request, f"Welcome back, {user.username}!")
            return response

        messages.error(request, "Invalid username or password. Please try again.")
        return redirect("login")

    return render(request, "login.html", {"userform": userAuthentication()})


def signout(request):
    logout(request)
    messages.info(request, "You have been signed out.")
    return redirect("home")


@login_required(login_url="login")
def my_profile(request):
    profile = UserProfile.objects.filter(user=request.user).first()
    return render(request, "my_profile.html", {"user_profile": profile})


@login_required(login_url="login")
def edit_profile(request, user_id):
    if request.user.id != user_id and not request.user.is_superuser:
        messages.error(request, "You can only edit your own profile.")
        return redirect("my_profile")

    profile, _ = UserProfile.objects.get_or_create(user_id=user_id)

    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("my_profile")
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = UserProfileForm(instance=profile)

    return render(request, "profile_edit.html", {"form": form, "user_profile": profile})


@login_required(login_url="login")
def my_addresses(request):
    return render(
        request,
        "my_addresses.html",
        {
            "addresses": processedtocheck.objects.filter(user=request.user),
            "user_profile": UserProfile.objects.filter(user=request.user).first(),
        },
    )


# ---------------------------------------------------------------------------
# Password reset by OTP
# ---------------------------------------------------------------------------
OTP_TTL_SECONDS = 10 * 60


def forgetpassword(request):
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        user = User.objects.filter(email__iexact=email).first()

        if not user:
            messages.error(request, "Email not found. Please enter a registered email.")
            return render(request, "forgetpassword.html")

        otp = random.randint(100000, 999999)
        request.session["reset_otp"] = otp
        request.session["reset_email"] = user.email
        request.session["reset_otp_at"] = timezone.now().isoformat()
        request.session["otp_purpose"] = "login"

        subject = "Password Reset Request - Your OTP Inside"
        message = (
            f"Hello {user.username},\n\n"
            "We received a request to reset your password. Use the one-time "
            f"password below to continue:\n\n"
            f"    OTP: {otp}\n\n"
            "This code is valid for 10 minutes. If you did not request it you "
            "can safely ignore this email.\n\n"
            "Never share this code with anyone.\n\n"
            "Fitness Empire Support"
        )

        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
        except Exception:
            # A mail-server outage should not produce a 500 page.
            messages.error(
                request,
                "We could not send the email right now. Please try again shortly.",
            )
            return render(request, "forgetpassword.html")

        messages.success(request, f"We sent a one-time code to {user.email}.")
        return redirect("verifyotp")

    return render(request, "forgetpassword.html")


def verifyotp(request):
    if request.method == "POST":
        entered = (request.POST.get("otp") or "").strip()
        stored = request.session.get("reset_otp")
        issued_at = request.session.get("reset_otp_at")
        purpose = request.session.get("otp_purpose", "")

        expired = True
        if issued_at:
            try:
                age = (
                    timezone.now() - datetime.datetime.fromisoformat(issued_at)
                ).total_seconds()
                expired = age > OTP_TTL_SECONDS
            except ValueError:
                expired = True

        if not stored:
            messages.error(request, "No code was requested. Please start again.")
            return redirect("forgetpassword")

        if expired:
            messages.error(request, "That code has expired. Please request a new one.")
            return redirect("forgetpassword")

        if entered == str(stored):
            request.session["otp_verified"] = True
            if purpose == "payment":
                return redirect("checkout")
            return redirect("resetpassword")

        messages.error(request, "Invalid OTP. Please check the code and try again.")

    return render(request, "verifyotp.html")


def resetpassword(request):
    if not request.session.get("otp_verified"):
        messages.error(request, "Please verify your one-time code first.")
        return redirect("forgetpassword")

    if request.method == "POST":
        new_password = request.POST.get("new_password") or ""
        confirm_password = request.POST.get("confirm_password") or ""
        email = request.session.get("reset_email")

        if new_password != confirm_password:
            messages.error(request, "Passwords do not match. Try again.")
            return render(request, "resetpassword.html")

        if len(new_password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(request, "resetpassword.html")

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            messages.error(request, "Something went wrong. Please start again.")
            return redirect("forgetpassword")

        user.set_password(new_password)
        user.save()

        for key in ("reset_otp", "reset_email", "reset_otp_at", "otp_verified"):
            request.session.pop(key, None)

        messages.success(request, "Password reset successful. You can now log in.")
        return redirect("login")

    return render(request, "resetpassword.html")


# ---------------------------------------------------------------------------
# Staff product management
# ---------------------------------------------------------------------------
@login_required(login_url="login")
def crud(request):
    if not request.user.is_superuser:
        messages.error(request, "You do not have permission to manage products.")
        return redirect("home")

    if request.method == "POST":
        Product.objects.create(
            productId=request.POST.get("product-id"),
            productName=request.POST.get("product-name"),
            productPrice=request.POST.get("product-price"),
            productDescription=request.POST.get("product-description"),
            productImage=request.FILES.get("product-image"),
        )
        messages.success(request, "Product added.")
        return redirect("showdetails")

    return render(request, "crud_operation.html")


@login_required(login_url="login")
def showdetails(request):
    if not request.user.is_superuser:
        messages.error(request, "You do not have permission to manage products.")
        return redirect("home")

    return render(request, "dashboard.html", {"products": Product.objects.all()})


@login_required(login_url="login")
def editproduct(request, id):
    if not request.user.is_superuser:
        messages.error(request, "You do not have permission to manage products.")
        return redirect("home")

    product = get_object_or_404(Product, id=id)

    if request.method == "POST":
        product.productId = request.POST.get("product-id")
        product.productName = request.POST.get("product-name")
        product.productDescription = request.POST.get("product-description")
        product.productPrice = request.POST.get("product-price")
        if request.FILES.get("product-image"):
            product.productImage = request.FILES.get("product-image")
        product.save()
        messages.success(request, "Product updated.")
        return redirect("showdetails")

    return render(request, "edit.html", {"product": product})


@login_required(login_url="login")
def deleteproduct(request, id):
    if not request.user.is_superuser:
        messages.error(request, "You do not have permission to manage products.")
        return redirect("home")

    get_object_or_404(Product, id=id).delete()
    messages.success(request, "Product deleted.")
    return redirect("showdetails")


@login_required(login_url="login")
def addproduct(request):
    if not request.user.is_superuser:
        messages.error(request, "You do not have permission to manage products.")
        return redirect("home")

    if request.method == "POST":
        form = SupplementForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Supplement added.")
            return redirect("protien")
    else:
        form = SupplementForm()

    return render(request, "crud_operation.html", {"form": form})


@login_required(login_url="login")
def deleteproductcrud(request, id):
    if not request.user.is_superuser:
        messages.error(request, "You do not have permission to manage products.")
        return redirect("home")

    product = get_object_or_404(Supplement, id=id, is_deleted=False)
    product.is_deleted = True
    product.delete_details = timezone.now()
    product.save(update_fields=["is_deleted", "delete_details"])
    messages.success(request, "Product removed from the store.")
    return redirect("protien")


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------
class crudapi(APIView):
    def get(self, request):
        customer_id = request.query_params.get("id") or request.data.get("id")
        if customer_id:
            customer = Customer.objects.filter(customerId=customer_id).first()
            if not customer:
                return Response(
                    {"msg": "Data not found"}, status=status.HTTP_404_NOT_FOUND
                )
            return Response(customerSerializer(customer).data, status=status.HTTP_200_OK)

        customers = Customer.objects.select_related("membership").all()
        return Response(
            customerSerializer(customers, many=True).data, status=status.HTTP_200_OK
        )

    def post(self, request):
        serializer = customerSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"msg": "Data inserted successfully", "data": serializer.data},
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request):
        customer_id = request.data.get("id")
        if not customer_id:
            return Response(
                {"msg": "Please provide a valid id"}, status=status.HTTP_400_BAD_REQUEST
            )

        customer = Customer.objects.filter(customerId=customer_id).first()
        if not customer:
            return Response({"msg": "Data not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = customerSerializer(customer, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"msg": "Data updated successfully"}, status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        customer_id = request.data.get("id")
        if not customer_id:
            return Response(
                {"msg": "Please provide a valid id"}, status=status.HTTP_400_BAD_REQUEST
            )

        customer = Customer.objects.filter(customerId=customer_id).first()
        if not customer:
            return Response({"msg": "Data not found"}, status=status.HTTP_404_NOT_FOUND)

        customer.delete()
        return Response({"msg": "Data deleted successfully"}, status=status.HTTP_200_OK)
