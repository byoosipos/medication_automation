frappe.ui.form.on('Stock Entry', {
    refresh: function(frm) {
        if (frm.doc.docstatus === 0) {  // Only show for draft entries
            // Add Fetch Medication Orders button
            frm.add_custom_button(__('Fetch Medication Orders'), function() {
                fetch_medication_orders(frm);
            }, __('Actions'));
            
            // Add button to fetch item details if this is a medication requisition
            if (frm.doc.custom_is_medication_requisition && frm.doc.items && frm.doc.items.length) {
                frm.add_custom_button(__('Fetch Item Details'), function() {
                    reload_item_details(frm);
                }, __('Actions'));
            }
        }
    },
    
    onload: function(frm) {
        if (!frm.doc.from_warehouse) {
            frappe.db.get_single_value('Medication Automation Settings', 'default_pharmacy_warehouse')
                .then(warehouse => {
                    if (warehouse) {
                        frm.set_value('from_warehouse', warehouse);
                    }
                });
        }
    },
    
    before_save: function(frm) {
        // Calculate qty_as_per_stock_uom for each item
        frm.doc.items.forEach(function(item) {
            item.qty_as_per_stock_uom = item.qty * item.conversion_factor;
        });
    }
});

// Also handle qty changes at row level
frappe.ui.form.on('Stock Entry Detail', {
    qty: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        row.qty_as_per_stock_uom = row.qty * row.conversion_factor;
        frm.refresh_field('items');
    },
    
    conversion_factor: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        row.qty_as_per_stock_uom = row.qty * row.conversion_factor;
        frm.refresh_field('items');
    }
});

function fetch_medication_orders(frm) {
    if (!frm.doc.posting_date) {
        frappe.msgprint(__('Please set a posting date first'));
        return;
    }

    // If from_warehouse is not set, try to get it from settings
    if (!frm.doc.from_warehouse) {
        frappe.db.get_single_value('Medication Automation Settings', 'default_pharmacy_warehouse')
            .then(warehouse => {
                if (warehouse) {
                    frm.set_value('from_warehouse', warehouse);
                    fetch_orders_with_warehouse(frm, warehouse);
                } else {
                    frappe.msgprint(__('Please set default pharmacy warehouse in Medication Automation Settings'));
                }
            });
    } else {
        fetch_orders_with_warehouse(frm, frm.doc.from_warehouse);
    }
}

function fetch_orders_with_warehouse(frm, warehouse) {
    frappe.call({
        method: 'medication_automation.medication_automation.custom.stock_entry.fetch_medication_orders',
        args: {
            posting_date: frm.doc.posting_date,
            warehouse: warehouse
        },
        callback: function(r) {
            if (r.message) {
                // Show summary before clearing
                let summary = create_order_summary(r.message);
                frappe.msgprint(summary);

                // Clear existing items if any
                frm.clear_table('items');
                
                // Add fetched items to the stock entry
                r.message.forEach(function(item) {
                    let row = frm.add_child('items');
                    row.item_code = item.drug;
                    row.item_name = item.drug_name;
                    row.qty = item.total_qty;
                    row.uom = item.uom;
                    row.stock_uom = item.stock_uom;
                    row.conversion_factor = item.conversion_factor;
                    row.qty_as_per_stock_uom = item.total_qty * item.conversion_factor;
                    row.from_warehouse = warehouse;
                    
                    // Add completion status in description
                    row.description = `Pending Orders: ${item.pending_orders}\n${item.completion_status}`;
                });
                
                frm.refresh();
                frappe.show_alert({
                    message: __('Medication orders fetched successfully'),
                    indicator: 'green'
                });
            }
        }
    });
}

function create_order_summary(medications) {
    let summary = "<h4>Medication Orders Summary</h4><br>";
    summary += "<table class='table table-bordered'>";
    summary += "<tr><th>Medication</th><th>Quantity</th><th>UOM</th><th>Status</th></tr>";
    
    medications.forEach(function(med) {
        summary += `<tr>
            <td>${med.drug_name}</td>
            <td>${med.total_qty}</td>
            <td>${med.uom}</td>
            <td>${med.completion_status}</td>
        </tr>`;
    });
    
    summary += "</table>";
    return summary;
}

function reload_item_details(frm) {
    frappe.show_alert({
        message: __('Fetching item details...'),
        indicator: 'blue'
    });

    let promises = frm.doc.items.map(item => {
        return new Promise((resolve) => {
            frappe.call({
                method: 'medication_automation.medication_automation.custom.stock_entry.fetch_item_details',
                args: {
                    item_code: item.item_code,
                    company: frm.doc.company,
                    from_warehouse: item.from_warehouse,
                    to_warehouse: item.to_warehouse
                },
                callback: function(r) {
                    if (r.message) {
                        let row = locals[item.doctype][item.name];
                        
                        // Update item details
                        Object.assign(row, {
                            item_group: r.message.item_group,
                            description: r.message.description,
                            stock_uom: r.message.stock_uom,
                            transfer_qty: flt(item.qty) * flt(r.message.conversion_factor),
                            conversion_factor: r.message.conversion_factor,
                            basic_rate: r.message.valuation_rate,
                            basic_amount: flt(item.qty) * flt(r.message.valuation_rate),
                            expense_account: r.message.expense_account,
                            cost_center: r.message.cost_center,
                            batch_no: r.message.batch_no,
                            has_batch_no: r.message.has_batch_no,
                            has_serial_no: r.message.has_serial_no
                        });
                    }
                    resolve();
                }
            });
        });
    });

    Promise.all(promises).then(() => {
        frm.refresh_field('items');
        frappe.show_alert({
            message: __('Item details updated successfully'),
            indicator: 'green'
        });
        
        // Trigger item detail calculations
        frm.trigger('calculate_basic_amount');
    });
} 