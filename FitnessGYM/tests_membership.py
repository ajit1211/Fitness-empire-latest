"""Membership tier ladder: buying, upgrading and what each plan offers."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    ANNUAL_TERM_DAYS,
    MONTHLY_TERM_DAYS,
    Membership,
    Membershipmonth,
    membershipprocessedtocheck,
)
# Importing the module installs the Django-on-Python-3.14 template shim it
# defines. Importing a name out of it would fail on older Pythons, where the
# shim is not defined at all.
from . import tests  # noqa: F401
from .views import plan_offer


class MembershipTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("member", "member@gmail.com", "pw12345!")
        self.client.force_login(self.user)

        self.core = Membership.objects.create(
            name="CORE", price=Decimal("24900.00"), tier=1, choice="Annual"
        )
        self.premier = Membership.objects.create(
            name="PREMIER", price=Decimal("34900.00"), tier=2, choice="Annual"
        )
        self.executive = Membership.objects.create(
            name="EXECUTIVE", price=Decimal("44900.00"), tier=3, choice="Annual"
        )

        self.m_core = Membershipmonth.objects.create(
            name="CORE", price=Decimal("2400.00"), tier=1, choice="Monthly"
        )
        self.m_premier = Membershipmonth.objects.create(
            name="PREMIER", price=Decimal("3200.00"), tier=2, choice="Monthly"
        )

    def details(self):
        return {
            "full_name": "Test Member",
            "email": "member@gmail.com",
            "phone_number": "9990001112",
            "city": "Pune",
            "pin_code": "411001",
        }

    def hold(self, plan, cycle="annual", paid=True, days_left=None):
        """Put an active plan on the account."""
        term = ANNUAL_TERM_DAYS if cycle == "annual" else MONTHLY_TERM_DAYS
        if days_left is None:
            days_left = term
        record = membershipprocessedtocheck.objects.create(
            user=self.user,
            membership_yearly=plan if cycle == "annual" else None,
            membership_monthly=plan if cycle == "monthly" else None,
            payment_status=paid,
            plan_expiry=timezone.now() + timedelta(days=days_left),
            **self.details(),
        )
        return record


class PlanOfferTests(MembershipTestCase):
    def test_every_tier_is_for_sale_when_nothing_is_held(self):
        for plan in (self.core, self.premier, self.executive):
            offer = plan_offer(None, plan, "annual")
            self.assertEqual(offer["state"], "buy")
            self.assertTrue(offer["allowed"])

    def test_the_held_tier_is_marked_as_current(self):
        record = self.hold(self.core)
        offer = plan_offer(record, self.core, "annual")
        self.assertEqual(offer["state"], "current")
        self.assertFalse(offer["allowed"])

    def test_higher_tiers_are_offered_as_upgrades(self):
        record = self.hold(self.core)
        for plan in (self.premier, self.executive):
            offer = plan_offer(record, plan, "annual")
            self.assertEqual(offer["state"], "upgrade")
            self.assertTrue(offer["allowed"])
            self.assertIn("CORE", offer["cta"])

    def test_a_lower_tier_is_shown_as_already_covered(self):
        record = self.hold(self.premier)
        offer = plan_offer(record, self.core, "annual")
        self.assertEqual(offer["state"], "lower")
        self.assertFalse(offer["allowed"])

    def test_the_top_tier_offers_no_upgrade(self):
        record = self.hold(self.executive)
        for plan in (self.core, self.premier):
            self.assertEqual(plan_offer(record, plan, "annual")["state"], "lower")
        self.assertEqual(
            plan_offer(record, self.executive, "annual")["state"], "current"
        )

    def test_the_other_billing_cycle_stays_closed(self):
        record = self.hold(self.m_core, cycle="monthly")
        offer = plan_offer(record, self.premier, "annual")
        self.assertEqual(offer["state"], "locked")
        self.assertIn("monthly", offer["note"])

    def test_monthly_holders_get_the_same_ladder_within_monthly(self):
        record = self.hold(self.m_core, cycle="monthly")
        offer = plan_offer(record, self.m_premier, "monthly")
        self.assertEqual(offer["state"], "upgrade")
        self.assertTrue(offer["allowed"])

    def test_an_expired_plan_puts_every_tier_back_on_sale(self):
        record = self.hold(self.core, days_left=-1)
        for plan in (self.core, self.premier, self.executive):
            self.assertEqual(plan_offer(record, plan, "annual")["state"], "buy")

    def test_an_unpaid_first_purchase_locks_the_other_tiers(self):
        record = self.hold(self.core, paid=False)
        self.assertEqual(plan_offer(record, self.core, "annual")["state"], "finish")
        self.assertEqual(plan_offer(record, self.premier, "annual")["state"], "locked")


class UpgradePricingTests(MembershipTestCase):
    def test_a_full_term_credits_the_whole_plan_price(self):
        record = self.hold(self.core, days_left=ANNUAL_TERM_DAYS)
        # Core costs 24,900 and none of it is used, so Premier at 34,900
        # should cost the 10,000 difference.
        self.assertEqual(record.upgrade_cost(self.premier), Decimal("10000.00"))

    def test_credit_shrinks_as_the_term_runs_down(self):
        record = self.hold(self.core, days_left=100)
        # 100 of 365 days left on a 24,900 plan.
        expected_credit = (
            Decimal("24900") * Decimal(100) / Decimal(365)
        ).quantize(Decimal("0.01"))
        self.assertEqual(record.unused_credit(), expected_credit)
        self.assertEqual(
            record.upgrade_cost(self.premier),
            (Decimal("34900") - expected_credit).quantize(Decimal("0.01")),
        )

    def test_late_in_the_term_the_upgrade_costs_nearly_full_price(self):
        record = self.hold(self.core, days_left=ANNUAL_TERM_DAYS)
        full_term_cost = record.upgrade_cost(self.premier)

        record.plan_expiry = timezone.now() + timedelta(days=5)
        record.save(update_fields=["plan_expiry"])
        late_cost = record.upgrade_cost(self.premier)

        self.assertGreater(late_cost, full_term_cost)
        self.assertLess(late_cost, self.premier.price)

    def test_an_expired_plan_carries_no_credit(self):
        record = self.hold(self.core, days_left=-3)
        self.assertEqual(record.unused_credit(), Decimal("0.00"))

    def test_an_unpaid_plan_carries_no_credit(self):
        record = self.hold(self.core, paid=False)
        self.assertEqual(record.unused_credit(), Decimal("0.00"))

    def test_the_cost_never_goes_below_zero(self):
        # A huge credit against a cheap tier must not produce a refund.
        record = self.hold(self.executive)
        self.assertEqual(record.upgrade_cost(self.core), Decimal("0.00"))


class UpgradeFlowTests(MembershipTestCase):
    def test_choosing_a_higher_tier_parks_it_without_touching_the_live_plan(self):
        record = self.hold(self.core)

        res = self.client.post(
            reverse("membership_list", args=[self.premier.id]), self.details()
        )
        self.assertRedirects(
            res, reverse("membershipprocessedtocheckouts", args=[self.premier.id])
        )

        record.refresh_from_db()
        self.assertEqual(record.membership_yearly, self.core)     # unchanged
        self.assertEqual(record.pending_yearly, self.premier)     # parked
        self.assertTrue(record.payment_status)                    # still active
        self.assertEqual(record.pending_amount, Decimal("10000.00"))

    def test_paying_promotes_the_upgrade_and_keeps_the_expiry(self):
        record = self.hold(self.core, days_left=200)
        expiry = record.plan_expiry

        self.client.post(
            reverse("membership_list", args=[self.premier.id]), self.details()
        )
        self.client.get(reverse("paymentmembership"))

        record.refresh_from_db()
        self.assertEqual(record.membership_yearly, self.premier)
        self.assertIsNone(record.pending_yearly)
        self.assertIsNone(record.pending_amount)
        self.assertTrue(record.payment_status)
        self.assertEqual(record.plan_expiry, expiry)

    def test_the_payment_screen_bills_the_difference_not_the_sticker_price(self):
        self.hold(self.core)
        self.client.post(
            reverse("membership_list", args=[self.premier.id]), self.details()
        )

        res = self.client.get(
            reverse("membershipprocessedtocheckouts", args=[self.premier.id])
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.context["is_upgrade"])
        self.assertEqual(res.context["amount"], Decimal("10000.00"))
        # 10,000 plus 18% GST, not 34,900 plus GST.
        self.assertEqual(res.context["total_price"], Decimal("11800.00"))

    def test_abandoning_an_upgrade_leaves_the_member_on_their_plan(self):
        record = self.hold(self.core)
        self.client.post(
            reverse("membership_list", args=[self.premier.id]), self.details()
        )

        res = self.client.get(reverse("cancel_membership_upgrade"))
        self.assertRedirects(res, reverse("profile"))

        record.refresh_from_db()
        self.assertEqual(record.membership_yearly, self.core)
        self.assertFalse(record.has_pending_upgrade)
        self.assertTrue(record.payment_status)

    def test_a_downgrade_is_refused(self):
        self.hold(self.premier)
        res = self.client.post(
            reverse("membership_list", args=[self.core.id]), self.details()
        )
        self.assertRedirects(res, reverse("profile"))
        self.assertFalse(
            membershipprocessedtocheck.objects.get(user=self.user).has_pending_upgrade
        )

    def test_buying_the_plan_already_held_is_refused(self):
        self.hold(self.core)
        res = self.client.post(
            reverse("membership_list", args=[self.core.id]), self.details()
        )
        self.assertRedirects(res, reverse("profile"))

    def test_crossing_billing_cycles_is_refused(self):
        self.hold(self.m_core, cycle="monthly")
        res = self.client.post(
            reverse("membership_list", args=[self.premier.id]), self.details()
        )
        self.assertRedirects(res, reverse("profile"))

    def test_the_monthly_ladder_upgrades_the_same_way(self):
        record = self.hold(self.m_core, cycle="monthly")

        self.client.post(
            reverse("membership_lists", args=[self.m_premier.id]), self.details()
        )
        record.refresh_from_db()
        self.assertEqual(record.pending_monthly, self.m_premier)
        self.assertEqual(record.membership_monthly, self.m_core)

        self.client.get(reverse("paymentmembership"))
        record.refresh_from_db()
        self.assertEqual(record.membership_monthly, self.m_premier)
        self.assertIsNone(record.membership_yearly)

    def test_a_member_can_climb_the_whole_ladder(self):
        self.hold(self.core)

        self.client.post(
            reverse("membership_list", args=[self.premier.id]), self.details()
        )
        self.client.get(reverse("paymentmembership"))

        self.client.post(
            reverse("membership_list", args=[self.executive.id]), self.details()
        )
        self.client.get(reverse("paymentmembership"))

        record = membershipprocessedtocheck.objects.get(user=self.user)
        self.assertEqual(record.membership_yearly, self.executive)
        self.assertTrue(record.payment_status)

    def test_a_lapsed_member_buying_again_gets_a_fresh_term(self):
        record = self.hold(self.core, days_left=-5)

        self.client.post(
            reverse("membership_list", args=[self.core.id]), self.details()
        )
        record.refresh_from_db()
        self.assertFalse(record.payment_status)
        self.assertGreater(record.plan_expiry, timezone.now())

    def test_a_first_purchase_still_charges_the_full_price(self):
        self.client.post(
            reverse("membership_list", args=[self.core.id]), self.details()
        )
        res = self.client.get(
            reverse("membershipprocessedtocheckouts", args=[self.core.id])
        )
        self.assertFalse(res.context["is_upgrade"])
        self.assertEqual(res.context["amount"], self.core.price)


class PlanPageTests(MembershipTestCase):
    def test_the_annual_page_marks_the_held_plan_and_the_upgrades(self):
        self.hold(self.core)
        res = self.client.get(reverse("membershipannual"))
        self.assertEqual(res.status_code, 200)

        states = {o["plan"].name: o["state"] for o in res.context["offers"]}
        self.assertEqual(states["CORE"], "current")
        self.assertEqual(states["PREMIER"], "upgrade")
        self.assertEqual(states["EXECUTIVE"], "upgrade")
        self.assertContains(res, "Your plan")

    def test_the_monthly_page_marks_the_held_plan_and_the_upgrades(self):
        self.hold(self.m_core, cycle="monthly")
        res = self.client.get(reverse("membershipmonthly"))
        states = {o["plan"].name: o["state"] for o in res.context["offers"]}
        self.assertEqual(states["CORE"], "current")
        self.assertEqual(states["PREMIER"], "upgrade")

    def test_a_signed_out_visitor_sees_plain_buy_buttons(self):
        self.client.logout()
        res = self.client.get(reverse("membershipannual"))
        self.assertTrue(all(o["state"] == "buy" for o in res.context["offers"]))
        self.assertContains(res, "Buy Now")

    def test_the_membership_page_lists_the_tiers_above_the_current_one(self):
        self.hold(self.core)
        res = self.client.get(reverse("profile"))
        names = [o["plan"].name for o in res.context["upgrades"]]
        self.assertEqual(names, ["PREMIER", "EXECUTIVE"])
        self.assertContains(res, "Move up a tier")

    def test_the_top_tier_is_offered_no_upgrades(self):
        self.hold(self.executive)
        res = self.client.get(reverse("profile"))
        self.assertEqual(res.context["upgrades"], [])
        self.assertNotContains(res, "Move up a tier")

    def test_a_parked_upgrade_is_shown_with_a_way_out(self):
        self.hold(self.core)
        self.client.post(
            reverse("membership_list", args=[self.premier.id]), self.details()
        )

        res = self.client.get(reverse("profile"))
        self.assertContains(res, "Upgrade in progress")
        self.assertContains(res, "Complete Upgrade")
        self.assertContains(res, reverse("cancel_membership_upgrade"))


class CancelUnpaidMembershipTests(MembershipTestCase):
    """An unpaid selection can be walked away from."""

    def test_cancelling_removes_the_unpaid_plan(self):
        self.hold(self.core, paid=False)

        res = self.client.get(reverse("cancel_membership_purchase"))
        self.assertRedirects(res, reverse("profile"))
        self.assertFalse(
            membershipprocessedtocheck.objects.filter(user=self.user).exists()
        )

    def test_an_active_plan_cannot_be_cancelled_through_this_route(self):
        record = self.hold(self.core, paid=True)

        self.client.get(reverse("cancel_membership_purchase"))

        record.refresh_from_db()
        self.assertEqual(record.membership_yearly, self.core)
        self.assertTrue(record.payment_status)

    def test_a_parked_upgrade_is_not_swept_away_with_it(self):
        # The member is active with an upgrade pending, so there is no unpaid
        # first purchase to cancel and the account must be left alone.
        record = self.hold(self.core, paid=True)
        self.client.post(
            reverse("membership_list", args=[self.premier.id]), self.details()
        )

        self.client.get(reverse("cancel_membership_purchase"))

        record.refresh_from_db()
        self.assertEqual(record.membership_yearly, self.core)
        self.assertEqual(record.pending_yearly, self.premier)

    def test_cancelling_with_nothing_pending_is_harmless(self):
        res = self.client.get(reverse("cancel_membership_purchase"))
        self.assertRedirects(res, reverse("profile"))

    def test_a_cancelled_member_can_choose_a_different_plan(self):
        self.hold(self.core, paid=False)
        self.client.get(reverse("cancel_membership_purchase"))

        self.client.post(
            reverse("membership_list", args=[self.executive.id]), self.details()
        )

        record = membershipprocessedtocheck.objects.get(user=self.user)
        self.assertEqual(record.membership_yearly, self.executive)
        self.assertFalse(record.payment_status)

    def test_the_monthly_selection_can_be_cancelled_too(self):
        self.hold(self.m_core, cycle="monthly", paid=False)

        self.client.get(reverse("cancel_membership_purchase"))
        self.assertFalse(
            membershipprocessedtocheck.objects.filter(user=self.user).exists()
        )

    def test_the_membership_page_offers_the_cancel(self):
        self.hold(self.core, paid=False)

        res = self.client.get(reverse("profile"))
        self.assertContains(res, reverse("cancel_membership_purchase"))
        self.assertContains(res, "Complete Payment")
        self.assertContains(res, "Cancel this membership?")

    def test_the_plan_page_banner_offers_the_cancel(self):
        self.hold(self.core, paid=False)

        res = self.client.get(reverse("membershipannual"))
        self.assertContains(res, reverse("cancel_membership_purchase"))
        # The old copy sent people somewhere that had no cancel on it.
        self.assertNotContains(res, "cancel from your membership page")

    def test_an_active_member_is_never_shown_the_cancel(self):
        self.hold(self.core, paid=True)

        res = self.client.get(reverse("profile"))
        self.assertNotContains(res, reverse("cancel_membership_purchase"))

    def test_signing_out_does_not_expose_the_cancel(self):
        self.client.logout()
        res = self.client.get(reverse("cancel_membership_purchase"))
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse("login"), res.url)

