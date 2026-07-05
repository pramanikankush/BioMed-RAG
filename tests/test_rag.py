import unittest
from langchain_core.documents import Document
from rag.hybrid import SparseRetriever, reciprocal_rank_fusion

class TestRAGComponents(unittest.TestCase):
    def setUp(self):
        self.doc1 = Document(page_content="Cancer is a disease of uncontrolled cell division.", metadata={"source": "doc1.txt", "page": 1})
        self.doc2 = Document(page_content="Diploid cancer cells grow slower than aneuploid cells.", metadata={"source": "doc2.txt", "page": 1})
        self.doc3 = Document(page_content="Lymphatic invasion refers to tumors penetrating lymphatic channels.", metadata={"source": "doc3.txt", "page": 1})
        self.documents = [self.doc1, self.doc2, self.doc3]

    def test_sparse_retriever(self):
        retriever = SparseRetriever(self.documents)
        results = retriever.retrieve("cell division", k=2)
        
        self.assertTrue(len(results) > 0)
        # The first document contains "cell division"
        self.assertEqual(results[0][0].metadata["source"], "doc1.txt")

    def test_reciprocal_rank_fusion(self):
        # Doc 1 is ranked 1 in dense, Doc 2 is ranked 2 in dense
        dense = [(self.doc1, 0.9), (self.doc2, 0.7)]
        # Doc 2 is ranked 1 in sparse, Doc 1 is ranked 2 in sparse
        sparse = [(self.doc2, 0.8), (self.doc1, 0.6)]
        
        fused = reciprocal_rank_fusion(dense, sparse, k_rrf=60)
        
        self.assertEqual(len(fused), 2)
        # Scores should be normalized
        self.assertTrue(0.0 <= fused[0][1] <= 1.0)
        self.assertTrue(0.0 <= fused[1][1] <= 1.0)
        
        # Verify both docs are present
        sources = {doc.metadata["source"] for doc, _ in fused}
        self.assertIn("doc1.txt", sources)
        self.assertIn("doc2.txt", sources)
