"""Site-opt-in Ocean 6 presentation; never changes users or payroll configuration."""

import frappe

ASSET_ROOT = "/assets/malaysia_workforce"
LOGO = f"{ASSET_ROOT}/images/ocean6/wordmark.png"
ICON = f"{ASSET_ROOT}/images/ocean6/icon.png"
HEAD_HTML = (
	f'<link rel="stylesheet" href="{ASSET_ROOT}/css/ocean6.css?v=20261029">'
	f'<script src="{ASSET_ROOT}/js/ocean6.js?v=20261029" data-ocean6-brand="true"></script>'
)


def enabled() -> bool:
	return frappe.conf.get("ocean6_branding") == 1


def boot_session(bootinfo):
	"""Brand the native navbar through its existing boot settings, per site."""
	if enabled():
		bootinfo.ocean6_branding = True
		bootinfo.navbar_settings.app_logo = LOGO
		for icon in bootinfo.desktop_icons:
			if icon.label == "Malaysia Payroll":
				icon.logo_url = ICON


def update_website_context(context):
	if enabled():
		context.head_html = (context.get("head_html") or "") + HEAD_HTML
		context.logo = LOGO
		context.favicon = ICON
