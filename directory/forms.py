from django import forms

from .models import Lead


class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = ("patient_name", "phone", "message")

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not phone.isdigit() or len(phone) != 10:
            raise forms.ValidationError("Enter a valid 10-digit phone number.")
        return phone


class EnquiryLeadForm(LeadForm):
    service = forms.ChoiceField(required=False)

    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        services = business.services if isinstance(business.services, list) else []
        self.fields["service"].choices = [("", "Select a service")] + [
            (service, service) for service in services if isinstance(service, str) and service.strip()
        ]

    class Meta(LeadForm.Meta):
        fields = ("patient_name", "phone", "service", "message")
