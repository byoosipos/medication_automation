/**
 * Common functions for handling Lab Consumables in Lab Tests and Observations
 */

// Handle item change and warehouse change in Lab Consumables table
function setup_lab_consumables_handlers(frm, child_table_field) {
    // Set up row event handlers for the child table
    frm.fields_dict[child_table_field].grid.add_custom_button(__('Update Batch Status'), function() {
        update_batch_status_for_all_rows(frm, child_table_field);
    });
    
    // Setup handlers for each row when the form loads or refreshes
    frm.fields_dict[child_table_field].grid.on_row_refresh = function(doc, cdt, cdn) {
        update_batch_status(frm, doc, cdt, cdn);
    };
    
    // Handle item selection
    frm.fields_dict[child_table_field].grid.wrapper.on('change', '.grid-row .frappe-control[data-fieldname="item"] input', function() {
        const $row = $(this).closest('.grid-row');
        const docname = $row.attr('data-name');
        if (docname) {
            const doc = locals[cdt][docname];
            if (doc && doc.item) {
                // Immediately check and fetch batch status
                frappe.db.get_value('Item', doc.item, 'has_batch_no', function(r) {
                    if (r && r.has_batch_no !== undefined) {
                        frappe.model.set_value(doc.doctype, doc.name, 'has_batch_no', r.has_batch_no);
                        frm.refresh_field(child_table_field);
                    }
                });
            }
        }
    });
    
    // Handle warehouse selection to refresh batch options
    frm.fields_dict[child_table_field].grid.wrapper.on('change', '.grid-row .frappe-control[data-fieldname="warehouse"] input', function() {
        frm.refresh_field(child_table_field);
    });
}

// Update batch status for a specific row
function update_batch_status(frm, doc, cdt, cdn) {
    if (!doc.item) return;
    
    // Get the actual grid row and find batch field
    const grid_row = frm.fields_dict[cdt === 'Lab Test' ? 'custom_consumables' : 'custom_observation_consumables'].grid.grid_rows_by_docname[cdn];
    if (!grid_row) return;
    
    const batch_field = grid_row.grid_form?.fields_dict?.batch_no;
    const item_field = grid_row.grid_form?.fields_dict?.item;
    
    if (!batch_field || !item_field) return;
    
    // If item has no value yet, hide batch field
    if (!doc.item) {
        $(batch_field.wrapper).hide();
        return;
    }
    
    // Check if has_batch_no is already set correctly
    if (doc.has_batch_no === undefined || doc.has_batch_no === null) {
        frappe.db.get_value('Item', doc.item, 'has_batch_no', function(r) {
            if (r && r.has_batch_no !== undefined) {
                frappe.model.set_value(doc.doctype, doc.name, 'has_batch_no', r.has_batch_no);
                
                // Immediately update UI while the value sets
                if (r.has_batch_no) {
                    $(batch_field.wrapper).show();
                } else {
                    $(batch_field.wrapper).hide();
                }
                
                frm.refresh_field(doc.parentfield);
            }
        });
    } else {
        // Use existing has_batch_no value to show/hide
        if (doc.has_batch_no) {
            $(batch_field.wrapper).show();
        } else {
            $(batch_field.wrapper).hide();
        }
    }
}

// Update batch status for all rows in the table
function update_batch_status_for_all_rows(frm, child_table_field) {
    $.each(frm.doc[child_table_field] || [], function(i, row) {
        update_batch_status(frm, row, row.doctype, row.name);
    });
}

// Apply to Lab Test
frappe.ui.form.on('Lab Test', {
    refresh: function(frm) {
        if (frm.fields_dict['custom_consumables']) {
            setup_lab_consumables_handlers(frm, 'custom_consumables');
            update_batch_status_for_all_rows(frm, 'custom_consumables');
        }
    },
    
    custom_consumables_add: function(frm, cdt, cdn) {
        update_batch_status(frm, locals[cdt][cdn], cdt, cdn);
    }
});

// Apply to Observation
frappe.ui.form.on('Observation', {
    refresh: function(frm) {
        if (frm.fields_dict['custom_observation_consumables']) {
            setup_lab_consumables_handlers(frm, 'custom_observation_consumables');
            update_batch_status_for_all_rows(frm, 'custom_observation_consumables');
        }
    },
    
    custom_observation_consumables_add: function(frm, cdt, cdn) {
        update_batch_status(frm, locals[cdt][cdn], cdt, cdn);
    }
}); 