"""Retrieval: directory answers, BM25, vector index and hybrid (RRF) fusion.

`from campuspilot.retrieval import campus_answer` keeps working (the former
campuspilot/retrieval.py now lives in retrieval/directory_answer.py).
"""

from campuspilot.retrieval.directory_answer import campus_answer, response

__all__ = ["campus_answer", "response"]
