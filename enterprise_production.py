"""Production entry point. Requires explicit HTTPS/SMTP/PostgreSQL configuration."""
from enterprise_preview import create_app as build_workspace
from workspace_runtime import ProductionSettings
import os


def create_app():
    app = build_workspace(production_settings=ProductionSettings.from_env())
    if os.getenv('LOAMY_WORKSPACE_SERVE_DIST') == '1':
        from enterprise_static import install_static
        install_static(app)
    return app
