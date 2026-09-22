from django.shortcuts import render, HttpResponse
from django.views import View
from .models import Customer, FitnessProgram, GymMembership, Trainer,SupplementCategory,Supplement,cart,Category, FitnessClass,Membership,processedtocheck,Membershipmonth,membershipprocessedtocheck,Orders,aboutus,UserProfile
from .form import RegisterForm,userAuthentication,forms,SupplementForm,processedtocheckform,membershipprocessedtocheckform,aboutusform,UserProfileForm
from django.contrib import messages
from decimal import Decimal
from django.contrib.auth.models import User
from django.urls import reverse
from django.contrib.auth import authenticate, login as auth_login,logout
from django.shortcuts import render, get_object_or_404, redirect
from .models import Product
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone
from django.conf import settings
import uuid
from paypal.standard.forms import PayPalPaymentsForm
from django.urls import reverse
# from rest_framework.decorators import 
 
# Display Fitness Programs and Memberships
def show(request):
    memberships = Membership.objects.all()  # Fetch all gym memberships
    programs = FitnessProgram.objects.all()  # Fetch all fitness programs
    context = {'memberships': memberships, 'programs': programs}
    return render(request, 'index.html', context)  # Render to 'index.html' template


# Customer CRUD Operations

# Display all customers and handle CRUD operations
def crud(request):
    if request.method == 'POST':
        customer_id = request.POST['customer-id']
        customer_name = request.POST['customer-name']
        customer_email = request.POST['customer-email']
        customer_contact = request.POST['customer-contact']
        
        # Create a new customer instance
        customer = Customer.objects.create(
            customerId=customer_id,
            customerName=customer_name,
            customerEmail=customer_email,
            contactNumber=customer_contact
        )
        customer.save()
        return HttpResponse('Customer created successfully')  # Response after saving customer
    else:
        return render(request, 'crud_operation.html')  # Render customer creation form for GET requests


# Show All Customers
def showdetails(request):
    customers = Customer.objects.all()  # Fetch all customers
    return render(request, 'dashboard.html', {'customers': customers})  # Render customers in the dashboard


# Delete Customer
def delete_customer(request, id):
    customer = Customer.objects.get(id=id)  # Find customer by ID
    customer.delete()  # Delete the customer
    return redirect('/showdetails')  # Redirect to show customer details after deletion


# Edit Customer Details
def edit_customer(request, id):
    if request.method == 'POST':
        customer_id = request.POST['customer-id']
        customer_name = request.POST['customer-name']
        customer_email = request.POST['customer-email']
        customer_contact = request.POST['customer-contact']
        
        # Update the customer details
        customer = Customer.objects.get(id=id)
        customer.customerId = customer_id
        customer.customerName = customer_name
        customer.customerEmail = customer_email
        customer.contactNumber = customer_contact
        customer.save()
        
        return redirect('/showdetails')  # Redirect after updating customer details
    else:
        customer = Customer.objects.get(id=id)  # Get the customer for editing
        return render(request, 'edit.html', {'customer': customer})  # Render customer edit form


# Contact Us Page (Basic page to show info)
def contactus(request):
    return HttpResponse("Contact us for gym membership, fitness programs, and more!")  # Static info page


# About Us Page (Basic page to show info)
def about_us(request):
    success_message = ""  # Initialize success message

    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        message = request.POST.get("message")

        if name and email and message:  # Basic validation
            aboutus.objects.create(name=name, email=email, message=message)
            success_message = "Thank you! Your message has been received."

    return render(request, 'aboutus.html', {'success_message': success_message})



# Simple View for Testing (Class-based View Example)
class SimpleView(View):
    def get(self, request):
        return HttpResponse("Welcome to our Fitness Gym!")  # Handle GET requests for SimpleView

    def post(self, request):
        return HttpResponse("Processing your request...")  # Handle POST requests for SimpleView



def home(request):
    return render(request, 'index.html') 

def register(request):
    if request.method == "POST":
        registerForm = RegisterForm(request.POST)
        if registerForm.is_valid():
            registerForm.save()
            return redirect('home')
    else:
        registerForm = RegisterForm()
        return render(request,'register.html',{'registerForm':registerForm})

