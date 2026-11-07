"""Real HTTP/session/database checks, using a temporary SQLite database only."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from fastapi.testclient import TestClient
from enterprise_preview import COOKIE, create_app


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.test_root = Path(__file__).resolve().parent / '.local-data' / 'tests'
        self.test_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.test_root)
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.env = patch.dict(os.environ, {"LOAMY_LOCAL_PREVIEW": "1"})
        self.env.start()
        self.app = create_app(self.path)
        self.owner = self.client()

    def tearDown(self):
        self.assertTrue(Path(self.temp.name).resolve().is_relative_to(self.test_root))
        self.temp.cleanup()
        self.env.stop()

    def client(self):
        return TestClient(self.app, headers={"Origin": "http://testserver"})

    def register(self, client, email):
        response = client.post("/enterprise-api/register", json={"email": email, "name": "Test Person", "password": "Test-password-42"})
        self.assertEqual(response.status_code, 201, response.text)
        token = client.get('/enterprise-api/email/inbox').json()['messages'][0]['verification_url'].split('#verify=')[1]
        self.assertEqual(client.post('/enterprise-api/email/verify', json={'token': token}).status_code, 200)
        return response.json()["user"]

    def business(self, client, name="Palm House"):
        response = client.post("/enterprise-api/businesses", json={"name": name, "location_name": "Lekki", "address": "1 Test Road"})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def test_authenticated_persistent_setup_and_logout(self):
        self.assertEqual(self.owner.get("/enterprise-api/me").status_code, 401)
        self.register(self.owner, "owner@example.test")
        bid = self.business(self.owner)
        response = self.owner.post(f"/enterprise-api/businesses/{bid}/locations", json={"name": "Ikeja", "address": "2 Test Road"})
        self.assertEqual(response.status_code, 201)
        # A new app instance reads persisted business records using a persisted session.
        other = TestClient(create_app(self.path), headers={"Origin": "http://testserver"})
        other.cookies.update(self.owner.cookies)
        detail = other.get(f"/enterprise-api/businesses/{bid}").json()
        self.assertEqual(len(detail["locations"]), 2)
        self.assertEqual(len(detail["events"]), 2)
        token = self.owner.cookies.get(COOKIE)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            hashes = str(conn.execute("SELECT password_hash FROM users").fetchall())
            sessions = str(conn.execute("SELECT token_hash FROM sessions").fetchall())
        self.assertNotIn("Test-password-42", hashes)
        self.assertNotIn(token, sessions)
        self.assertEqual(self.owner.post("/enterprise-api/logout").status_code, 200)
        self.assertEqual(other.get("/enterprise-api/me").status_code, 401)
        self.assertEqual(self.owner.post("/enterprise-api/login", json={"email": "owner@example.test", "password": "Test-password-42"}).status_code, 200)

    def test_cross_business_and_location_scope(self):
        self.register(self.owner, "owner@example.test")
        bid = self.business(self.owner)
        outsider = self.client()
        self.register(outsider, "outside@example.test")
        self.assertEqual(outsider.get(f"/enterprise-api/businesses/{bid}").status_code, 404)
        self.assertEqual(outsider.post(f"/enterprise-api/businesses/{bid}/locations", json={"name": "Hidden", "address": "Hidden"}).status_code, 404)
        other_bid = self.business(outsider, "Other Business")
        foreign_lid = outsider.get(f"/enterprise-api/businesses/{other_bid}").json()["locations"][0]["id"]
        response = self.owner.post(f"/enterprise-api/businesses/{bid}/invitations", json={"email": "staff@example.test", "role": "staff", "location_id": foreign_lid})
        self.assertEqual(response.status_code, 400)

    def test_invitation_role_enforcement_replay_and_revocation(self):
        self.register(self.owner, "owner@example.test")
        bid = self.business(self.owner)
        lid = self.owner.get(f"/enterprise-api/businesses/{bid}").json()["locations"][0]["id"]
        self.owner.post(f"/enterprise-api/businesses/{bid}/locations", json={"name": "Second", "address": "Second address"})
        staff = self.client()
        self.register(staff, "staff@example.test")
        wrong = self.client()
        self.register(wrong, "wrong@example.test")
        for role in ("manager", "finance", "front_desk", "staff"):
            with self.subTest(role=role):
                invitation = self.owner.post(f"/enterprise-api/businesses/{bid}/invitations", json={"email": "staff@example.test", "role": role, "location_id": lid})
                self.assertEqual(invitation.status_code, 201, invitation.text)
                token = invitation.json()["token"]
                self.assertEqual(wrong.post("/enterprise-api/invitations/accept", json={"token": token}).status_code, 403)
                self.assertEqual(staff.post("/enterprise-api/invitations/accept", json={"token": token}).status_code, 200)
                self.assertEqual(staff.post("/enterprise-api/invitations/accept", json={"token": token}).status_code, 404)
                detail = staff.get(f"/enterprise-api/businesses/{bid}").json()
                self.assertEqual(detail["role"], role)
                self.assertEqual([row["id"] for row in detail["locations"]], [lid])
                self.assertEqual(detail["team"], [])
                self.assertEqual(detail["events"], [])
                self.assertEqual(staff.post(f"/enterprise-api/businesses/{bid}/locations", json={"name": "Denied", "address": "Denied"}).status_code, 403)
                self.assertEqual(staff.post(f"/enterprise-api/businesses/{bid}/invitations", json={"email": "wrong@example.test", "role": "staff", "location_id": lid}).status_code, 403)
                owner_view = self.owner.get(f"/enterprise-api/businesses/{bid}").json()
                member = next(m for m in owner_view["team"] if m["email"] == "staff@example.test")
                self.assertEqual(self.owner.delete(f"/enterprise-api/businesses/{bid}/members/{member['id']}").status_code, 200)
                self.assertEqual(staff.get(f"/enterprise-api/businesses/{bid}").status_code, 404)

    def test_validation_expiry_and_cross_origin(self):
        self.assertEqual(self.owner.post("/enterprise-api/register", json={"email": "invalid", "name": "Test", "password": "short"}).status_code, 422)
        self.register(self.owner, "owner@example.test")
        bid = self.business(self.owner)
        lid = self.owner.get(f"/enterprise-api/businesses/{bid}").json()["locations"][0]["id"]
        self.assertEqual(self.owner.post(f"/enterprise-api/businesses/{bid}/invitations", json={"email": "staff@example.test", "role": "owner", "location_id": lid}).status_code, 422)
        self.assertEqual(self.owner.post(f"/enterprise-api/businesses/{bid}/locations", json={"name": "Lekki", "address": "Duplicate"}).status_code, 409)
        owner_id = self.owner.get(f"/enterprise-api/businesses/{bid}").json()["team"][0]["id"]
        self.assertEqual(self.owner.delete(f"/enterprise-api/businesses/{bid}/members/{owner_id}").status_code, 400)
        self.assertEqual(self.owner.post("/enterprise-api/businesses", headers={"Origin": "https://untrusted.test"}, json={"name": "Bad", "location_name": "Bad", "address": "Bad"}).status_code, 403)
        self.assertEqual(self.owner.get("/enterprise-api/me", headers={"Host": "attacker.test"}).status_code, 403)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("UPDATE sessions SET expires_at=0")
        self.assertEqual(self.owner.get("/enterprise-api/me").status_code, 401)

    def test_invitation_expiry_and_replaced_link(self):
        self.register(self.owner, "owner@example.test")
        bid = self.business(self.owner)
        lid = self.owner.get(f"/enterprise-api/businesses/{bid}").json()["locations"][0]["id"]
        staff = self.client()
        self.register(staff, "staff@example.test")
        payload = {"email": "staff@example.test", "role": "staff", "location_id": lid}
        first = self.owner.post(f"/enterprise-api/businesses/{bid}/invitations", json=payload).json()["token"]
        second = self.owner.post(f"/enterprise-api/businesses/{bid}/invitations", json=payload).json()["token"]
        self.assertEqual(staff.post("/enterprise-api/invitations/accept", json={"token": first}).status_code, 404)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("UPDATE invitations SET expires_at=0")
        self.assertEqual(staff.post("/enterprise-api/invitations/accept", json={"token": second}).status_code, 404)

    def test_preview_disabled_by_default(self):
        with patch.dict(os.environ, {"LOAMY_LOCAL_PREVIEW": "0"}):
            with self.assertRaises(RuntimeError):
                create_app(self.path)


if __name__ == "__main__":
    unittest.main()
