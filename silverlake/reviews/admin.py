from django.contrib import admin

from core.audit import log_admin_action

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('customer_name', 'rating', 'is_approved', 'created_at')
    list_filter = ('is_approved', 'rating')
    search_fields = ('customer_name', 'comment')
    actions = ['approve_reviews']

    @admin.action(description='Approve selected reviews')
    def approve_reviews(self, request, queryset):
        # Not queryset.update() - that bypasses save() entirely, so a driver's rating (which
        # AdminReviewViewSet.approve recalculates on every approval) would silently go stale
        # for any review approved this way instead of through the real admin dashboard.
        count = 0
        for review in queryset.filter(is_approved=False):
            review.is_approved = True
            review.save(update_fields=['is_approved'])
            if review.driver_id:
                review.driver.recalculate_rating()
            log_admin_action(request, 'review.approve', review, detail='via Django admin')
            count += 1
        self.message_user(request, f'{count} review(s) approved.')
