from django import forms
from django.contrib.auth.forms import UserCreationForm,AuthenticationForm 
from django.contrib.auth.models import User
from .models import Supplement,processedtocheck,membershipprocessedtocheck,aboutus,UserProfile
import re


class GymProductForm(forms.Form):
    gymProductName = forms.CharField(
        label="Product Name",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter product name'}),
    )
    gymProductPrice = forms.DecimalField(
        label="Product Price",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter product price'}),
    )
    gymProductDesc = forms.CharField(
        label="Product Description",
        widget=forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Enter product description'}),
    )


class RegisterForm(UserCreationForm):
    password1 = forms.CharField(
        label="Enter Password :",
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )
    password2 = forms.CharField(
        label="Confirm Password :",
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        labels = {
            'username': 'Enter Username',
            'first_name': 'Enter First Name',
            'last_name': 'Enter Last Name',
            'email': 'Enter Email',
        }
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your username'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your first name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your last name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter your email'}),
        }

    def clean_username(self):
        username = self.cleaned_data.get("username")
        if not re.match("^[a-zA-Z0-9_]*$", username):
            raise forms.ValidationError("Username can only contain letters, numbers, and underscores.")
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken. Please choose another.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already registered. Please use a different email.")
        return email

    def clean_password1(self):
        password1 = self.cleaned_data.get("password1")
        if len(password1) < 8:
            raise forms.ValidationError("Password must be at least 8 characters long.")
        if not any(char.isdigit() for char in password1):
            raise forms.ValidationError("Password must contain at least one digit.")
        if not any(char.isalpha() for char in password1):
            raise forms.ValidationError("Password must contain at least one letter.")
        return password1

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match.")
        
        return cleaned_data


class userAuthentication(AuthenticationForm):
    class Meta:
        model = User
        fields = ['username', 'password'] 

    username = forms.CharField(label='Enter username', widget=forms.TextInput(attrs={'class': 'form-control'}))
    password = forms.CharField(label='Enter password', widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    
class SupplementForm(forms.ModelForm):
    class Meta:
        model=Supplement
        fields=['supplementName','supplementDescription','supplementPrice','supplementImage','supplementRating','supplementCategory']

    def clean_prodName(self):
        prodName=self.cleaned_data.get('prodName')
        if not prodName.isalpha():
            raise forms.ValidationError("Product Name must be alpha")
        return prodName
    
class processedtocheckform(forms.ModelForm):
    class Meta:
        model=processedtocheck
        fields=['full_name','email','phone_number','address','city','pin_code','country','additional_notes']

    
class membershipprocessedtocheckform(forms.ModelForm):
    class Meta:
        model=membershipprocessedtocheck
        fields=['full_name','email','phone_number','city','pin_code']

class aboutusform(forms.ModelForm):
    class Meta:
        model=aboutus
        fields=['name','email','message']

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['full_name', 'gender', 'phone', 'email']