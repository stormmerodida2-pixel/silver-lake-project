from django.contrib import admin

from .models import Vehicle, VehicleImage


class VehicleImageInline(admin.TabularInline):
    model = VehicleImage
    extra = 1


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'category', 'passenger_capacity', 'price_per_day', 'is_available',
        'insurance_expiry_date', 'insurance_valid', 'inspection_expiry_date', 'inspection_valid',
    )
    list_filter = ('category', 'is_available', 'allow_self_drive', 'allow_with_driver')
    search_fields = ('name',)
    inlines = [VehicleImageInline]

    @admin.display(description='Insurance OK', boolean=True)
    def insurance_valid(self, obj):
        return not obj.is_insurance_expired

    @admin.display(description='Inspection OK', boolean=True)
    def inspection_valid(self, obj):
        return not obj.is_inspection_expired
