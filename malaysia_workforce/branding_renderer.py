"""Identity extensions around installed HRMS output; native controller stays authoritative."""

import json

import frappe

from werkzeug.wrappers import Response

from frappe.website.page_renderers.base_renderer import BaseRenderer
from frappe.website.page_renderers.template_page import TemplatePage

from malaysia_workforce.branding import MANIFEST_ROUTE, brand_hrms_head, enabled, hrms_manifest


class Ocean6HRManifest(BaseRenderer):
	def can_render(self):
		return self.path == MANIFEST_ROUTE and enabled()

	def render(self):
		return Response(json.dumps(hrms_manifest()), content_type="application/manifest+json", headers={"Cache-Control": "no-cache"})


class Ocean6HRMSPage(TemplatePage):
	def can_render(self):
		return self.path == "hrms" and enabled() and super().can_render()

	def setup_template_source(self):
		super().setup_template_source()
		self.source = brand_hrms_head(self.source, email_link_login=frappe.get_system_settings("login_with_email_link") == 1)
