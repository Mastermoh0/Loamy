"""Location navigation QR codes; never invitations or access credentials."""
import base64
from urllib.parse import urlencode
import qrcode
from qrcode.image.svg import SvgPathFillImage
from fastapi import Depends, HTTPException


def install_location_links(app, db, verified_user, membership, web_origin):
    @app.get('/enterprise-api/businesses/{business_id}/locations/{location_id}/link')
    def location_link(business_id: str, location_id: str, actor=Depends(verified_user)):
        with db() as conn:
            member = membership(conn, business_id, actor)
            if member['role'] != 'owner' and member['location_id'] != location_id:
                raise HTTPException(404, 'Location not found')
            if not conn.execute('SELECT id FROM locations WHERE id=? AND business_id=?', (location_id, business_id)).fetchone():
                raise HTTPException(404, 'Location not found')
        url = web_origin + '/business?' + urlencode({'business': business_id, 'location': location_id})
        qr = qrcode.make(url, image_factory=SvgPathFillImage, border=4)
        return {'url': url, 'qr_data_url': 'data:image/svg+xml;base64,' + base64.b64encode(qr.to_string()).decode()}
