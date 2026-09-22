"""Tests for the shop: cart state, direct purchase and the wishlist."""

import sys
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import (
    Membership,
    Membershipmonth,
    Orders,
    Supplement,
    SupplementCategory,
    Wishlist,
    cart,
    membershipprocessedtocheck,
    processedtocheck,
)
from .views import BUY_NOW_KEY, to_usd

# ---------------------------------------------------------------------------
# Django 5.1 on Python 3.14
#
# `BaseContext.__copy__` is written as `copy(super())`, which on 3.14 returns a
# bare `super` object instead of a context, so every test-client request that
# renders a template dies with
# "'super' object has no attribute 'dicts'".
#
# Only `django.test.client` ever copies a context, so this affects the test
# suite and not the running site. The project pins Django 5.1.6, whose
# supported Python range stops at 3.13; drop this shim once Django is upgraded.
# ---------------------------------------------------------------------------
if sys.version_info >= (3, 14):  # pragma: no cover - environment dependent
    from django.template.context import BaseContext

    def _copy_base_context(self):
        duplicate = self.__class__.__new__(self.__class__)
        duplicate.__dict__.update(self.__dict__)
        duplicate.dicts = self.dicts[:]
        return duplicate

    BaseContext.__copy__ = _copy_base_context


class ShopTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("lifter", "lifter@gmail.com", "pw12345!")
        self.category = SupplementCategory.objects.create(
            categoryName="Vitamins", categoryDescription="Micronutrients"
        )
        self.product = Supplement.objects.create(
            supplementName="Omega 3",
            supplementDescription="Triple strength EPA and DHA.",
            supplementPrice=Decimal("1200.00"),
            supplementCategory=self.category,
            stock=48,
        )
        self.client.force_login(self.user)

    def address(self):
        return processedtocheck.objects.create(
            user=self.user,
            full_name="Test Lifter",
            email="lifter@gmail.com",
            phone_number="9990001112",
            address="1 Iron Street",
            city="Pune",
            pin_code="411001",
            country="India",
        )


class ProductPageTests(ShopTestCase):
    def test_action_slot_shows_add_to_cart_when_basket_is_empty(self):
        res = self.client.get(reverse("cards", args=[self.product.id]))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["in_cart_qty"], 0)
        self.assertContains(res, "Add to Cart")
        self.assertContains(res, "Buy Now")

    def test_action_slot_flips_to_view_cart_once_the_product_is_in_the_basket(self):
        cart.objects.create(userid=self.user, productid=self.product, quantity=2)
        res = self.client.get(reverse("cards", args=[self.product.id]))
        self.assertEqual(res.context["in_cart_qty"], 2)
        self.assertContains(res, "View Cart")

    def test_quantity_cap_never_exceeds_the_stock_on_hand(self):
        self.product.stock = 3
        self.product.save(update_fields=["stock"])
        res = self.client.get(reverse("cards", args=[self.product.id]))
        self.assertEqual(res.context["max_qty"], 3)


class AddToCartTests(ShopTestCase):
    def test_post_adds_the_requested_quantity(self):
        self.client.post(
            reverse("addtocart", args=[self.product.id]), {"quantity": 3}
        )
        row = cart.objects.get(userid=self.user, productid=self.product)
        self.assertEqual(row.quantity, 3)

    def test_ajax_call_answers_json_with_the_new_counts(self):
        res = self.client.post(
            reverse("addtocart", args=[self.product.id]),
            {"quantity": 2},
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        payload = res.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["in_cart"], 2)
        self.assertEqual(payload["cart_count"], 2)

    def test_a_line_can_never_pass_the_per_item_cap(self):
        self.client.post(reverse("addtocart", args=[self.product.id]), {"quantity": 4})
        self.client.post(reverse("addtocart", args=[self.product.id]), {"quantity": 4})
        row = cart.objects.get(userid=self.user, productid=self.product)
        self.assertEqual(row.quantity, 5)

    def test_requested_quantity_is_clamped_to_the_stock(self):
        self.product.stock = 2
        self.product.save(update_fields=["stock"])
        self.client.post(reverse("addtocart", args=[self.product.id]), {"quantity": 5})
        row = cart.objects.get(userid=self.user, productid=self.product)
        self.assertEqual(row.quantity, 2)

    def test_an_out_of_stock_product_is_refused(self):
        self.product.stock = 0
        self.product.save(update_fields=["stock"])
        self.client.post(reverse("addtocart", args=[self.product.id]), {"quantity": 1})
        self.assertFalse(cart.objects.filter(productid=self.product).exists())


