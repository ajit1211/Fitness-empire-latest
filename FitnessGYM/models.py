# models.py
import math
from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class GymMembership(models.Model):
    membershipId = models.IntegerField()
    membershipName = models.CharField(max_length=100)
    membershipPrice = models.DecimalField(max_digits=10, decimal_places=2)
    duration = models.IntegerField()  # Duration in months or days
    description = models.TextField()

class FitnessProgram(models.Model):
    programId = models.IntegerField()
    programName = models.CharField(max_length=100)
    programDurations = models.IntegerField()  # Duration in months or days
    programLevel = models.CharField(max_length=50)
    programDescription = models.TextField()

class Trainer(models.Model):
    trainerId = models.IntegerField()
    trainerName = models.CharField(max_length=100)
    trainerSpecialization = models.CharField(max_length=100)
    trainerExperience = models.IntegerField()  # Years of experience
    trainerEmail = models.EmailField()

class Equipment(models.Model):
    equipmentId = models.IntegerField()
    equipmentName = models.CharField(max_length=100)
    equipmentType = models.CharField(max_length=50)
    equipmentCondition = models.CharField(max_length=50)
    equipmentPrice = models.DecimalField(max_digits=10, decimal_places=2)

class Product(models.Model):
    productId = models.IntegerField(unique=True)
    productName = models.CharField(max_length=255)
    productPrice = models.DecimalField(max_digits=10, decimal_places=2)
    productDescription = models.TextField()
    productImage = models.ImageField(upload_to='product_images/',blank=True,null=True)  # To store images

    def __str__(self):
        return self.productName
    
def validation_Email(value):
    if "@gmail.com" in value:
        return value
    else:
        return ValidationError('This field accepts mail id of gmail only')

class Customer(models.Model):
    customerId = models.AutoField(primary_key=True)  # Auto increments and doesn't need a default
    customerName = models.CharField(max_length=100)
    customerEmail = models.CharField(max_length=200, validators=[validation_Email])
    customerPhone = models.CharField(max_length=15)
    membership = models.ForeignKey(GymMembership, on_delete=models.SET_NULL, null=True)

class SupplementCategory(models.Model):
    categoryName = models.CharField(max_length=100)
    categoryDescription = models.TextField()

    def __str__(self):
        return self.categoryName

class Supplement(models.Model):
    supplementName = models.CharField(max_length=200)
    supplementDescription = models.TextField()
    supplementPrice = models.DecimalField(max_digits=7, decimal_places=2)
    supplementImage = models.ImageField(upload_to='images/', null=True, blank=True)
    supplementRating = models.DecimalField(max_digits=2,decimal_places=1,null=True,blank=True)
    supplementCategory = models.ForeignKey(SupplementCategory, on_delete=models.CASCADE)
    stock = models.PositiveIntegerField(default=25)
    is_deleted=models.BooleanField(default=False)
    delete_details=models.DateTimeField(null=True,blank=True)

    class Meta:
        ordering = ['supplementName']

    def __str__(self):
        return self.supplementName

    @property
    def in_stock(self):
        return self.stock > 0

    @property
    def low_stock(self):
        return 0 < self.stock <= 5
    

class cart(models.Model):
    userid=models.ForeignKey(User,on_delete=models.CASCADE,db_column='userid',null=True,blank=True)
    productid=models.ForeignKey(Supplement,on_delete=models.CASCADE,db_column='productid')
    quantity=models.IntegerField(default=1)

