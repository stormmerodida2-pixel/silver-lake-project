from django.contrib import admin

from .models import Driver, DriverApplication


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'years_of_experience', 'rating', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('full_name',)


@admin.register(DriverApplication)
class DriverApplicationAdmin(admin.ModelAdmin):
    list_display = (
        'full_name', 'phone_number', 'vehicle_name', 'vehicle_category',
        'status', 'created_at', 'reviewed_at',
    )
    list_filter = ('status', 'vehicle_category')
    search_fields = ('full_name', 'email', 'phone_number', 'license_number', 'vehicle_name')
    readonly_fields = ('created_driver', 'created_vehicle', 'reviewed_at', 'created_at')
    actions = ['approve_applications', 'reject_applications']

    @admin.action(description='Approve selected applications (creates Driver + Vehicle)')
    def approve_applications(self, request, queryset):
        approved = 0
        for application in queryset.exclude(status='approved'):
            application.approve()
            approved += 1
        self.message_user(request, f'{approved} application(s) approved and enlisted.')

    @admin.action(description='Reject selected applications')
    def reject_applications(self, request, queryset):
        rejected = 0
        for application in queryset.exclude(status='approved'):
            application.reject()
            rejected += 1
        self.message_user(request, f'{rejected} application(s) rejected.')
