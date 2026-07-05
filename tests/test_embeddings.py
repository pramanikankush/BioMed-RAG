import unittest
from unittest.mock import patch, MagicMock
import requests
from rag.engine import HuggingFaceAPIEmbeddings

class TestHuggingFaceAPIEmbeddings(unittest.TestCase):
    def setUp(self):
        self.model_name = "NeuML/pubmedbert-base-embeddings"
        self.api_key = "test_hf_token"
        self.embeddings = HuggingFaceAPIEmbeddings(model_name=self.model_name, api_key=self.api_key)

    @patch('requests.post')
    def test_embed_documents_success(self, mock_post):
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_post.return_value = mock_response

        texts = ["hello", "world"]
        result = self.embeddings.embed_documents(texts)

        self.assertEqual(result, [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        mock_post.assert_called_once_with(
            f"https://router.huggingface.co/hf-inference/models/{self.model_name}",
            headers={"Authorization": "Bearer test_hf_token"},
            json={"inputs": texts, "options": {"wait_for_model": True}},
            timeout=30
        )

    @patch('requests.post')
    def test_embed_query_success(self, mock_post):
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [[0.1, 0.2, 0.3]]
        mock_post.return_value = mock_response

        result = self.embeddings.embed_query("hello")

        self.assertEqual(result, [0.1, 0.2, 0.3])
        mock_post.assert_called_once_with(
            f"https://router.huggingface.co/hf-inference/models/{self.model_name}",
            headers={"Authorization": "Bearer test_hf_token"},
            json={"inputs": ["hello"], "options": {"wait_for_model": True}},
            timeout=30
        )

    @patch('requests.post')
    @patch('time.sleep')
    def test_embed_documents_503_retry(self, mock_sleep, mock_post):
        # Mock a 503 response followed by a 200 response
        mock_response_503 = MagicMock()
        mock_response_503.status_code = 503
        
        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = [[0.1, 0.2, 0.3]]

        mock_post.side_effect = [mock_response_503, mock_response_200]

        result = self.embeddings.embed_documents(["hello"])

        self.assertEqual(result, [[0.1, 0.2, 0.3]])
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once_with(5)

    @patch('requests.post')
    def test_embed_documents_error(self, mock_post):
        # Mock a failed response (e.g., 400 Bad Request)
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        with self.assertRaises(Exception) as context:
            self.embeddings.embed_documents(["hello"])

        self.assertIn("HF API Error (Status 400): Bad Request", str(context.exception))

if __name__ == '__main__':
    unittest.main()
