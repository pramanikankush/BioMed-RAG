import os
import sys
import unittest
from fastapi.testclient import TestClient

# Ensure workspace root is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, query_rate_limiter, upload_rate_limiter

class TestFastAPIEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        # Clear rate limiters for testing consistency
        query_rate_limiter.history.clear()
        upload_rate_limiter.history.clear()

    def test_root_route(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Bio Medical RAG App", response.text)

    def test_list_chats(self):
        response = self.client.get("/chats")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), dict)

    def test_list_documents(self):
        response = self.client.get("/documents")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_chunks", data)
        self.assertIn("total_files", data)
        self.assertIn("files", data)

    def test_admin_health(self):
        response = self.client.get("/admin/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("vector_db", data)
        self.assertIn("cache", data)
        self.assertIn("diagnostics", data)
