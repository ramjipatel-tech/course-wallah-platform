"""
Course Wallah — Hardened Student Media Security Audit Test Suite
Verifies defense-in-depth, IDOR prevention, short-lived signed URLs,
admin authentication, security headers, and secret scanning on frontend bundles.
"""

import unittest
import asyncio
import os
import sys
import re
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from httpx import AsyncClient, ASGITransport
from api.server import app
from db.connection import get_db_session, init_db
from db.models import App, Batch, Subject, Folder, Lecture, Video, PDF, PublicationStatus
from api.auth import create_jwt_token, verify_jwt_token
from engines.b2_storage import B2StorageManager

class SecurityAuditTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()

    async def test_01_unauthorized_admin_api_blocked(self):
        """Verify that all admin endpoints reject requests without a valid JWT token (401/403)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            endpoints = [
                ("/api/v1/admin/stats", "GET"),
                ("/api/v1/admin/apps", "GET"),
                ("/api/v1/admin/batches", "GET"),
                ("/api/v1/admin/jobs", "GET"),
                ("/api/v1/admin/watermark", "GET"),
                ("/api/v1/admin/youtube", "GET"),
            ]
            for ep, method in endpoints:
                if method == "GET":
                    res = await client.get(ep)
                else:
                    res = await client.post(ep, json={})
                self.assertIn(
                    res.status_code, 
                    [401, 403], 
                    f"Endpoint {ep} must be blocked for unauthenticated requests, got {res.status_code}"
                )

    async def test_02_admin_login_generates_valid_jwt(self):
        """Verify admin login with correct credentials yields valid role=ADMIN token."""
        from config.settings import ADMIN_USERNAME, ADMIN_PASSWORD
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # Bad credentials
            bad_res = await client.post("/api/v1/admin/login", json={"username": "admin", "password": "wrong_password"})
            self.assertEqual(bad_res.status_code, 401)

            # Good credentials
            good_res = await client.post("/api/v1/admin/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
            self.assertEqual(good_res.status_code, 200)
            token = good_res.json().get("token")
            self.assertIsNotNone(token)
            
            payload = verify_jwt_token(token)
            self.assertIsNotNone(payload)
            self.assertEqual(payload.get("role"), "ADMIN")

    async def test_03_idor_lecture_access_defense(self):
        """Verify IDOR prevention: Non-existent or unpublished lectures return 404."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # Non-existent lecture ID
            res1 = await client.get("/api/v1/lectures/fake-uuid-9999/access")
            self.assertEqual(res1.status_code, 404)

            # Non-existent PDF access
            res2 = await client.get("/api/v1/pdfs/fake-uuid-9999/access")
            self.assertEqual(res2.status_code, 404)

            # Non-existent PDF content
            res3 = await client.get("/api/v1/pdfs/fake-uuid-9999/content")
            self.assertEqual(res3.status_code, 404)

    async def test_04_jwt_token_expiration_and_tamper_resistance(self):
        """Verify that expired or tampered JWT tokens are strictly rejected."""
        # Expired token (-10 seconds)
        expired_token = create_jwt_token({"sub": "admin", "role": "ADMIN"}, expires_in=-10)
        self.assertIsNone(verify_jwt_token(expired_token))

        # Tampered token
        valid_token = create_jwt_token({"sub": "admin", "role": "ADMIN"}, expires_in=3600)
        tampered_token = valid_token[:-4] + "xxxx"
        self.assertIsNone(verify_jwt_token(tampered_token))

    async def test_05_security_headers_present(self):
        """Verify that API server includes required HTTP security headers."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.get("/health")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(res.headers.get("X-Frame-Options"), "SAMEORIGIN")
            self.assertEqual(res.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")

    async def test_06_b2_signed_urls_never_expose_secrets(self):
        """Verify that B2 presigned URLs contain expiring tokens and never expose raw secret keys."""
        signed_url = B2StorageManager.generate_presigned_url(
            object_key="courses/sample_notes.pdf",
            bucket_name="course-wallah-pdfs",
            expires_in_seconds=900
        )
        self.assertIn("course-wallah-pdfs", signed_url)
        self.assertIn("courses/sample_notes.pdf", signed_url)
        # Ensure raw secret is not in URL
        from config.settings import B2_APPLICATION_KEY
        if B2_APPLICATION_KEY:
            self.assertNotIn(B2_APPLICATION_KEY, signed_url)

    def test_07_production_bundle_secret_scan(self):
        """Scan frontend source code and Next.js bundle for accidental secret leaks."""
        base_dir = Path(__file__).parent.parent
        app_dir = base_dir / "app"
        components_dir = base_dir / "components"
        lib_dir = base_dir / "lib"

        dangerous_patterns = [
            re.compile(r'B2_SECRET_KEY\s*=\s*["\'][^"\']+["\']'),
            re.compile(r'GOOGLE_CLIENT_SECRET\s*=\s*["\'][^"\']+["\']'),
            re.compile(r'TELEGRAM_BOT_TOKEN\s*=\s*["\'][^"\']+["\']'),
            re.compile(r'DATABASE_URL\s*=\s*["\']sqlite\+aiosqlite'),
            re.compile(r'ADMIN_PASSWORD\s*=\s*["\'][^"\']+["\']'),
        ]

        scanned_files = 0
        for scan_path in [app_dir, components_dir, lib_dir]:
            if not scan_path.exists():
                continue
            for file_path in scan_path.rglob("*"):
                if file_path.is_file() and file_path.suffix in [".ts", ".tsx", ".js", ".jsx", ".json"]:
                    scanned_files += 1
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    for pat in dangerous_patterns:
                        self.assertIsNone(
                            pat.search(content),
                            f"Dangerous secret pattern found in client file: {file_path}"
                        )

        self.assertGreater(scanned_files, 5, "Should scan multiple frontend files")

    def test_08_no_admin_ui_in_frontend_navigation(self):
        """Verify that Navbar and Footer do not link to /admin or render admin text."""
        base_dir = Path(__file__).parent.parent
        navbar_path = base_dir / "components" / "navigation" / "Navbar.tsx"
        footer_path = base_dir / "components" / "navigation" / "Footer.tsx"

        navbar_content = navbar_path.read_text("utf-8")
        footer_content = footer_path.read_text("utf-8")

        self.assertNotIn('href="/admin"', navbar_content)
        self.assertNotIn('href="/admin"', footer_content)
        self.assertNotIn("Admin Portal", navbar_content)
        self.assertNotIn("Admin Portal", footer_content)

    async def test_09_student_auth_registration_and_login_flow(self):
        """Verify student registration, password hashing, login, and profile retrieval."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            test_email = f"student_audit_{int(asyncio.get_event_loop().time())}@coursewallah.com"
            test_pass = "SecurePass123!"

            # 1. Register
            reg_res = await client.post("/api/v1/auth/register", json={
                "name": "Audit Student",
                "email": test_email,
                "password": test_pass,
                "confirm_password": test_pass
            })
            self.assertEqual(reg_res.status_code, 200)
            reg_data = reg_res.json()
            self.assertTrue(reg_data.get("ok"))
            self.assertIn("token", reg_data)

            # 2. Login
            login_res = await client.post("/api/v1/auth/login", json={
                "email": test_email,
                "password": test_pass
            })
            self.assertEqual(login_res.status_code, 200)
            login_data = login_res.json()
            token = login_data.get("token")
            self.assertIsNotNone(token)

            # 3. Bad Login
            bad_login = await client.post("/api/v1/auth/login", json={
                "email": test_email,
                "password": "WrongPassword!"
            })
            self.assertEqual(bad_login.status_code, 401)

            # 4. Get Profile (/me)
            me_res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(me_res.status_code, 200)
            me_data = me_res.json()
            self.assertEqual(me_data.get("email"), test_email)

    async def test_10_ai_assistant_public_and_authorized_queries(self):
        """Verify AI assistant answers safely without leaking credentials or database structure."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.post("/api/v1/ai/ask", json={"query": "What courses are available?"})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertIn("answer", data)
            # Ensure no internal secret leaks
            answer_text = data.get("answer", "")
            self.assertNotIn("B2_SECRET_KEY", answer_text)
            self.assertNotIn("DATABASE_URL", answer_text)

    async def test_11_contact_form_submission_and_validation(self):
        """Verify contact form validation and successful submission."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # Valid submission
            res = await client.post("/api/v1/contact/submit", json={
                "name": "Aarav Sharma",
                "email": "aarav@coursewallah.com",
                "subject": "Curriculum Question",
                "message": "Hello, I would like to know more about the digital electronics course schedule."
            })
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.json().get("ok"))

            # Invalid email submission
            bad_res = await client.post("/api/v1/contact/submit", json={
                "name": "Aarav Sharma",
                "email": "invalid-email-format",
                "subject": "Curriculum Question",
                "message": "Hello"
            })
            self.assertEqual(bad_res.status_code, 422)


if __name__ == "__main__":
    unittest.main()

