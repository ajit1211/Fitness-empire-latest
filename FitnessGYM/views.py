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
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
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
    aboutus,
    cart,
    membershipprocessedtocheck,
    processedtocheck,
)
from .serializers import customerSerializer

GST_RATE = Decimal("0.18")


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


def paypal_form(request, *, amount, item_name, return_url_name):
    """Build the PayPal button form used by the checkout screens."""
    host = request.get_host()
    scheme = "https" if request.is_secure() else "http"
    return PayPalPaymentsForm(
        initial={
            "business": settings.PAYPAL_RECEIVER_EMAIL,
            "amount": amount,
            "item_name": item_name,
            "invoice": uuid.uuid4(),
            "currency_code": "USD",
            "notify_url": f"{scheme}://{host}{reverse('paypal-ipn')}",
            "return_url": f"{scheme}://{host}{reverse(return_url_name)}",
            "cancel_url": f"{scheme}://{host}{reverse('paymentfailed')}",
        }
    )


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
    return render(
        request,
        "membershipannual.html",
        {"memberships": Membership.objects.all()},
    )


def membershipmonthly(request):
    return render(
        request,
        "membershipmonthly.html",
        {"Membershipmonth": Membershipmonth.objects.all()},
    )


@login_required(login_url="login")
def membership_processed_view(request, id):
    """Collect member details for a yearly plan."""
    membership = get_object_or_404(Membership, id=id)
    total_price = membership.price + (membership.price * GST_RATE)

    existing = membershipprocessedtocheck.objects.filter(user=request.user).first()
    if existing:
        if existing.membership_monthly:
            messages.warning(
                request,
                "You already have a monthly membership and cannot buy a yearly one.",
            )
            return redirect("profile")
        if existing.membership_yearly:
            messages.warning(
                request, "You already have a yearly membership and cannot buy another one."
            )
            return redirect("profile")

    if request.method == "POST":
        form = membershipprocessedtocheckform(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.user = request.user
            record.membership_yearly = membership
            record.membership_monthly = None
            record.save()
            messages.success(request, "Proceed to payment to complete your membership.")
            return redirect("membershipprocessedtocheckouts", id=id)
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = membershipprocessedtocheckform(initial=_member_initial(request.user))

    return render(
        request,
        "membership_form.html",
        {"form": form, "membership": membership, "total_price": total_price},
    )


@login_required(login_url="login")
def membership_processed_view_month(request, id):
    """Collect member details for a monthly plan."""
    membership = get_object_or_404(Membershipmonth, id=id)
    total_price = membership.price + (membership.price * GST_RATE)

    existing = membershipprocessedtocheck.objects.filter(user=request.user).first()
    if existing:
        if existing.membership_yearly:
            messages.warning(
                request,
                "You already have a yearly membership and cannot buy a monthly one.",
            )
            return redirect("profile")
        if existing.membership_monthly:
            messages.warning(
                request,
                "You already have a monthly membership and cannot buy another one.",
            )
            return redirect("profile")

    if request.method == "POST":
        form = membershipprocessedtocheckform(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.user = request.user
            record.membership_monthly = membership
            record.membership_yearly = None
            record.save()
            messages.success(request, "Proceed to payment to complete your membership.")
            return redirect("membershipprocessedtocheckout", id=id)
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = membershipprocessedtocheckform(initial=_member_initial(request.user))

    return render(
        request,
        "membership_form_month.html",
        {"form": form, "membership": membership, "total_price": total_price},
    )


def _member_initial(user):
    """Pre-fill the membership form from the user's profile."""
    profile = UserProfile.objects.filter(user=user).first()
    return {
        "full_name": (profile.full_name if profile else "") or user.get_full_name(),
        "email": (profile.email if profile else "") or user.email,
        "phone_number": profile.phone if profile else "",
    }


@login_required(login_url="login")
def membership_processedtocheckout(request, id):
    """Payment screen for a yearly plan."""
    membership = get_object_or_404(Membership, id=id)
    record = membershipprocessedtocheck.objects.filter(
        user=request.user, membership_yearly=membership
    ).first()

    if not record:
        messages.warning(request, "No pending payment found.")
        return redirect("profile")

    total_price = membership.price + (membership.price * GST_RATE)

    return render(
        request,
        "membershipprocessedtocheckout.html",
        {
            "membership": membership,
            "record": record,
            "gst": membership.price * GST_RATE,
            "total_price": total_price,
            "paypalpayment": paypal_form(
                request,
                amount=total_price,
                item_name=membership.name,
                return_url_name="paymentmembership",
            ),
        },
    )


@login_required(login_url="login")
def membership_processedtocheckout_monthly(request, id):
    """Payment screen for a monthly plan."""
    membership = get_object_or_404(Membershipmonth, id=id)
    record = membershipprocessedtocheck.objects.filter(
        user=request.user, membership_monthly=membership
    ).first()

    if not record:
        messages.warning(request, "No pending payment found.")
        return redirect("profile")

    total_price = membership.price + (membership.price * GST_RATE)

    return render(
        request,
        "membershipprocessedtocheckoutmonthly.html",
        {
            "membership": membership,
            "record": record,
            "gst": membership.price * GST_RATE,
            "total_price": total_price,
            "paypalpayment": paypal_form(
                request,
                # Previously this charged the pre-GST price while the page
                # displayed the GST-inclusive total.
                amount=total_price,
                item_name=membership.name,
                return_url_name="paymentmembership",
            ),
        },
    )


@login_required(login_url="login")
def paymentmembership(request):
    record = membershipprocessedtocheck.objects.filter(
        user=request.user, payment_status=False
    ).first()

    if record:
        record.payment_status = True
        record.save()
        messages.success(request, "Payment successful! Your membership is now active.")
    else:
        messages.warning(request, "No pending membership found.")

    return render(request, "finalthankyou.html", {"membership": record})


@login_required(login_url="login")
def profile_view(request):
    membership = (
        membershipprocessedtocheck.objects.filter(user=request.user)
        .select_related("membership_yearly", "membership_monthly")
        .first()
    )
    pending_payment = bool(membership and not membership.payment_status)

    return render(
        request,
        "profile.html",
        {"membership": membership, "pending_payment": pending_payment},
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
    return render(request, "cards.html", {"product": product, "related": related})


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
@login_required(login_url="login")
def addtocart(request, id):
    product = get_object_or_404(Supplement, id=id, is_deleted=False)

    if product.stock <= 0:
        messages.warning(request, f"{product.supplementName} is out of stock.")
        return redirect("cards", id=product.id)

    row, created = cart.objects.get_or_create(
        productid=product, userid=request.user, defaults={"quantity": 1}
    )

    if created:
        messages.success(request, f"{product.supplementName} added to your cart.")
    elif row.quantity >= 5:
        messages.warning(request, "You cannot add more than 5 units of one product.")
    elif row.quantity >= product.stock:
        messages.warning(request, "No more units of this product are in stock.")
    else:
        row.quantity = F("quantity") + 1
        row.save(update_fields=["quantity"])
        messages.success(request, f"Added another {product.supplementName} to your cart.")

    return redirect("cards", id=product.id)


@login_required(login_url="login")
def viewcart(request):
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
        if row.quantity >= 5:
            messages.warning(request, "You cannot add more than 5 units of one product.")
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
# Checkout + orders
# ---------------------------------------------------------------------------
@login_required(login_url="login")
def Processedtocheck(request):
    items = list(cart_for(request.user))
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

    context = {"form": form, "form_filled": False}
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
    items = list(cart_for(request.user))
    if not items:
        messages.info(request, "Your cart is empty.")
        return redirect("viewcart")

    totals = cart_totals(items)
    address = processedtocheck.objects.filter(user=request.user).first()
    if not address:
        return redirect("checkout")

    context = {
        "products": items,
        "custformdetail": [address],
        "address": address,
        "paypalpayment": paypal_form(
            request,
            amount=totals["grand_total"],
            item_name="Fitness Empire order",
            return_url_name="paymentsuccess",
        ),
    }
    context.update(totals)
    return render(request, "processedtocheckout.html", context)


@login_required(login_url="login")
def paymentsuccess(request):
    items = list(cart_for(request.user))

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
                customer=row.userid,
                supplement=row.productid,
                quantity=row.quantity,
                total_price=line_total,
            )
            order_list.append(order)

            Supplement.objects.filter(id=row.productid_id, stock__gte=row.quantity).update(
                stock=F("stock") - row.quantity
            )
            row.delete()

    if order_list:
        messages.success(request, "Payment received. Your order is confirmed.")

    return render(
        request,
        "paymentsuccess.html",
        {"orders": order_list, "grand_total": grand_total},
    )


def paymentfailed(request):
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
