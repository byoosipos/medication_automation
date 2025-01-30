frappe.ui.form.on('Patient Encounter', {
    refresh: function(frm) {
        if (!frm.doc.__islocal) {  // Show button as long as it's not a new document
            frm.add_custom_button(__('Create Medication Order'), function() {
                show_medication_order_dialog(frm);
            }, __('Actions'));
            
            // Check if there are any active medication orders
            frappe.db.get_list('Inpatient Medication Order', {
                filters: {
                    'patient_encounter': frm.doc.name,
                    'docstatus': 1,
                    'custom_treatment_status': 'Active'
                },
                limit: 1
            }).then(orders => {
                if (orders && orders.length > 0) {
                    frm.add_custom_button(__('Stop Medication'), function() {
                        show_stop_medication_dialog(frm);
                    }, __('Actions'));
                }
            });
        }
    }
});

function show_medication_order_dialog(frm) {
    if (!frm.doc.drug_prescription || !frm.doc.drug_prescription.length) {
        frappe.msgprint(__('No drugs prescribed in this encounter'));
        return;
    }

    // Prepare fields for each medication
    let fields = [
        {
            fieldname: 'start_date',
            label: __('Default Start Date'),
            fieldtype: 'Date',
            default: frappe.datetime.get_today(),
            reqd: 1
        },
        {
            fieldname: 'start_time',
            label: __('Default Start Time'),
            fieldtype: 'Time',
            default: '09:00:00',
            reqd: 1,
            description: __('First dose will be given at this time, subsequent doses will be spaced evenly')
        },
        {
            fieldname: 'sb1',
            fieldtype: 'Section Break',
            label: __('Individual Medication Schedule')
        }
    ];

    // Add fields for each medication
    frm.doc.drug_prescription.forEach((drug, idx) => {
        if (idx > 0) {
            fields.push({ fieldtype: 'Section Break' });
        }
        
        // Format frequency display
        let frequency_display = '';
        if (drug.dosage) {
            frequency_display = drug.dosage;  // e.g. "1-1-1"
        } else if (drug.interval && drug.interval_uom) {
            frequency_display = `Every ${drug.interval} ${drug.interval_uom}`;
        }
        
        // Format duration display
        let duration_display = '';
        if (drug.days) {
            duration_display = `${drug.days} days`;
        } else if (drug.period) {
            duration_display = drug.period;
        }
        
        fields.push(
            {
                fieldname: `drug_${idx}`,
                fieldtype: 'HTML',
                label: __('Drug Details'),
                options: `
                    <div class="drug-details" style="padding: 10px 0;">
                        <div><strong>${drug.drug_name || drug.drug_code}</strong></div>
                        <div>Dosage Pattern: ${frequency_display || 'Once Daily'}</div>
                        <div>Period: ${drug.period || 'Not specified'}</div>
                        <div>Duration: ${duration_display || 'Not specified'}</div>
                        ${drug.dosage_form ? `<div>Form: ${drug.dosage_form}</div>` : ''}
                        ${drug.comment ? `<div>Instructions: ${drug.comment}</div>` : ''}
                    </div>
                `
            },
            {
                fieldname: `date_${idx}`,
                label: __('Start Date'),
                fieldtype: 'Date',
                default: frappe.datetime.get_today(),
                reqd: 1
            },
            {
                fieldname: `time_${idx}`,
                label: __('First Dose Time'),
                fieldtype: 'Time',
                default: '09:00:00',
                reqd: 1,
                description: __('For pattern 1-1-1, doses will be given every 8 hours starting from this time')
            }
        );
    });

    let d = new frappe.ui.Dialog({
        title: __('Create Medication Order'),
        fields: fields,
        primary_action_label: __('Create'),
        primary_action: function() {
            let values = d.get_values();
            
            // Prepare drug schedules
            let drug_schedules = frm.doc.drug_prescription.map((drug, idx) => {
                return {
                    drug_code: drug.drug_code,
                    start_date: values[`date_${idx}`],
                    start_time: values[`time_${idx}`],
                    dosage: drug.dosage  // Use dosage instead of frequency
                };
            });

            create_medication_order(frm, {
                start_date: values.start_date,
                start_time: values.start_time,
                drug_schedules: drug_schedules
            });
            d.hide();
        }
    });

    // Add button to apply default date/time to all
    d.add_custom_action(__('Apply Default to All'), function() {
        let default_date = d.get_value('start_date');
        let default_time = d.get_value('start_time');
        
        frm.doc.drug_prescription.forEach((drug, idx) => {
            d.set_value(`date_${idx}`, default_date);
            d.set_value(`time_${idx}`, default_time);
        });
    });

    d.show();
}

function create_medication_order(frm, values) {
    frappe.call({
        method: 'medication_automation.automation.create_inpatient_medication_order',
        args: {
            encounter: frm.doc.name,
            start_date: values.start_date,
            start_time: values.start_time,
            drug_schedules: values.drug_schedules
        },
        callback: function(r) {
            if (r.message) {
                frappe.msgprint(__('Inpatient Medication Order {0} created successfully', [r.message]));
            }
        }
    });
}

function show_stop_medication_dialog(frm) {
    let d = new frappe.ui.Dialog({
        title: __('Stop Medication'),
        fields: [
            {
                fieldname: 'stop_reason',
                label: __('Reason for Stopping'),
                fieldtype: 'Small Text',
                reqd: 1
            }
        ],
        primary_action_label: __('Stop'),
        primary_action: function() {
            stop_medication(frm, d.get_value('stop_reason'));
            d.hide();
        }
    });
    d.show();
}

function stop_medication(frm, reason) {
    frappe.call({
        method: 'medication_automation.automation.stop_medication',
        args: {
            encounter: frm.doc.name,
            reason: reason
        },
        callback: function(r) {
            if (r.message) {
                frappe.show_alert({
                    message: __('Medication auto-creation stopped'),
                    indicator: 'red'
                });
                
                // Remove the Stop Medication button
                frm.remove_custom_button(__('Stop Medication'), __('Actions'));
                
                // Refresh the form
                frm.reload_doc();
            }
        }
    });
} 