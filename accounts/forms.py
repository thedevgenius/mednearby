from django import forms
from django.contrib.auth.forms import AuthenticationForm


class PhoneAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Phone number",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "tel",
                "autofocus": True,
                "inputmode": "tel",
                "placeholder": "Enter your phone number",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "Enter your password",
            }
        ),
    )

    def clean_username(self):
        phone = self.cleaned_data["username"].strip()
        if not phone.isdigit() or len(phone) != 10:
            raise forms.ValidationError("Enter a valid 10-digit phone number.")
        return phone
