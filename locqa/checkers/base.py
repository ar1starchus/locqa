from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from locqa.models import ArbFile, Finding, IssueType


class BaseChecker(ABC):
    """Abstract base class for all localization QA checkers."""

    @property
    @abstractmethod
    def issue_type(self) -> IssueType:
        """The issue type this checker is responsible for."""
        pass

    @abstractmethod
    def check(
        self,
        source: ArbFile,
        target: ArbFile,
        context: Dict[str, Any] | None = None,
    ) -> List[Finding]:
        """Execute QA check comparing source ARB and target ARB.
        
        Args:
            source: Source language ARB file (e.g. Russian)
            target: Target language ARB file (e.g. Kazakh, Uzbek)
            context: Optional context containing glossary, thresholds, etc.
            
        Returns:
            List of detected Finding objects.
        """
        pass