class BuyNowTests(ShopTestCase):
    def test_buy_now_stages_the_product_without_touching_the_cart(self):
        res = self.client.post(
            reverse("buynow", args=[self.product.id]), {"quantity": 2}
        )
        self.assertRedirects(res, reverse("checkout"))
        self.assertEqual(
            self.client.session[BUY_NOW_KEY],
            {"product": self.product.id, "quantity": 2},
        )
        self.assertFalse(cart.objects.filter(userid=self.user).exists())

    def test_buy_now_skips_the_address_form_when_one_is_on_file(self):
        self.address()
        res = self.client.post(reverse("buynow", args=[self.product.id]))
        self.assertRedirects(res, reverse("makepayment"))

    def test_checkout_totals_cover_only_the_direct_item(self):
        other = Supplement.objects.create(
            supplementName="Whey",
            supplementDescription="Protein",
            supplementPrice=Decimal("4000.00"),
            supplementCategory=self.category,
            stock=10,
        )
        cart.objects.create(userid=self.user, productid=other, quantity=1)

        self.client.post(reverse("buynow", args=[self.product.id]), {"quantity": 2})
        res = self.client.get(reverse("checkout"))

        self.assertTrue(res.context["is_direct"])
        self.assertEqual(res.context["total"], Decimal("2400.00"))
        self.assertEqual(res.context["totalCount"], 2)

    def test_paying_creates_one_order_and_leaves_the_cart_alone(self):
        other = Supplement.objects.create(
            supplementName="Whey",
            supplementDescription="Protein",
            supplementPrice=Decimal("4000.00"),
            supplementCategory=self.category,
            stock=10,
        )
        cart.objects.create(userid=self.user, productid=other, quantity=1)
        self.address()

        self.client.post(reverse("buynow", args=[self.product.id]), {"quantity": 2})
        self.client.get(reverse("makepayment"))
        self.client.get(reverse("paymentsuccess"))

        orders = Orders.objects.filter(customer=self.user)
        self.assertEqual(orders.count(), 1)
        self.assertEqual(orders.first().supplement, self.product)
        self.assertEqual(orders.first().total_price, Decimal("2400.00"))

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 46)

        # The basket is untouched and the staged purchase is gone.
        self.assertEqual(cart.objects.filter(userid=self.user).count(), 1)
        self.assertNotIn(BUY_NOW_KEY, self.client.session)

    def test_opening_the_cart_abandons_a_staged_direct_purchase(self):
        self.client.post(reverse("buynow", args=[self.product.id]))
        self.client.get(reverse("viewcart"))
        self.assertNotIn(BUY_NOW_KEY, self.client.session)

    def test_cancelling_at_paypal_abandons_the_staged_purchase(self):
        self.client.post(reverse("buynow", args=[self.product.id]))
        self.client.get(reverse("paymentfailed"))
        self.assertNotIn(BUY_NOW_KEY, self.client.session)

    def test_a_deleted_product_cannot_linger_in_the_session(self):
        self.client.post(reverse("buynow", args=[self.product.id]))
        self.product.is_deleted = True
        self.product.save(update_fields=["is_deleted"])

        res = self.client.get(reverse("checkout"))
        self.assertRedirects(res, reverse("viewcart"))