def memberships(request):
    memberships = Membership.objects.all()  # Fetch all gym memberships
    return render(request, 'membershipannual.html',{'memberships':memberships})

def membershipmonthly(request):
    membershipmonthly = Membershipmonth.objects.all()
    return render(request,'membershipmonthly.html',{'Membershipmonth':membershipmonthly})

# View for Diet Plan
def diet_plan(request):
    return render(request, 'dietplan.html')

# View for Classes

def fitness_classes(request, category_name=None):
    categories = Category.objects.all()
    
    if category_name and category_name.lower() != 'all':
        category = Category.objects.filter(name__iexact=category_name).first()
        classes = FitnessClass.objects.filter(category=category)
    else:
        classes = FitnessClass.objects.all()
    
    return render(request, 'fitness_classes.html', {
        'categories': categories,
        'selected_category': category_name or 'All',
        'classes': classes
    })

# View for Training
def training(request):
    return render(request, 'training.html')

# View for Careers
def careers(request):
    return render(request, 'careers.html')

# View for Products
def products(request):
    categories = SupplementCategory.objects.all()
    products = Supplement.objects.all()
    context = {'categories': categories,'products': products}
    return render(request, 'protien.html', context)

def login(request):
    return render(request, 'login.html')

# Views for Login and Register
def login_view(request):
    return render(request, 'login.html')

def register_view(request):
    return render(request, 'register.html')

# User registration
def register(request):
    if request.method == "POST":
        registerForm = RegisterForm(request.POST)
        if registerForm.is_valid():
            registerForm.save()
            messages.success(request, "Successfully registered, now you can log in.")  # ✅ FIXED
            return redirect('login')
        else:
            messages.error(request, "Invalid form submission. Please check the details and try again.")
            return render(request, 'register.html', {'registerForm': registerForm})  

    else:
        registerForm = RegisterForm()
        return render(request, 'register.html', {'registerForm': registerForm})
 
def clean_email(self):
    email = self.cleaned_data.get('email')
    if User.objects.filter(email=email).exists():
        raise forms.ValidationError("This email is already registered.")
    return email

import datetime

def loginuser(request):
    if request.method == "POST":
        uname = request.POST['username']
        upass = request.POST['password']
        print(uname)
        print(upass)
        
        # Authenticate user
        user = authenticate(request, username=uname, password=upass)
        print(user)
        
        if user is not None:
            # Use auth_login (not login) to log the user in
            auth_login(request, user)
            response=redirect('home')
            request.session['username']=uname
            response.set_cookie('username',uname)
            response.set_cookie('Time',datetime.datetime.now())
            return response  # Redirect to home page or wherever you want
        else:
            messages.error(request, "Invalid username or password. Please try again.")
            return redirect("login")
    else:
        userform = userAuthentication()
        return render(request, 'login.html', {'userform': userform})
      
def signout(request):
    logout(request)
    return redirect('home')

def category(request, id):
    print(id)
    categories = SupplementCategory.objects.all()
    products = Supplement.objects.filter(supplementCategory_id=id)  # Use the correct field name
    return render(request, 'protien.html', {'categories': categories, 'products': products})

# Create or Update Product
def crud(request):
    if request.method == 'POST':
        productId = request.POST.get('product-id')
        productName = request.POST.get('product-name')
        productPrice = request.POST.get('product-price')
        productDescription = request.POST.get('product-description')
        productImage = request.FILES.get('product-image')
        
        prod=Product.objects.create(
            productId=productId, 
            productName=productName, 
            productPrice=productPrice, 
            productDescription=productDescription,
            productImage=productImage
        )
        prod.save()
        return HttpResponse('Product Data Submitted')
    else:
        return render(request, 'crud_operation.html')

# Show all product details
def showdetails(request):
    products = Product.objects.all()
    return render(request, 'dashboard.html', {'products': products})

# Delete a product
def deleteproduct(request, id):
    product = get_object_or_404(Product, id=id)
    product.delete()
    return redirect(reverse('showdetails'))

# Edit product details

