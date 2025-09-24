/**
 * Common functions for handling Lab Consumables in Lab Tests and Observations
 */

// Handle item change and warehouse change in Lab Consumables table
function setup_lab_consumables_handlers(frm, child_table_field) {
    // Setup functions for the entire grid
    frm.fields_dict[child_table_field].grid.add_custom_button(__('Update Batch Status'), function() {
        update_batch_status_for_all_rows(frm, child_table_field);
    });
    
    // Setup get_query for batch_no selection - following ERPNext pattern
    frm.fields_dict[child_table_field].grid.get_field('batch_no').get_query = function(doc, cdt, cdn) {
        var child = locals[cdt][cdn];
        if (!child.item) {
            return { filters: { name: '' } }; // Empty filter if no item selected
        }
        
        // Use the standard method similar to stock_entry.js
        return {
            query: "medication_automation.doc_events.get_batch_query",
            filters: {
                'item': child.item,
                'warehouse': child.warehouse || ''
            }
        };
    };
    
    // Handle item selection like stock_entry.js
    frm.fields_dict[child_table_field].grid.wrapper.on('change', '.grid-row .frappe-control[data-fieldname="item"] input', function() {
        const $row = $(this).closest('.grid-row');
        const docname = $row.attr('data-name');
        if (docname) {
            const cdt = $row.attr('data-doctype');
            const doc = locals[cdt][docname];
            
            if (doc && doc.item) {
                // Clear batch number when item changes (standard behavior)
                frappe.model.set_value(doc.doctype, doc.name, 'batch_no', '');
                
                // Fetch item properties including has_batch_no
                frappe.db.get_value('Item', doc.item, ['has_batch_no', 'stock_uom'], function(r) {
                    if (r && r.has_batch_no !== undefined) {
                        frappe.model.set_value(doc.doctype, doc.name, 'has_batch_no', r.has_batch_no);
                        
                        // Set UOM from item if not already set
                        if (!doc.uom && r.stock_uom) {
                            frappe.model.set_value(doc.doctype, doc.name, 'uom', r.stock_uom);
                        }
                        
                        frm.refresh_field(child_table_field);
                        
                        // Show guidance message
                        if (r.has_batch_no && !doc.warehouse) {
                            frappe.show_alert({
                                message: __('Select a warehouse to see available batches for {0}', [doc.item]),
                                indicator: 'blue'
                            }, 5);
                        }
                    }
                });
            }
        }
    });
    
    // Handle warehouse selection - similar to stock_entry.js s_warehouse handler
    frm.fields_dict[child_table_field].grid.wrapper.on('change', '.grid-row .frappe-control[data-fieldname="warehouse"] input', function() {
        const $row = $(this).closest('.grid-row');
        const docname = $row.attr('data-name');
        if (docname) {
            const cdt = $row.attr('data-doctype');
            const doc = locals[cdt][docname];
            
            if (doc && doc.item && doc.warehouse && doc.has_batch_no) {
                // Clear batch when warehouse changes (standard behavior)
                frappe.model.set_value(doc.doctype, doc.name, 'batch_no', '');
                
                // Check available stock - similar to stock_entry.js
                check_batch_availability(doc.item, doc.warehouse);
            }
        }
    });
    
    // Handle batch selection - like stock_entry.js batch_no handler
    frm.fields_dict[child_table_field].grid.wrapper.on('change', '.grid-row .frappe-control[data-fieldname="batch_no"] input', function() {
        const $row = $(this).closest('.grid-row');
        const docname = $row.attr('data-name');
        if (docname) {
            const cdt = $row.attr('data-doctype');
            const doc = locals[cdt][docname];
            
            if (doc && doc.batch_no) {
                // Optional: Get additional batch information if needed
                // frappe.db.get_value('Batch', doc.batch_no, ['expiry_date', 'batch_qty'], function(r) {
                //     // Could show additional info or set fields based on batch
                // });
            }
        }
    });
    
    // Add row-specific batch refresh button - convenience function
    frm.fields_dict[child_table_field].grid.add_custom_button(__('Refresh Batch Options'), function() {
        const focused_row = frm.get_field(child_table_field).grid.get_focused_row();
        if (!focused_row) {
            frappe.show_alert({
                message: __('Please select a row first'),
                indicator: 'red'
            }, 3);
            return;
        }
        
        const doc = focused_row.doc;
        if (!doc.item || !doc.warehouse) {
            frappe.show_alert({
                message: __('Please select both Item and Warehouse'),
                indicator: 'orange'
            }, 3);
            return;
        }
        
        // Clear batch and refresh field
        frappe.model.set_value(doc.doctype, doc.name, 'batch_no', '');
        frm.refresh_field(child_table_field);
        
        // Check batch availability
        check_batch_availability(doc.item, doc.warehouse);
    });
}

// Update batch status for a specific row
function update_batch_status(frm, doc, cdt, cdn) {
    if (!doc.item) return;
    
    // Find the actual grid row
    const grid_row = frm.fields_dict[cdt === 'Lab Test' ? 'custom_consumables' : 'custom_observation_consumables'].grid.grid_rows_by_docname[cdn];
    if (!grid_row) return;
    
    const batch_field = grid_row.grid_form?.fields_dict?.batch_no;
    
    // If item has no value yet, hide batch field
    if (!doc.item) {
        $(batch_field?.wrapper).hide();
        return;
    }
    
    // Check if has_batch_no is already set correctly
    if (doc.has_batch_no === undefined || doc.has_batch_no === null) {
        frappe.db.get_value('Item', doc.item, 'has_batch_no', function(r) {
            if (r && r.has_batch_no !== undefined) {
                frappe.model.set_value(doc.doctype, doc.name, 'has_batch_no', r.has_batch_no);
                
                // Immediately update UI while the value sets
                if (r.has_batch_no) {
                    $(batch_field?.wrapper).show();
                } else {
                    $(batch_field?.wrapper).hide();
                }
                
                frm.refresh_field(doc.parentfield);
            }
        });
    } else {
        // Use existing has_batch_no value to show/hide
        if (doc.has_batch_no) {
            $(batch_field?.wrapper).show();
        } else {
            $(batch_field?.wrapper).hide();
        }
    }
}

// Update batch status for all rows in the table
function update_batch_status_for_all_rows(frm, child_table_field) {
    const items = frm.doc[child_table_field] || [];
    
    for (let item of items) {
        update_batch_status(frm, item, item.doctype, item.name);
    }
}

// Check batch availability - helper function
function check_batch_availability(item_code, warehouse) {
    frappe.call({
        method: 'frappe.db.sql',
        args: {
            query: `
                SELECT 
                    batch_no, 
                    SUM(actual_qty) as qty
                FROM 
                    \`tabStock Ledger Entry\`
                WHERE 
                    item_code = %s 
                    AND warehouse = %s 
                    AND batch_no IS NOT NULL
                GROUP BY 
                    batch_no
                HAVING 
                    SUM(actual_qty) > 0
                LIMIT 1
            `,
            values: [item_code, warehouse]
        },
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                frappe.show_alert({
                    message: __('Found batches with stock for {0} in {1}', [item_code, warehouse]),
                    indicator: 'green'
                }, 5);
            } else {
                frappe.show_alert({
                    message: __('Warning: No stock found for {0} in warehouse {1}', [item_code, warehouse]),
                    indicator: 'red'
                }, 5);
            }
        }
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