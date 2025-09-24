frappe.ui.form.on('Lab Test', {
    refresh: function(frm) {
        frm.doc.custom_consumables = frm.doc.custom_consumables || [];
        
        // Set default warehouse for new consumable rows
        frm.fields_dict.custom_consumables.grid.add_custom_button(__('Set Default Warehouse'), function() {
            frm.doc.custom_consumables.forEach((row) => {
                if (!row.warehouse) {
                    frappe.call({
                        method: 'medication_automation.medication_automation.doctype.lab_consumables.lab_consumables.get_default_warehouse',
                        args: { 
                            doctype: frm.doctype 
                        },
                        callback: function(r) {
                            if (r.message) {
                                frappe.model.set_value(row.doctype, row.name, 'warehouse', r.message);
                            }
                        }
                    });
                }
            });
        });
        
        // Simpler approach - use the form render of the child table
        frm.warehouse_for_lab_test = null;
        
        // Pre-fetch the warehouse value
        frappe.call({
            method: 'medication_automation.medication_automation.doctype.lab_consumables.lab_consumables.get_default_warehouse',
            args: { doctype: "Lab Test" },
            callback: function(r) {
                if (r.message) {
                    frm.warehouse_for_lab_test = r.message;
                }
            }
        });
    }
});

frappe.ui.form.on('Lab Consumables', {
    form_render: function(frm, cdt, cdn) {
        // Get the parent doctype
        const row = frappe.get_doc(cdt, cdn);
        if (row.parenttype === "Lab Test" && !row.warehouse && frm.warehouse_for_lab_test) {
            frappe.model.set_value(cdt, cdn, 'warehouse', frm.warehouse_for_lab_test);
        }
    },
    
    custom_consumables_add: function(frm, cdt, cdn) {
        const row = frappe.get_doc(cdt, cdn);
        if (!row.warehouse && frm.warehouse_for_lab_test) {
            frappe.model.set_value(cdt, cdn, 'warehouse', frm.warehouse_for_lab_test);
        }
    }
}); 