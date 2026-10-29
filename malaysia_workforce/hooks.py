app_name = "malaysia_workforce"
app_title = "Malaysia Payroll"
app_publisher = "Malaysia Workforce contributors"
app_description = "Malaysian payroll and statutory localisation for Frappe HR"
app_license = "GNU General Public License (v3)"
required_apps = ["erpnext", "hrms"]

before_install = "malaysia_workforce.install.before_install"
after_install = "malaysia_workforce.install.after_install"
before_migrate = "malaysia_workforce.install.before_migrate"
after_migrate = "malaysia_workforce.install.after_migrate"

# HRMS' employee payslip endpoint defaults to wkhtmltopdf even when Frappe's
# native Chrome renderer is available.  Use the standard renderer when the
# host provides it, and fall back to Frappe's supported Chrome renderer on
# developer machines and deployments that do not install wkhtmltopdf.
override_whitelisted_methods = {
	"hrms.api._download_pdf": "malaysia_workforce.payroll.pdf.download_salary_slip_pdf",
}

doc_events = {
	"Company": {
		"validate": "malaysia_workforce.payroll.validation.validate_company",
	},
	"Employee": {
		"validate": "malaysia_workforce.payroll.validation.validate_employee",
	},
	"Contract": {
		"validate": "malaysia_workforce.payroll.validation.validate_contract",
	},
	"Salary Component": {
		"validate": "malaysia_workforce.payroll.validation.validate_salary_component",
	},
	"Salary Slip": {
		"validate": "malaysia_workforce.payroll.salary_slip.apply_malaysia_statutory_calculations",
		"before_submit": "malaysia_workforce.payroll.salary_slip.validate_statutory_profile_snapshot",
		"on_submit": "malaysia_workforce.payroll.salary_slip.refresh_cp38_directive_after_submit",
		"before_cancel": "malaysia_workforce.payroll.salary_slip.protect_filed_salary_slip",
	},
	"Payroll Entry": {
		"before_submit": "malaysia_workforce.payroll.events.validate_payroll_release",
	},
}

extend_doctype_class = {
	"Overtime Slip": ["malaysia_workforce.payroll.overtime.MalaysiaOvertimeMixin"],
}

doctype_js = {
	"Payroll Entry": "public/js/payroll_entry.js",
}

permission_query_conditions = {
	"Malaysia Tax Declaration TP1": "malaysia_workforce.permissions.tp1_query",
	"Malaysia Previous Employment TP3": "malaysia_workforce.permissions.tp3_query",
	"Malaysia CP38 Directive": "malaysia_workforce.permissions.cp38_query",
	"Malaysia Statutory Filing": "malaysia_workforce.permissions.filing_query",
}

has_permission = {
	"Malaysia Tax Declaration TP1": "malaysia_workforce.permissions.employee_tax_permission",
	"Malaysia Previous Employment TP3": "malaysia_workforce.permissions.employee_tax_permission",
	"Malaysia CP38 Directive": "malaysia_workforce.permissions.company_permission",
	"Malaysia Statutory Filing": "malaysia_workforce.permissions.company_permission",
}

# Ocean 6 presentation is disabled unless the site sets ocean6_branding to 1.
boot_session = "malaysia_workforce.branding.boot_session"
update_website_context = "malaysia_workforce.branding.update_website_context"
app_include_css = ["/assets/malaysia_workforce/css/ocean6.css?v=20261029-6"]
app_include_js = ["/assets/malaysia_workforce/js/ocean6.js?v=20261029-6"]
page_renderer = [
	"malaysia_workforce.branding_renderer.Ocean6HRManifest",
	"malaysia_workforce.branding_renderer.Ocean6HRMSPage",
]

# Pinned HRMS identity build patch; keeps runtime opt-in and native SW behavior.
after_build = "malaysia_workforce.branding_build.after_build"
