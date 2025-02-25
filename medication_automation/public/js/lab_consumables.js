/**
 * Common functions for handling Lab Consumables in Lab Tests and Observations
 */

// Handle item change and warehouse change in Lab Consumables table
function setup_lab_consumables_handlers(frm, child_table_field) {
    frm.fields_dict[child_table_field].grid.on_row_refresh = function(doc) {
        setup_batch_query(frm, doc, child_table_field);
    };
    
    // Set up handlers when form is initialized
    $.each(frm.doc[child_table_field] || [], function(i, row) {
        setup_batch_query(frm, row, child_table_field);
    });
}

// Set up the batch query with proper filtering based on selected warehouse
function setup_batch_query(frm, row, child_table_field) {
    if (!row.item) return;
    
    // When item changes, check for batch tracking
    if (row.item && !row.has_batch_no) {
        frappe.db.get_value('Item', row.item, 'has_batch_no', (r) => {
            if (r && r.has_batch_no) {
                frappe.model.set_value(row.doctype, row.name, 'has_batch_no', r.has_batch_no);
                frm.refresh_field(child_table_field);
            }
        });
    }
    
    // When warehouse changes, update batch options
    $(frm.fields_dict[child_table_field].grid.grid_rows_by_docname[row.name].grid_form.fields_dict.warehouse.input).on('change', function() {
        frm.refresh_field(child_table_field);
    });
}

// Apply to Lab Test
frappe.ui.form.on('Lab Test', {
    refresh: function(frm) {
        if (frm.fields_dict['custom_consumables']) {
            setup_lab_consumables_handlers(frm, 'custom_consumables');
        }
    }
});

// Apply to Observation
frappe.ui.form.on('Observation', {
    refresh: function(frm) {
        if (frm.fields_dict['custom_observation_consumables']) {
            setup_lab_consumables_handlers(frm, 'custom_observation_consumables');
        }
    }
}); 