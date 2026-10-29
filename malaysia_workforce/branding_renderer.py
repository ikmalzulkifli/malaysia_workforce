"""Use the installed HRMS template and controller, including its built asset hashes."""

from frappe.website.page_renderers.template_page import TemplatePage

from malaysia_workforce.branding import HEAD_HTML, enabled


class Ocean6HRMSPage(TemplatePage):
	def can_render(self):
		return self.path == "hrms" and enabled() and super().can_render()

	def setup_template_source(self):
		# HRMS is a standalone Vue/Ionic document and does not include Frappe's
		# website head. Extend only its head, keeping the upstream page/controller,
		# authentication, CSRF boot, manifest and compiled bundles authoritative.
		super().setup_template_source()
		self.source = self.source.replace("</head>", HEAD_HTML + "</head>", 1)