class WishlistTests(ShopTestCase):
    def test_posting_the_toggle_saves_then_unsaves(self):
        url = reverse("wishlist_toggle", args=[self.product.id])

        self.client.post(url)
        self.assertTrue(Wishlist.objects.filter(user=self.user).exists())

        self.client.post(url)
        self.assertFalse(Wishlist.objects.filter(user=self.user).exists())

    def test_ajax_toggle_reports_the_saved_state_and_the_badge(self):
        res = self.client.post(
            reverse("wishlist_toggle", args=[self.product.id]),
            headers={"x-requested-with": "XMLHttpRequest"},
        )
        payload = res.json()
        self.assertTrue(payload["saved"])
        self.assertEqual(payload["wishlist_count"], 1)

    def test_a_get_only_ever_adds_so_the_post_login_redirect_is_safe(self):
        url = reverse("wishlist_toggle", args=[self.product.id])
        self.client.get(url)
        self.client.get(url)
        self.assertEqual(Wishlist.objects.filter(user=self.user).count(), 1)

    def test_an_anonymous_visitor_is_sent_to_sign_in_first(self):
        self.client.logout()
        url = reverse("wishlist_toggle", args=[self.product.id])
        res = self.client.get(url)
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse("login"), res.url)

    def test_an_off_site_next_value_cannot_redirect_the_shopper_away(self):
        res = self.client.post(
            reverse("wishlist_toggle", args=[self.product.id]),
            {"next": "https://evil.example.com/phish"},
        )
        self.assertEqual(res.status_code, 302)
        self.assertNotIn("evil.example.com", res.url)

    def test_an_on_site_next_value_is_honoured(self):
        target = reverse("cards", args=[self.product.id])
        res = self.client.post(
            reverse("wishlist_toggle", args=[self.product.id]), {"next": target}
        )
        self.assertRedirects(res, target)

    def test_moving_to_the_cart_empties_the_wishlist_row(self):
        Wishlist.objects.create(user=self.user, product=self.product)
        self.client.post(reverse("wishlist_move_to_cart", args=[self.product.id]))

        self.assertFalse(Wishlist.objects.filter(user=self.user).exists())
        self.assertTrue(cart.objects.filter(userid=self.user).exists())

    def test_the_page_lists_saved_products(self):
        Wishlist.objects.create(user=self.user, product=self.product)
        res = self.client.get(reverse("wishlist"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Omega 3")

    def test_saved_ids_reach_every_template(self):
        Wishlist.objects.create(user=self.user, product=self.product)
        res = self.client.get(reverse("protien"))
        self.assertEqual(res.context["wishlist_ids"], {self.product.id})
        self.assertEqual(res.context["wishlist_count"], 1)


class PaypalAmountTests(ShopTestCase):
    def test_the_rupee_total_is_converted_before_it_reaches_paypal(self):
        # 6,450 rupees must not be handed to PayPal as 6,450 US dollars.
        self.assertEqual(to_usd(Decimal("6450")), Decimal("77.40"))

    def test_a_tiny_total_still_clears_the_one_cent_floor(self):
        self.assertEqual(to_usd(Decimal("0.10")), Decimal("0.01"))

    def test_the_pay_screen_renders_the_branded_button(self):
        self.address()
        cart.objects.create(userid=self.user, productid=self.product, quantity=1)

        res = self.client.get(reverse("makepayment"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "paypal-btn")
        self.assertContains(res, "www.sandbox.paypal.com")
        # The hidden fields django-paypal builds must survive the restyling.
        self.assertContains(res, 'name="business"')
        self.assertContains(res, 'name="amount"')
        self.assertNotContains(res, 'type="image"')


class TemplateRenderTests(ShopTestCase):
    """Every page touched by this change must still render."""

    def member_record(self, **plan):
        return membershipprocessedtocheck.objects.create(
            user=self.user,
            full_name="Test Lifter",
            email="lifter@gmail.com",
            phone_number="9990001112",
            city="Pune",
            pin_code="411001",
            **plan,
        )

    def test_the_cart_page_renders_with_the_new_navbar(self):
        cart.objects.create(userid=self.user, productid=self.product, quantity=1)
        res = self.client.get(reverse("viewcart"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Order Summary")
        self.assertContains(res, "data-wishlist-count")

    def test_the_empty_wishlist_page_renders(self):
        res = self.client.get(reverse("wishlist"))
        self.assertContains(res, "Nothing saved yet")

    def test_the_yearly_membership_pay_screen_renders_the_branded_button(self):
        plan = Membership.objects.create(name="Annual", price=Decimal("12000.00"))
        self.member_record(membership_yearly=plan)

        res = self.client.get(reverse("membership_processedtocheckout", args=[plan.id]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "paypal-btn")
        self.assertNotContains(res, 'type="image"')

    def test_the_monthly_membership_pay_screen_renders_the_branded_button(self):
        plan = Membershipmonth.objects.create(name="Monthly", price=Decimal("1500.00"))
        self.member_record(membership_monthly=plan)

        res = self.client.get(
            reverse("membership_processedtocheckout_monthly", args=[plan.id])
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "paypal-btn")
        self.assertNotContains(res, 'type="image"')

    def test_an_anonymous_visitor_sees_a_sign_in_prompt_instead_of_a_heart_form(self):
        self.client.logout()
        res = self.client.get(reverse("cards", args=[self.product.id]))
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, "data-wish-form")
        self.assertContains(res, "Sign in to save")


class PaypalRoutingTests(ShopTestCase):
    def test_the_ipn_endpoint_no_longer_collides_with_the_homepage(self):
        ipn = reverse("paypal-ipn")
        self.assertNotEqual(ipn, reverse("home"))
        self.assertEqual(ipn, "/paypal/")

    def test_the_button_points_its_callback_at_the_ipn_endpoint(self):
        self.address()
        cart.objects.create(userid=self.user, productid=self.product, quantity=1)

        res = self.client.get(reverse("makepayment"))
        self.assertContains(res, 'value="http://testserver/paypal/"')
