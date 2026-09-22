from django.contrib import admin
from .models import GymMembership, FitnessProgram, Trainer, Equipment, Supplement, SupplementCategory,cart,Category, FitnessClass,processedtocheck, Membership,Membershipmonth,membershipprocessedtocheck,Orders,aboutus,UserProfile,Customer,Wishlist



# Admin for GymMembership
class GymMembershipAdmin(admin.ModelAdmin):
    list_display = ['membershipId', 'membershipName', 'membershipPrice', 'duration', 'description']

admin.site.register(GymMembership, GymMembershipAdmin)

# Admin for FitnessProgram
class FitnessProgramAdmin(admin.ModelAdmin):
    list_display = ['programId', 'programName', 'programDurations', 'programLevel', 'programDescription']

admin.site.register(FitnessProgram, FitnessProgramAdmin)

# Admin for Trainer
class TrainerAdmin(admin.ModelAdmin):
    list_display = ['trainerId', 'trainerName', 'trainerSpecialization', 'trainerExperience', 'trainerEmail']

admin.site.register(Trainer, TrainerAdmin)

# Admin for Equipment
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ['equipmentId', 'equipmentName', 'equipmentType', 'equipmentCondition', 'equipmentPrice']

admin.site.register(Equipment, EquipmentAdmin)

# Admin for Customer
# class CustomerAdmin(admin.ModelAdmin):
#     list_display = ['customerId', 'customerName', 'customerEmail', 'customerPhone', 'membership']

# admin.site.register(Customer, CustomerAdmin)

# Admin for SupplementCategory
class SupplementCategoryAdmin(admin.ModelAdmin):
    list_display = ['categoryName', 'categoryDescription']

admin.site.register(SupplementCategory, SupplementCategoryAdmin)

# Admin for Supplement
class SupplementAdmin(admin.ModelAdmin):
    list_display = ['supplementName', 'supplementDescription', 'supplementPrice', 'supplementImage', 'supplementRating', 'supplementCategory']

admin.site.register(Supplement, SupplementAdmin)

class cartAdmin(admin.ModelAdmin):
    list_display = ['userid','productid','quantity']
admin.site.register(cart,cartAdmin)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')

@admin.register(FitnessClass)
class FitnessClassAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'category')

class processedtocheckAdmin(admin.ModelAdmin):
    list_display =['user','full_name','email','phone_number','address','city','pin_code','country','additional_notes']
admin.site.register(processedtocheck,processedtocheckAdmin)

class Membershipadmin(admin.ModelAdmin):
    list_display = ['id','choice','name','price','description']
admin.site.register(Membership,Membershipadmin)

class Membershipmonthadmin(admin.ModelAdmin):
    list_display = ['id','choice','name','price','description']
admin.site.register(Membershipmonth,Membershipmonthadmin)

class membershipprocessedtocheckadmin(admin.ModelAdmin):
    list_display=['user','full_name','email','phone_number','city','membership_monthly','membership_yearly','payment_status','pin_code','purchased_at','plan_expiry']
admin.site.register(membershipprocessedtocheck,membershipprocessedtocheckadmin)

class OrdersAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'supplement', 'quantity', 'order_date', 'status', 'total_price']
admin.site.register(Orders, OrdersAdmin)

class aboutusadmin(admin.ModelAdmin):
    list_display = ['id','name','email','message']
admin.site.register(aboutus,aboutusadmin)

class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'phone', 'gender')
admin.site.register(UserProfile,UserProfileAdmin)

class CustomerAdmin(admin.ModelAdmin):
    list_display = ('customerId','customerName','customerEmail','customerPhone','membership')
admin.site.register(Customer,CustomerAdmin)

@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'product', 'added_at')
    list_filter = ('added_at',)
    search_fields = ('user__username', 'product__supplementName')
