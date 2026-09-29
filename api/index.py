"""Vercel entrypoint for the FastAPI application."""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

spec = importlib.util.spec_from_file_location("deal_intel_api", os.path.join(ROOT, "api.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
app = module.app