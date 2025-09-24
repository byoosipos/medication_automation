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
    },
    
    onload: function(frm) {
        if (frm.is_new() && !frm.doc.practitioner) {
            // Only get current practitioner if not already set
            frappe.call({
                method: 'medication_automation.config.autofill.get_current_practitioner',
                callback: function(r) {
                    if (r.message) {
                        frm.set_value('practitioner', r.message.name);
                        // Medical department will be auto-fetched
                    }
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
    // First fetch active medications
    frappe.call({
        method: 'medication_automation.automation.get_active_medications',
        args: {
            encounter: frm.doc.name
        },
        freeze: true,
        freeze_message: __('Fetching active medications...'),
        callback: function(r) {
            if (!r.message || !r.message.length) {
                frappe.msgprint({
                    title: __('No Active Medications'),
                    message: __('There are no active medications that can be stopped for this encounter.'),
                    indicator: 'orange'
                });
                return;
            }

            // Group medications by drug name for better organization
            let medications_by_drug = {};
            r.message.forEach(med => {
                if (!medications_by_drug[med.drug_name]) {
                    medications_by_drug[med.drug_name] = [];
                }
                medications_by_drug[med.drug_name].push(med);
            });

            let fields = [
                {
                    fieldname: 'help_html',
                    fieldtype: 'HTML',
                    options: `
                        <div class="alert alert-info">
                            <p><strong>${__('Instructions')}:</strong></p>
                            <ul>
                                <li>${__('Select the medications you want to stop')}</li>
                                <li>${__('Each checkbox represents a scheduled dose')}</li>
                                <li>${__('You can use Select All/Deselect All buttons for each medication')}</li>
                            </ul>
                        </div>
                    `
                }
            ];

            // Add medications section
            Object.keys(medications_by_drug).forEach(drug_name => {
                // Add section for each drug
                fields.push({
                    fieldname: `section_${drug_name.replace(/[^a-zA-Z0-9]/g, '_')}`,
                    fieldtype: 'Section Break',
                    label: drug_name
                });

                // Add select/deselect buttons for this drug
                fields.push({
                    fieldname: `html_${drug_name.replace(/[^a-zA-Z0-9]/g, '_')}`,
                    fieldtype: 'HTML',
                    options: `
                        <div class="row">
                            <div class="col-sm-12">
                                <button class="btn btn-xs btn-default" 
                                    onclick="cur_dialog.events.select_drug('${drug_name}', true)">
                                    ${__('Select All')}
                                </button>
                                <button class="btn btn-xs btn-default" 
                                    onclick="cur_dialog.events.select_drug('${drug_name}', false)">
                                    ${__('Deselect All')}
                                </button>
                            </div>
                        </div>
                    `
                });

                // Add each scheduled dose
                medications_by_drug[drug_name].forEach(med => {
                    let schedule_time = frappe.datetime.str_to_user(med.date) + 
                                     ' ' + med.time;
                    let label = `${med.dosage || '1'} ${med.dosage_form || ''} ${med.period || 'As Needed'} (${schedule_time})`;
                    if (med.instructions) {
                        label += `<br><small class="text-muted">${med.instructions}</small>`;
                    }
                    
                    fields.push({
                        fieldname: `med_${med.name}`,
                        fieldtype: 'Check',
                        label: label,
                        default: 1,  // Checked by default
                        drug_name: drug_name  // Custom property for select/deselect functionality
                    });
                });
            });

            // Add reason section
            fields.push({
                fieldname: 'reason_section',
                fieldtype: 'Section Break',
                label: __('Stop Reason')
            });

            fields.push({
                fieldname: 'stop_reason',
                label: __('Reason for Stopping'),
                fieldtype: 'Small Text',
                reqd: 1
            });

            let d = new frappe.ui.Dialog({
                title: __('Stop Medications'),
                fields: fields,
                primary_action_label: __('Stop Selected'),
                primary_action: function() {
                    let values = d.get_values();
                    let selected_medications = r.message
                        .filter(med => values[`med_${med.name}`])
                        .map(med => med.name);

                    if (!selected_medications.length) {
                        frappe.msgprint({
                            title: __('Selection Required'),
                            message: __('Please select at least one medication to stop'),
                            indicator: 'red'
                        });
                        return;
                    }

                    // Confirm before stopping
                    let selected_names = r.message
                        .filter(med => values[`med_${med.name}`])
                        .map(med => med.drug_name)
                        .filter((value, index, self) => self.indexOf(value) === index) // unique values
                        .join(', ');

                    frappe.confirm(
                        __('Are you sure you want to stop the following medications: {0}?', [selected_names]),
                        function() {
                            // Yes
                            stop_medication(frm, values.stop_reason, selected_medications);
                            d.hide();
                        }
                    );
                }
            });

            // Add select/deselect all button
            d.add_custom_action(__('Select All'), function() {
                r.message.forEach(med => {
                    d.set_value(`med_${med.name}`, 1);
                });
            });

            d.add_custom_action(__('Deselect All'), function() {
                r.message.forEach(med => {
                    d.set_value(`med_${med.name}`, 0);
                });
            });

            // Add method to select/deselect by drug
            d.events = {
                select_drug: function(drug_name, value) {
                    r.message.forEach(med => {
                        if (med.drug_name === drug_name) {
                            d.set_value(`med_${med.name}`, value ? 1 : 0);
                        }
                    });
                }
            };

            d.show();
        }
    });
}

function stop_medication(frm, reason, medication_entries) {
    if (!medication_entries || !medication_entries.length) {
        frappe.msgprint({
            title: __('Selection Required'),
            message: __('Please select medications to stop'),
            indicator: 'red'
        });
        return;
    }

    frappe.call({
        method: 'medication_automation.automation.stop_medication',
        args: {
            encounter: frm.doc.name,
            reason: reason,
            medication_entries: medication_entries
        },
        freeze: true,
        freeze_message: __('Stopping selected medications...'),
        callback: function(r) {
            if (r.message) {
                frappe.show_alert({
                    message: __('Selected medications stopped successfully'),
                    indicator: 'green'
                });
                
                // Refresh the form to update the UI
                frm.reload_doc();
            }
        }
    });
} 