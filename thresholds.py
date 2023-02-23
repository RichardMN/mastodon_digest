from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from scipy import stats

if TYPE_CHECKING:
    from models import ScoredPost
    from scorers import Scorer


class Threshold(Enum):
    LAX = 90
    NORMAL = 95
    STRICT = 98

    def get_name(self):
        return self.name.lower()

    def posts_meeting_criteria(
        self, posts: list[ScoredPost], scorer: Scorer
    ) -> list[ScoredPost]:
        """Returns a list of ScoredPosts that meet this Threshold with the given Scorer"""
        # If we are using a FilteredScorer, split the list between the filtered
        # accounts and the unfiltered accounts, and treat them separately
        match = re.search(r"^Filtered", scorer.get_name())
        if match:
        
        else:
            eligible_posts = [ post for post in posts if post.get_score(scorer)>=0 ]
        all_post_scores = [p.get_score(scorer) for p in eligible_posts]
        print(f"all_post_scores {all_post_scores}")
        min_score = max(stats.scoreatpercentile(all_post_scores, per=self.value),
            delta)
        print(f"min_score is {min_score}")
        threshold_posts = [
            post for post, score in zip(eligible_posts, all_post_scores) if score >= min_score
        ]
        return threshold_posts


def get_thresholds():
    """Returns a dictionary mapping lowercase threshold names to values"""

    return {i.get_name(): i.value for i in Threshold}


def get_threshold_from_name(name: str) -> Threshold:
    """Returns Threshold for a given named string"""

    return Threshold[name.upper()]