def editproduct(request, id):
    product = get_object_or_404(Product, id=id)

    if request.method == 'POST':
        product.productId = request.POST.get('product-id') 
        product.productName = request.POST.get('product-name')
        product.productDescription = request.POST.get('product-description')
        product.productPrice = request.POST.get('product-price')

        if request.FILES.get('product-image'):
            product.productImage = request.FILES.get('product-image')

        product.save()
        return redirect(reverse('showdetails'))  
    
    return render(request, 'edit.html', {'product': product})


def cards(request,id):
    products=Supplement.objects.filter(id=id)
    return render(request,'cards.html',{'products':products})

# def addtocart(request,id):
#     prodid=Supplement.objects.filter(id=id)
#     print(prodid)
#     addtocartproduct=cart.objects.create(productid=prodid)
#     addtocartproduct.save()
#     return render(request,'addtocart.html')

@login_required(login_url='login')
def addtocart(request, id):
    # Get the current logged-in user
    userid = request.user.id
    user_details = get_object_or_404(User, id=userid)  # Fetch user details

    # Get the supplement product
    product = get_object_or_404(Supplement, id=id)  # Fetch the supplement product by ID

    # Check if the product is already in the cart for this user
    existing_cart_item = cart.objects.filter(productid=product, userid=user_details).exists()

    # Prepare the context
    context = {'products': [product]}

    if existing_cart_item:
        # Product already in the cart
        context['msg'] = "Already in cart! Please check."
    else:
        # Add product to the cart
        cart.objects.create(productid=product, userid=user_details)
        context['success'] = "Successfully added to cart."

    return render(request, 'cards.html', context)

def addproduct(request):
    if request.method == "POST":
        form = SupplementForm(request.POST, request.FILES)  # Use SupplementForm
        if form.is_valid():
            form.save()  # Save the valid form
            return redirect('home')
        else:
            # Render form with validation errors
            return render(request, 'addproductcrud.html', {'form': form})
    else:
        form = SupplementForm()
        return render(request, 'addproductcrud.html', {'form': form})

def deleteproductcrud(request, id):
    product = get_object_or_404(Supplement, id=id, is_deleted=False)
    product.is_deleted = True
    product.delete_details = timezone.now()
    product.save()  # Save the soft-deleted product
    return redirect('home')

def viewcart(request):
    userid = request.user.id
    print(userid)
    products = cart.objects.filter(userid=userid)
    print(products)

    total = 0

    # Calculate total price based on cart items
    for i in products:
        total += i.productid.supplementPrice * i.quantity

    # Apply delivery charges based on order value
    if total == 0:
        delivery_charge = 0  # No order, no delivery charge
    elif total <= 2000:
        delivery_charge = 120
    elif total <= 5000:
        delivery_charge = 70
    else:
        delivery_charge = 0  # Free delivery for orders above 5000

    grand_total = total + delivery_charge  # Final amount after adding delivery charge

    return render(request, 'viewcart.html', {
        'products': products,
        'total': total,
        'delivery_charge': delivery_charge,
        'grand_total': grand_total,
    })

from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages

def updateqty(request, qv, id):
    card_details = get_object_or_404(cart, id=id)  # Get cart item

    if qv == '1':  # Increase quantity
        if card_details.quantity < 5:  # Limit to 5
            card_details.quantity += 1
            card_details.save()
        else:
            messages.warning(request, "You cannot add more than 5 items of this product.")
    else:  # Decrease quantity
        if card_details.quantity > 1:  # Ensure it doesn't go below 1
            card_details.quantity -= 1
            card_details.save()

    return redirect('viewcart')

def searchdata(request):
    query = request.GET.get('query', '').strip()
    products = Supplement.objects.none()
    categories = SupplementCategory.objects.none()
    menu_items = []  # Store matching menu items

    # Define menu items (URL names and their display text)
    all_menu_items = [
        {"name": "Memberships", "url": "membershipannual"},
        {"name": "Diet Plan", "url": "dietplan"},
        {"name": "Classes", "url": "all_classes"},
        {"name": "Training", "url": "training"},
        {"name": "Products", "url": "protien"},
        {"name": "About Us", "url": "aboutus"},
        {"name": "Careers", "url": "careers"},
    ]

    if query:
        # Search for products
        products_by_name = Supplement.objects.filter(supplementName__icontains=query)
        categories = SupplementCategory.objects.filter(categoryName__icontains=query)
        products_by_category = Supplement.objects.filter(supplementCategory__in=categories)
        products = products_by_name.union(products_by_category)

        # Search for menu items (if query matches menu name)
        menu_items = [
            item for item in all_menu_items if query.lower() in item["name"].lower()
        ]

    return render(request, 'protien.html', {
        'query': query,
        'products': products,
        'categories': categories,
        'menu_items': menu_items,
        'no_results': not products.exists() and not menu_items,
    })


