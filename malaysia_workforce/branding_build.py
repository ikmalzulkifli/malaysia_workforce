"""Build the pinned, runtime-opt-in HRMS identity patch and derived brand sizes."""

import subprocess
from pathlib import Path

import frappe

from malaysia_workforce.branding_assets import build_assets


def after_build():
	hrms_frontend = Path(frappe.get_app_path("hrms")).parent / "frontend"
	script = Path(__file__).with_name("build_hrms.mjs")
	subprocess.run(["node", str(script), str(hrms_frontend)], check=True)
	build_assets(hrms_frontend)
