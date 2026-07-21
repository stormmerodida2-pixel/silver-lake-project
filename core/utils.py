import csv
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.http import HttpResponse


def parse_amount(raw):
    """Parses a user-submitted money amount (arriving as a JSON number or string) into a Decimal
    quantized to 2 decimal places - used at every offline-payment entry point instead of
    float(raw), which risks carrying binary floating-point imprecision into values that flow
    straight into Decimal arithmetic and a DecimalField. Raises ValueError for anything that
    doesn't parse (None, empty, non-numeric), so callers can turn it into a clean 400 the same
    way they already handle a bad amount today."""
    if raw is None or raw == '':
        raise ValueError('Amount is required.')
    try:
        return Decimal(str(raw)).quantize(Decimal('0.01'))
    except InvalidOperation:
        raise ValueError('Amount is not a valid number.')


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


def csv_response(filename, header, rows):
    """Builds a downloadable CSV HttpResponse - shared by every admin export action (bookings,
    payments, payouts). `rows` is an iterable of iterables, already in the exact column order
    `header` describes; this only handles the CSV encoding/headers, never any filtering/scoping,
    which stays the caller's responsibility (usually just get_queryset(), so an export always
    matches whatever the requester can already see or has filtered for)."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows(rows)
    return response


def parse_date_range(params):
    """Optional start_date/end_date query params (YYYY-MM-DD) for a CSV export's date range -
    returns (start, end) as date objects or None each. Raises ValueError on a malformed value so
    the caller can turn it into a clean 400."""
    def _parse(key):
        raw = params.get(key, '').strip()
        return date.fromisoformat(raw) if raw else None
    return _parse('start_date'), _parse('end_date')
