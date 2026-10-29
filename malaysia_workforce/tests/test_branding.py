"""The optional site brand must not leak into another site's presentation."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def brand(monkeypatch):
	frappe = SimpleNamespace(conf={})
	monkeypatch.setitem(sys.modules, "frappe", frappe)
	path = Path(__file__).parents[1] / "branding.py"
	spec = importlib.util.spec_from_file_location("ocean6_branding_test", path)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module, frappe


@pytest.mark.parametrize("setting", [None, 0, "1", False])
def test_branding_requires_explicit_numeric_site_opt_in(brand, setting):
	module, frappe = brand
	frappe.conf["ocean6_branding"] = setting
	boot = SimpleNamespace(navbar_settings=SimpleNamespace(app_logo="original.svg"), desktop_icons=[])
	context = SimpleNamespace(logo="original.svg")
	module.boot_session(boot)
	module.update_website_context(context)
	assert boot.navbar_settings.app_logo == "original.svg"
	assert context.logo == "original.svg"
	assert not hasattr(boot, "ocean6_branding")
	assert not hasattr(context, "head_html")


def test_opted_in_brand_preserves_other_apps_and_website_head(brand):
	module, frappe = brand
	frappe.conf["ocean6_branding"] = 1
	payroll = SimpleNamespace(label="Malaysia Payroll", logo_url="payroll.svg")
	other = SimpleNamespace(label="ERPNext", logo_url="erpnext.svg")
	boot = SimpleNamespace(navbar_settings=SimpleNamespace(app_logo="original.svg"), desktop_icons=[payroll, other])
	context = SimpleNamespace(get=lambda key: '<meta name="existing" content="retained">')
	module.boot_session(boot)
	module.update_website_context(context)
	assert boot.ocean6_branding is True
	assert boot.navbar_settings.app_logo == context.logo == module.LOGO
	assert payroll.logo_url == module.ICON
	assert other.logo_url == "erpnext.svg"
	assert context.head_html.startswith('<meta name="existing" content="retained">')
	assert 'data-ocean6-brand="true"' in context.head_html
	assert context.favicon == module.ICON


def test_auth_templates_wrap_native_controls_only_when_enabled(brand):
	module, frappe = brand
	frappe.conf["ocean6_branding"] = 1
	for page in ("login", "update-password"):
		values = {"template": f"frappe/www/{page}.html", "head_html": "<meta name='kept'>"}
		context = SimpleNamespace(get=values.get)
		module.update_website_context(context)
		assert context.template == f"malaysia_workforce/templates/branding/{page}.html"
		assert context.app_name == "Ocean 6 HR"
		assert context.head_html.startswith("<meta name='kept'>")


def test_hrms_identity_changes_do_not_rewrite_boot_or_legal_content(brand):
	module, _ = brand
	source = '''<html><head><title>Frappe HR</title>
<meta name="apple-mobile-web-app-title" content="Frappe HR">
<meta name="theme-color" content="#fff">
<link rel="manifest" href="/assets/hrms/frontend/manifest.webmanifest">
<link rel="apple-touch-startup-image" href="/assets/hrms/manifest/apple-splash-640-1136.jpg" media="(device-width: 320px)">
<script type="module" src="/assets/hrms/frontend/assets/index-old.js"></script>
</head><body><script>frappe.boot = {{ boot }}</script><p>Frappe HR legal credit</p></body></html>'''
	result = module.brand_hrms_head(source)
	assert "<title>Ocean 6 HR</title>" in result
	assert 'href="/ocean6-hr.webmanifest"' in result
	assert 'splash-640x1136.png' in result
	assert 'media="(device-width: 320px)"' in result
	assert '/assets/hrms/frontend/assets/index-old.js' in result
	assert result.split('</head>', 1)[1] == source.split('</head>', 1)[1]
	assert 'data-ocean6-brand="true"' in result


def test_manifest_keeps_installed_app_identity_scope_and_navigation(brand, tmp_path):
	import json
	module, frappe = brand
	original = {"name":"Frappe HR", "short_name":"Frappe HR", "id":"/hrms", "start_url":"/hrms", "scope":"/assets/hrms/frontend/", "display":"standalone", "lang":"en", "icons":[]}
	path = tmp_path / "manifest.webmanifest"
	path.write_text(json.dumps(original))
	frappe.get_app_path = lambda *args: str(path)
	result = module.hrms_manifest()
	for key in ("id", "scope", "start_url", "display", "lang"):
		assert result[key] == original[key]
	assert result['name'] == result['short_name'] == 'Ocean 6 HR'
	assert all(icon['src'].startswith('/assets/malaysia_workforce/') for icon in result['icons'])
	assert json.loads(path.read_text()) == original


def test_unexpected_hrms_head_fails_instead_of_claiming_partial_branding(brand):
	module, _ = brand
	with pytest.raises(RuntimeError, match="head boundary"):
		module.brand_hrms_head("<body>No standalone head</body>")


@pytest.mark.parametrize("allowed", [False, True])
def test_email_link_is_exposed_to_hrms_only_when_native_setting_allows(brand, allowed):
	module, _ = brand
	result = module.brand_hrms_head("<head></head><body></body>", email_link_login=allowed)
	assert ('data-ocean6-email-link="true"' in result) is allowed
