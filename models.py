from __future__ import annotations

from typing import TYPE_CHECKING
import re

if TYPE_CHECKING:
    from scorers import Scorer


class ScoredPost:
    def __init__(self, info: dict):
        self.info = info

    @property
    def url(self) -> str:
        return self.info["url"]

    def get_home_url(self, mastodon_base_url: str) -> str:
        return f"{mastodon_base_url}/@{self.info['account']['acct']}/{self.info['id']}"

    def get_score(self, scorer: Scorer) -> float:
        return scorer.score(self)
    
    def is_filtered(self, scorer: Scorer) -> bool:
        match = re.search(r"^Filtered", scorer.get_name())
        if match:
            return scorer.is_filtered(self)
        else:
            return False

