"""Site-opt-in Ocean 6 presentation; no account or payroll configuration changes."""

import json
import re
from pathlib import Path

import frappe

PRODUCT_NAME = "Ocean 6 HR"
ASSET_ROOT = "/assets/malaysia_workforce"
ASSET_VERSION = "20261029-6"
LOGO = f"{ASSET_ROOT}/images/ocean6/wordmark.png"
ICON = f"{ASSET_ROOT}/images/ocean6/icon.png"
PWA_ROOT = f"{ASSET_ROOT}/images/ocean6/pwa"
MANIFEST_ROUTE = "ocean6-hr.webmanifest"
HEAD_HTML = (
	f'<link rel="stylesheet" href="{ASSET_ROOT}/css/ocean6.css?v={ASSET_VERSION}">'
	f'<script src="{ASSET_ROOT}/js/ocean6.js?v={ASSET_VERSION}" data-ocean6-brand="true"></script>'
)


def enabled() -> bool:
	return frappe.conf.get("ocean6_branding") == 1


def boot_session(bootinfo):
	if enabled():
		bootinfo.ocean6_branding = True
		bootinfo.navbar_settings.app_logo = LOGO
		for icon in bootinfo.desktop_icons:
			if icon.label == "Malaysia Payroll":
				icon.logo_url = ICON


def update_website_context(context):
	if not enabled():
		return
	context.head_html = (context.get("head_html") or "") + HEAD_HTML
	context.logo = LOGO
	context.favicon = ICON
	context.app_name = PRODUCT_NAME
	template = context.get("template") or ""
	for page in ("login", "update-password"):
		if template in (f"www/{page}.html", f"frappe/www/{page}.html"):
			context.template = f"malaysia_workforce/templates/branding/{page}.html"


def brand_hrms_head(source: str, *, email_link_login: bool = False) -> str:
	"""Change only identity metadata in the installed standalone HRMS document."""
	head, closing, body = source.partition("</head>")
	if not closing:
		raise RuntimeError("Unsupported HRMS template: missing head boundary")
	head = re.sub(r"<title>[^<]*</title>", f"<title>{PRODUCT_NAME}</title>", head, count=1)

	def identity_tag(match):
		tag = match.group(0)
		attributes = dict(re.findall(r'''([\w-]+)\s*=\s*["'](.*?)["']''', tag, re.S))
		if attributes.get("name") == "apple-mobile-web-app-title":
			return f'<meta name="apple-mobile-web-app-title" content="{PRODUCT_NAME}">'
		if attributes.get("name") == "theme-color":
			return '<meta name="theme-color" content="#c51f2a">'
		if attributes.get("rel") == "manifest":
			return f'<link rel="manifest" href="/{MANIFEST_ROUTE}">'
		if attributes.get("rel") in ("icon", "apple-touch-icon"):
			return f'<link rel="{attributes["rel"]}" type="image/png" sizes="192x192" href="{PWA_ROOT}/icon-192.png">'
		if attributes.get("rel") == "apple-touch-startup-image":
			old = attributes.get("href", "")
			size = re.search(r"apple-splash-(\d+)-(\d+)\.jpg$", old)
			if not size:
				raise RuntimeError("Unsupported HRMS splash asset")
			return tag.replace(old, f"{PWA_ROOT}/splash-{size[1]}x{size[2]}.png")
		return tag

	head = re.sub(r"<(?:meta|link)\b[^>]*>", identity_tag, head)
	includes = HEAD_HTML
	if email_link_login:
		includes = includes.replace('data-ocean6-brand="true"', 'data-ocean6-brand="true" data-ocean6-email-link="true"')
	return head + includes + closing + body


def hrms_manifest() -> dict:
	"""Keep native start URL, ID semantics, scope and display; replace identity only."""
	path = Path(frappe.get_app_path("hrms", "public", "frontend", "manifest.webmanifest"))
	manifest = json.loads(path.read_text())
	manifest.update(
		name=PRODUCT_NAME,
		short_name=PRODUCT_NAME,
		description="Ocean 6 employee self-service",
		theme_color="#c51f2a",
		background_color="#f2f0ea",
		icons=[
			{"src": f"{PWA_ROOT}/icon-{size}.png", "sizes": f"{size}x{size}", "type": "image/png", "purpose": "any"}
			for size in (192, 512)
		],
	)
	return manifest