class Wishlist(models.Model):
    """A product a signed-in shopper saved for later.

    Kept separate from `cart` so saving something never changes the order
    total, and so the list survives checkout.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="wishlist_items"
    )
    product = models.ForeignKey(
        Supplement, on_delete=models.CASCADE, related_name="wishlisted_by"
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "product")
        ordering = ["-added_at"]

    def __str__(self):
        return f"{self.user} -> {self.product}"


#for classes

class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

class FitnessClass(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="classes")
    name = models.CharField(max_length=100)
    image = models.ImageField(upload_to='images/')

    def __str__(self):
        return self.name


from datetime import timedelta

from django.utils import timezone

class Membership(models.Model):
    """A yearly plan."""

    choice = models.CharField(max_length=50, null=True, blank=True)
    name = models.CharField(max_length=20, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    # Where the plan sits in the ladder, low to high. Upgrades compare this
    # rather than the price, so a promotional price cannot reorder the tiers.
    tier = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["tier", "price"]

    def __str__(self):
        return self.name

class Membershipmonth(models.Model):
    """A monthly plan. Mirrors `Membership`, billed every 30 days."""

    choice = models.CharField(max_length=50, null=True, blank=True)
    name = models.CharField(max_length=20, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    tier = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["tier", "price"]

    def __str__(self):
        return self.name

# How long each billing cycle runs, in days. Used for the expiry date and for
# prorating the credit left on a plan when a member upgrades mid-term.
ANNUAL_TERM_DAYS = 365
MONTHLY_TERM_DAYS = 30


class membershipprocessedtocheck(models.Model):
    """One member plan, plus any upgrade started but not yet paid for.

    A member holds at most one plan. Upgrading does not overwrite that plan
    straight away: the chosen tier is parked in the `pending_*` fields until the
    payment lands, so a member who abandons an upgrade keeps the plan they are
    already paying for.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE)  # Each user has one membership
    membership_yearly = models.ForeignKey(Membership, on_delete=models.CASCADE, null=True, blank=True)
    membership_monthly = models.ForeignKey(Membershipmonth, on_delete=models.CASCADE, null=True, blank=True)
    payment_status = models.BooleanField(default=False)  # ✅ Track if payment is done

    # An upgrade awaiting payment. Promoted into the fields above by
    # `apply_pending_upgrade()` once PayPal returns.
    pending_yearly = models.ForeignKey(
        Membership, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pending_upgrades",
    )
    pending_monthly = models.ForeignKey(
        Membershipmonth, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pending_upgrades",
    )
    # What the upgrade costs before tax: the new plan less the unused credit,
    # frozen when it was quoted so the price cannot drift while the member sits
    # on the payment screen.
    pending_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    phone_number = models.CharField(max_length=15)
    city = models.CharField(max_length=100)
    pin_code = models.CharField(max_length=20)
    purchased_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)  # Purchase time
    plan_expiry = models.DateTimeField(null=True, blank=True)  # ✅ Plan expiry date

    def save(self, *args, **kwargs):
        # timezone.now() rather than datetime.now(): USE_TZ is on, so a naive
        # datetime was being stored as if it were UTC and the expiry date came
        # out shifted by the local UTC offset.
        if not self.plan_expiry:
            if self.membership_yearly:
                self.plan_expiry = timezone.now() + timedelta(days=ANNUAL_TERM_DAYS)
            elif self.membership_monthly:
                self.plan_expiry = timezone.now() + timedelta(days=MONTHLY_TERM_DAYS)
        super().save(*args, **kwargs)

    # -- what the member holds today ---------------------------------------
    @property
    def plan(self):
        """The plan on the account, whichever cycle it is billed on."""
        return self.membership_yearly or self.membership_monthly

    @property
    def cycle(self):
        if self.membership_yearly_id:
            return "annual"
        if self.membership_monthly_id:
            return "monthly"
        return None

    @property
    def term_days(self):
        return ANNUAL_TERM_DAYS if self.cycle == "annual" else MONTHLY_TERM_DAYS

    @property
    def is_expired(self):
        return bool(self.plan_expiry and self.plan_expiry < timezone.now())

    @property
    def is_active(self):
        """Paid for and still inside its term."""
        return bool(self.payment_status and self.plan and not self.is_expired)

    @property
    def days_remaining(self):
        """Whole days left, rounding a part-day up.

        timedelta.days truncates, so a term set to exactly 365 days reads as
        364 a microsecond later. Rounding up keeps the number the member is
        shown and the credit they are given honest about the day in progress.
        """
        if not self.plan_expiry:
            return None
        seconds = (self.plan_expiry - timezone.now()).total_seconds()
        if seconds <= 0:
            return 0
        return int(math.ceil(seconds / 86400))

    # -- the upgrade waiting to be paid for --------------------------------
    @property
    def pending_plan(self):
        return self.pending_yearly or self.pending_monthly

    @property
    def pending_cycle(self):
        if self.pending_yearly_id:
            return "annual"
        if self.pending_monthly_id:
            return "monthly"
        return None

    @property
    def has_pending_upgrade(self):
        return self.pending_plan is not None

    def plan_id_matches(self, plan, cycle):
        """True when this plan, on this cycle, is the one already on the record."""
        return self.cycle == cycle and self.plan is not None and self.plan.id == plan.id

    @property
    def awaiting_first_payment(self):
        """A plan was chosen but never paid for, so nothing is active yet."""
        return bool(self.plan and not self.payment_status)

    # -- pricing -----------------------------------------------------------
    def unused_credit(self):
        """What the member has paid for but not yet used.

        Prorated across the days still to run, so upgrading in month eleven of
        an annual plan does not hand back a full year of credit.
        """
        if not self.is_active or not self.plan_expiry:
            return Decimal("0.00")

        remaining = min(self.days_remaining or 0, self.term_days)
        if remaining <= 0:
            return Decimal("0.00")
        credit = self.plan.price * Decimal(remaining) / Decimal(self.term_days)
        return credit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def upgrade_cost(self, new_plan):
        """Price of moving to `new_plan`, net of the credit left on the old one."""
        due = Decimal(new_plan.price) - self.unused_credit()
        return max(due, Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # -- transitions --------------------------------------------------------
    def start_upgrade(self, new_plan, cycle, amount):
        """Park an upgrade without disturbing the plan currently in force."""
        self.pending_yearly = new_plan if cycle == "annual" else None
        self.pending_monthly = new_plan if cycle == "monthly" else None
        self.pending_amount = amount
        self.save(
            update_fields=["pending_yearly", "pending_monthly", "pending_amount"]
        )

    def clear_pending_upgrade(self):
        self.pending_yearly = None
        self.pending_monthly = None
        self.pending_amount = None
        self.save(
            update_fields=["pending_yearly", "pending_monthly", "pending_amount"]
        )

    def apply_pending_upgrade(self):
        """Promote the paid-for upgrade to the live plan.

        The expiry date is deliberately left alone: an upgrade buys a better
        tier for the term already running, not extra time. The member paid only
        the difference, so extending the term would hand back the remainder of
        the old plan a second time.
        """
        if not self.has_pending_upgrade:
            return False

        if self.pending_yearly_id:
            self.membership_yearly = self.pending_yearly
            self.membership_monthly = None
        else:
            self.membership_monthly = self.pending_monthly
            self.membership_yearly = None

        self.pending_yearly = None
        self.pending_monthly = None
        self.pending_amount = None
        self.payment_status = True
        self.save(
            update_fields=[
                "membership_yearly",
                "membership_monthly",
                "pending_yearly",
                "pending_monthly",
                "pending_amount",
                "payment_status",
            ]
        )
        return True

    def __str__(self):
        return self.full_name



class processedtocheck(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    phone_number = models.CharField(max_length=15)
    address = models.TextField()
    city = models.CharField(max_length=100)
    pin_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    additional_notes = models.TextField(blank=True, null=True)
    membership = models.ForeignKey(Membership, null=True, blank=True, on_delete=models.CASCADE)  # Annual
    membership_month = models.ForeignKey(Membershipmonth, null=True, blank=True, on_delete=models.CASCADE)  # Monthly

    def __str__(self):
        return self.full_name



class Orders(models.Model):
    STATUS_CHOICE = [
        ('PENDING','pending'),
        ('PROCESSING','processing'),
        ('SHIPPED','shipped'),
        ('DELIVERED','delivered'),
        ('CANCELLED','cancelled'),
    ]
    customer =models.ForeignKey(User, on_delete=models.CASCADE)
    supplement = models.ForeignKey(Supplement,on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    order_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICE, default='PENDING')
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"Order #{self.id} - {self.status}"
    
class aboutus(models.Model):
    name = models.CharField(max_length=50)
    email = models.EmailField()
    message = models.CharField(max_length=255)

    def __str__(self):
        return self.name
    

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE,null=True,blank=True)  # Link to User model
    full_name = models.CharField(max_length=255)
    gender = models.CharField(max_length=10, choices=[('Male', 'Male'), ('Female', 'Female')])
    phone = models.CharField(max_length=15)
    email = models.EmailField()

    def __str__(self):
        return self.full_name


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Ensure every User has a UserProfile.

    Replaces the old module-level loop in views.py, which queried the
    database at import time and broke `migrate` on a fresh database.
    """
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={"full_name": instance.get_full_name(), "email": instance.email},
        )


