from django.db.models import Q


def search_filter(queryset, search, fields):
    """Case-insensitive OR search across the given fields (dotted lookups like
    'booking__customer_name' work fine) - a no-op when search is blank, so callers can always
    run this unconditionally rather than guarding it themselves. Shared by every admin viewset
    that has a search box (core/views.py, payments/views.py)."""
    if not search:
        return queryset
    query = Q()
    for field in fields:
        query |= Q(**{f'{field}__icontains': search})
    return queryset.filter(query)


def capture_replaced_files(serializer, field_names):
    """Call before serializer.save() on an update. Django never deletes a FileField/ImageField's
    previous file just because it's been reassigned to something else (a new upload, or None to
    clear it) - the old file is simply orphaned in storage forever unless something explicitly
    deletes it. Returns the File objects about to be replaced so they can be cleaned up with
    delete_files() *after* save() succeeds - never before, so a request that fails validation on
    some other field can't destroy a file that was already there."""
    old_files = []
    for name in field_names:
        if name in serializer.validated_data:
            old = getattr(serializer.instance, name, None)
            if old:
                old_files.append(old)
    return old_files


def delete_files(files):
    for file in files:
        file.delete(save=False)
