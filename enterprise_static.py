"""Serve the opt-in business-only frontend from the same origin as its secure API."""
from pathlib import Path
from starlette.exceptions import HTTPException
from fastapi.staticfiles import StaticFiles


class BusinessStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        if path.replace('\\', '/').lstrip('/').split('/')[0] in {'enterprise-api', 'health'}:
            raise HTTPException(404)
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or scope['method'] not in {'GET', 'HEAD'}:
                raise
            return await super().get_response('index.html', scope)


def install_static(app):
    directory = Path(__file__).resolve().parent / 'dist'
    if not (directory / 'index.html').is_file():
        raise RuntimeError('Build the business-only frontend before starting the combined web service')
    app.mount('/', BusinessStaticFiles(directory=directory, html=True))
