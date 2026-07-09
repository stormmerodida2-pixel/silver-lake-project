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