def remove(request,id):
    product=cart.objects.filter(id=id)
    product.delete()
    return redirect('viewcart')

@login_required
def Processedtocheck(request):
    userid = request.user.id
    products = cart.objects.filter(userid=userid)

    # Calculate total price
    total = sum(i.productid.supplementPrice * i.quantity for i in products)

    # Apply delivery charges based on order value
    if total == 0:
        delivery_charge = 0  # No order, no delivery charge
    elif total <= 2000:
        delivery_charge = 120
    elif total <= 5000:
        delivery_charge = 70
    else:
        delivery_charge = 0  # Free delivery for orders above 5000

    grand_total = total + delivery_charge  # Final amount after adding delivery charge

    # Check if the user has already submitted their details
    form_filled = processedtocheck.objects.filter(user=request.user).exists()

    if form_filled:
        # If user has already filled the form, redirect to payment page
        return redirect('makepayment')  # Change 'payment_page' to your actual payment URL name

    if request.method == "POST":
        form = processedtocheckform(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.user = request.user
            customer.save()
            return redirect('makepayment')  # Redirect to payment page after successful form submission

    else:
        form = processedtocheckform()

    return render(request, 'checkout.html', {
        'form': form, 
        'total': total, 
        'delivery_charge': delivery_charge,
        'grand_total': grand_total,
        'form_filled': form_filled
    })
@login_required(login_url='login')
def profile_view(request):
    membership = membershipprocessedtocheck.objects.filter(user=request.user).first()

    pending_payment = membership and not membership.payment_status  # Check if payment is pending

    if pending_payment:
        messages.warning(request, "⚠️ You need to complete your payment to activate your membership.")

    return render(request, 'profile.html', {
        'membership': membership,  # Always pass membership, even if payment is pending
        'pending_payment': pending_payment,
    })



@login_required(login_url='login')
def membership_processed_view(request, id):
    """View for processing yearly membership purchase"""
    membership = get_object_or_404(Membership, id=id)

    gst_rate = Decimal('0.18')  # GST 18%
    total_price = membership.price + (membership.price * gst_rate)

    existing_membership = membershipprocessedtocheck.objects.filter(user=request.user).first()

    if existing_membership:
        if existing_membership.membership_monthly:
            messages.warning(request, "You already have a monthly membership and cannot buy a yearly one.")
            return redirect('profile')

        if existing_membership.membership_yearly:
            messages.warning(request, "You already have a yearly membership and cannot buy another one.")
            return redirect('profile')

    if request.method == 'POST':
        form = membershipprocessedtocheckform(request.POST)
        if form.is_valid():
            membership_customer = form.save(commit=False)
            membership_customer.user = request.user
            membership_customer.membership_yearly = membership
            membership_customer.membership_monthly = None  # Ensure monthly is empty
            membership_customer.save()
            messages.success(request, "Proceed to payment to complete your membership.")
            return redirect('membershipprocessedtocheckouts', id=id)


    else:
        form = membershipprocessedtocheckform()

    return render(request, 'membership_form.html', {
        'form': form,
        'membership': membership,
        'total_price': total_price,
    })


@login_required(login_url='login')
def membership_processed_view_month(request, id):
    """View for processing monthly membership purchase"""
    membership = get_object_or_404(Membershipmonth, id=id)

    existing_membership = membershipprocessedtocheck.objects.filter(user=request.user).first()

    if existing_membership:
        if existing_membership.membership_yearly:
            messages.warning(request, "You already have a yearly membership and cannot buy a monthly one.")
            return redirect('profile')

        if existing_membership.membership_monthly:
            messages.warning(request, "You already have a monthly membership and cannot buy another one.")
            return redirect('profile')

    if request.method == 'POST':
        form = membershipprocessedtocheckform(request.POST)
        if form.is_valid():
            membership_customer = form.save(commit=False)
            membership_customer.user = request.user
            membership_customer.membership_monthly = membership
            membership_customer.membership_yearly = None  # Ensure yearly is empty
            membership_customer.save()
            messages.success(request, "Proceed to payment to complete your membership.")
            return redirect('membershipprocessedtocheckout', id=id)

    else:
        form = membershipprocessedtocheckform()

    return render(request, 'membership_form_month.html', {
        'form': form,
        'membership': membership,
    })


def makepayment(request):
    uid = request.user.id  # Get logged-in user's ID
    print(uid)  # Debugging

    products = cart.objects.filter(userid=uid)  # Get cart items
    print(products)  # Debugging

    totalCount = sum(prod.quantity for prod in products)  # Total quantity
    totalamount = sum(prod.productid.supplementPrice * prod.quantity for prod in products)  # Total price

    # Apply delivery charges based on order value
    if totalamount == 0:
        delivery_charge = 0  # No order, no delivery charge
    elif totalamount <= 2000:
        delivery_charge = 120
    elif totalamount <= 5000:
        delivery_charge = 70
    else:
        delivery_charge = 0  # Free delivery for orders above 5000

    grand_total = totalamount + delivery_charge  # Final amount after adding delivery charge

    custformdetail = processedtocheck.objects.filter(user=uid)

    host = request.get_host()

    paypal_checkout = {
        'business': settings.PAYPAL_RECEIVER_EMAIL,
        'amount': grand_total,  # Use grand total instead of just totalamount
        'item_name': 'Suppliment',
        'invoice': uuid.uuid4(),  # Unique invoice number
        'currency_code': 'USD',
        'notify_url': f"http://{host}{reverse('paypal-ipn')}",
        'return_url': f"http://{host}{reverse('paymentsuccess')}",
        'cancel_url': f"http://{host}{reverse('paymentfailed')}",
    }

    paypal_payment = PayPalPaymentsForm(initial=paypal_checkout)

    return render(request, 'processedtocheckout.html', {
        'products': products,
        'totalCount': totalCount,
        'totalamount': totalamount,
        'delivery_charge': delivery_charge,
        'grand_total': grand_total,  # Pass grand total to template
        'custformdetail': custformdetail,
        'paypalpayment': paypal_payment
    })  
  
def paymentsuccess(request):
    userid = request.user.id
    print(userid)
    
    products = cart.objects.filter(userid=userid)
    print(products)

    order_list = []  # To store newly created orders
    total = 0

    for i in products:
        total += i.productid.supplementPrice * i.quantity
        order = Orders.objects.create(
            customer=i.userid,
            supplement=i.productid,
            quantity=i.quantity,
            total_price=total
        )
        order.save()
        order_list.append(order)  # Store the current order details
        i.delete()  # Remove the product from the cart after ordering

    return render(request, 'paymentsuccess.html', {'orders': order_list})  

def orders(request):
    orders=Orders.objects.filter(customer=request.user.id)
    return render(request,'orders.html',{'orders':orders})

def myorders(request):
    orders=Orders.objects.filter(customer=request.user.id)
    return render(request,'myorder.html',{'orders':orders})


def remove_order(request, order_id):
    order = get_object_or_404(Orders, id=order_id, customer=request.user)

    # Check if the order is already delivered, prevent deletion if needed
    if order.status == "Delivered":
        messages.warning(request, "You cannot remove a delivered order.")
    else:
        order.delete()
        messages.success(request, "Order removed successfully.")

    return redirect('orders')  # Redirect to the orders page

def cancel_order(request, order_id):
    order = get_object_or_404(Orders, id=order_id, customer=request.user)
    
    if order.status != "Cancelled":  # Ensure order is not already canceled
        order.status = "Cancelled"
        order.save()
        messages.success(request, "Your order has been cancelled successfully.")
    else:
        messages.warning(request, "Order is already cancelled.")

    return redirect('orders')

def paymentfailed(request):
    return render(request,'paymentfailed.html')


def edit_address(request, id):
    customer = get_object_or_404(processedtocheck, id=id)
    if request.method == "POST":
        form = processedtocheckform(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            return redirect('makepayment')
    else:
        form = processedtocheckform(instance=customer)
    
    return render(request, 'edit_address.html', {'form': form}) 

#Annuual
@login_required(login_url='login')
def membership_processedtocheckout(request, id):
    membership = get_object_or_404(Membership, id=id)
    
    # Fetch pending payment
    membership_record = membershipprocessedtocheck.objects.filter(user=request.user, membership_yearly=membership).first()

    if not membership_record:
        messages.warning(request, "No pending payment found.")
        return redirect('profile')

    gst_rate = Decimal('0.18')
    total_price = membership.price + (membership.price * gst_rate)

    host = request.get_host()
    paypal_checkout = {
        'business': settings.PAYPAL_RECEIVER_EMAIL,
        'amount': total_price,
        'item_name': membership.name,
        'invoice': uuid.uuid4(),
        'currency_code': 'USD',
        'notify_url': f"http://{host}{reverse('paypal-ipn')}",
        'return_url': f"http://{host}{reverse('paymentmembership')}",
        'cancel_url': f"http://{host}{reverse('paymentfailed')}",
    }

    paypal_payment = PayPalPaymentsForm(initial=paypal_checkout)

    return render(request, 'membershipprocessedtocheckout.html', {
        'membership': membership,
        'total_price': total_price,
        'paypalpayment': paypal_payment,
    })
@login_required(login_url='login')
def membership_processedtocheckout_monthly(request, id):
    membership = get_object_or_404(Membershipmonth, id=id)

    # Fetch pending payment
    membership_record = membershipprocessedtocheck.objects.filter(user=request.user, membership_monthly=membership).first()

    if not membership_record:
        messages.warning(request, "No pending payment found.")
        return redirect('profile')

    gst_rate = Decimal('0.18')
    total_price = membership.price + (membership.price * gst_rate)

    host = request.get_host()
    paypal_checkout = {
        'business': settings.PAYPAL_RECEIVER_EMAIL,
        'amount': membership.price,
        'item_name': membership.name,
        'invoice': uuid.uuid4(),
        'currency_code': 'USD',
        'notify_url': f"http://{host}{reverse('paypal-ipn')}",
        'return_url': f"http://{host}{reverse('paymentmembership')}",
        'cancel_url': f"http://{host}{reverse('paymentfailed')}",
    }

    paypal_payment = PayPalPaymentsForm(initial=paypal_checkout)

    return render(request, 'membershipprocessedtocheckoutmonthly.html', {
        'membership': membership,
        'total_price': total_price,
        'paypalpayment': paypal_payment,
    })

@login_required(login_url='login')
def paymentmembership(request):
    membership = membershipprocessedtocheck.objects.filter(user=request.user, payment_status=False).first()
    
    if membership:
        membership.payment_status = True  # ✅ Mark as paid
        membership.save()

        messages.success(request, "Payment successful! Your membership is now active.")
    else:
        messages.warning(request, "No pending membership found.")

    return render(request,'finalthankyou.html')

@login_required
def my_profile(request):
    user_profile = UserProfile.objects.filter(user=request.user).first()  # Fetch profile

    return render(request, 'my_profile.html', {'user_profile': user_profile})


@login_required
def edit_profile(request, user_id):
    user_profile, created = UserProfile.objects.get_or_create(user_id=user_id)  

    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=user_profile)
        if form.is_valid():
            form.save()
            return redirect('my_profile')  # Redirect to profile page after update
    else:
        form = UserProfileForm(instance=user_profile)

    return render(request, 'profile_edit.html', {'form': form})

@login_required
def my_addresses(request):
    user_profile = UserProfile.objects.filter(user=request.user).first()  # Fetch profile
    addresses = processedtocheck.objects.filter(user=request.user)
    return render(request, 'my_addresses.html', {'addresses': addresses,'user_profile': user_profile})


from rest_framework.decorators import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import customerSerializer

class crudapi(APIView):
    def get(self,request):
        id=request.data.get('id',None)
        if id:
            try:
                customer=Customer.objects.get(customerId=id)
                customerdata=customerSerializer(customer)
                print(customerdata)
                return Response(customerdata.data,status.HTTP_200_OK)
            except:
                return Response({'msg':'Data not Found'},status=status.HTTP_404_NOT_FOUND)
            
        else:
            customer=Customer.objects.all()
            print(customer)
            customerdata=customerSerializer(customer,many=True)
            print(customerdata)
            return Response(customerdata.data,status=status.HTTP_200_OK)
        

    def post(self,request):
        customerdetails=request.data
        print(customerdetails)
        customerdata=customerSerializer(data=customerdetails)
        print(customerdata)
        if customerdata.is_valid():
            customerdata.save()
            return Response({'msg':'Data is successfully inserted'},status=status.HTTP_200_OK)
        return Response({'msg':'Data is not available'},status=status.HTTP_404_NOT_FOUND)
    

    def patch(self,request):
        new_data=request.data
        id=new_data.get('id',None)
        if id:
            try:
                customer_data=Customer.objects.get(customerid=id)
                print(customer_data)
                customer_data=customerSerializer(customer_data,new_data,partial=True)
                if customer_data.is_valid():
                    customer_data.save()
                    return Response({'msg':'Data update successfully'},status=status.HTTP_200_OK)
            except:
                return Response({'msg':'data is not available'},status=status.HTTP_404_NOT_FOUND)
    
    def delete(self,request):
        id=request.data.get('id',None)
        if id:
            try:
                customer=Customer.objects.get(customerId=id)
                customer.delete()
                return Response({'msg':'data delete successfully'},status.HTTP_200_OK)
            except:
                return Response({'msg':'Data not Found'},status=status.HTTP_404_NOT_FOUND)
            
        else:
            return Response({'msg':'please provied a valid id'},status=status.HTTP_200_OK)
        
import random  
from django.core.mail import send_mail

def forgetpassword(request):
    if request.method == "POST":
        email = request.POST.get('email')

        users = User.objects.filter(email=email)
        print(users)
        if users.exists():
            user = users.first()
            otp = random.randint(100000, 999999)
            request.session['reset_otp'] = otp
            request.session['reset_email'] = email
            request.session['otp_purpose'] = "login"

            subject = "Password Reset Request - Your OTP Inside"
            message = f"""
            Hello {user.username},

            We received a request to reset your password. To proceed, please use the One-Time Password (OTP) below:

            🔐 **Your OTP:** {otp}

            This OTP is valid for a limited time. If you did not request this, please ignore this email, and your account will remain secure.

            For security reasons, never share your OTP with anyone.

            Best regards,  
            Your Support Team
            """

            send_mail(
                subject,message,settings.EMAIL_HOST_USER,[email],fail_silently=False
            )
            return redirect ('verifyotp')
        else:
            messages.error(request, "Email not found ! Please enter a registered email")
            return render(request, 'forgetpassword.html')
    return render(request,'forgetpassword.html')

def resetpassword(request):
    if request.method == "POST":
        new_password = request.POST['new_password']
        confirm_password = request.POST['confirm_password']
        email = request.session.get('reset_email')

        if new_password == confirm_password:
            try:
                user =  User.objects.get(email=email)
                user.set_password(new_password)
                user.save()

                del request.session['reset_otp']
                del request.session['reset_email']

                messages.success(request,"Password reset successful ! You can login ")
                return redirect('login')
            except User.DoesNotExist:
                messages.error(request,"Somthing went wrong")
                return redirect('forgotpassword')
        else:
            messages.error(request,"Password do not match ! Try again")
            return render(request, 'resetpassword.html')
    return render(request,'resetpassword.html')
                

def verifyotp(request):
    if request.method == "POST":
        entered_otp = request.POST.get('otp')
        stored_otp = request.session.get('reset_otp')
        otp_purpose = request.session.get('otp_purpose','')

        if stored_otp and entered_otp == str(stored_otp):
            if otp_purpose == "login":
                return redirect('resetpassword')
            elif otp_purpose == "payment":
                return  redirect('checkout')
            else:
                return redirect('home')
            
        else:
            messages.error(request, "Invalid OTP! Please enter valid otp or try again")
    return render(request,'verifyotp.html')

def weightlossplan(request):
    return render(request,'weightlossplan.html')

def muselloss(request):
    return render(request,'musel.html')

def healthlyplan(request):
    return render(request,'healthlyplan.html')


