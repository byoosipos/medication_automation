def handle_billable_service(doc, method):
    """Universal handler for billable healthcare services"""
    # Skip billing for Vital Signs
    if doc.doctype == "Vital Signs":
        return
    
    if not doc.patient:
        return
    
    try:
        if doc.billing_item:
            # ... rest of the billing logic ...
            pass
    except AttributeError:
        # Skip if billing_item attribute doesn't exist
        return 