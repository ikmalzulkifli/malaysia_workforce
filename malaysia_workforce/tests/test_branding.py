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
