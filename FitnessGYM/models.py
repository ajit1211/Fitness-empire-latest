# models.py
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
    choice = models.CharField(max_length=50, null=True, blank=True)
    name = models.CharField(max_length=20, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class Membershipmonth(models.Model):
    choice = models.CharField(max_length=50, null=True, blank=True)
    name = models.CharField(max_length=20, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class membershipprocessedtocheck(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)  # Each user has one membership
    membership_yearly = models.ForeignKey(Membership, on_delete=models.CASCADE, null=True, blank=True)
    membership_monthly = models.ForeignKey(Membershipmonth, on_delete=models.CASCADE, null=True, blank=True)
    payment_status = models.BooleanField(default=False)  # ✅ Track if payment is done
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
                self.plan_expiry = timezone.now() + timedelta(days=365)
            elif self.membership_monthly:
                self.plan_expiry = timezone.now() + timedelta(days=30)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return bool(self.plan_expiry and self.plan_expiry < timezone.now())

    @property
    def days_remaining(self):
        if not self.plan_expiry:
            return None
        return max((self.plan_expiry - timezone.now()).days, 0)

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


