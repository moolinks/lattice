"""Agent layer for Lattice.

The paper summarizer is deliberately provider-agnostic:

* with an Anthropic key it runs an LLM summarization prompt over BM25/page
  evidence;
* without a key it runs a deterministic evidence agent that extracts
  claim-bearing sentences and records page-level provenance.

Every run is persisted as a `SummaryRecord`, so a summary is never a
fire-and-forget string with no audit trail.
"""

from .paper_summarizer import PaperSummaryAgent, prompt_version

__all__ = ["PaperSummaryAgent", "prompt_version"]
