from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from scipy import stats

import re

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
        delta = 0.0
        match = re.search(r"^Filtered", scorer.get_name())
        if match:
            unfiltered_posts = [ post for post
                in posts if post.is_filtered(scorer)]
            filtered_posts = [ post for post
                in posts if (not post.is_filtered(scorer))]
            eligible_unfiltered_posts = [ post for post in unfiltered_posts if post.get_score(scorer)>=0 ]
            eligible_filtered_posts = [ post for post in filtered_posts if post.get_score(scorer) > 0 ]
            #all_unfiltered_scores =  [p.get_score(scorer) for p in eligible_unfiltered_posts]
            #max_unfiltered_score = max(all_unfiltered_scores)
            eligible_posts = eligible_unfiltered_posts
        else:
            eligible_posts = [ post for post in posts if post.get_score(scorer)>=0 ]
        all_post_scores = [p.get_score(scorer) for p in eligible_posts]
        print(f"all_post_scores (unfiltered only) {all_post_scores}")
        if len(all_post_scores)>0:
            min_score = stats.scoreatpercentile(all_post_scores, per=self.value)
        else:
            min_score = 0.0
        print(f"min_score is {min_score}")
        threshold_posts = [
            post for post, score in zip(eligible_posts, all_post_scores) if score >= min_score
        ]
        if match:
            threshold_posts = threshold_posts + eligible_filtered_posts
        return threshold_posts

def get_thresholds():
    """Returns a dictionary mapping lowercase threshold names to values"""

    return {i.get_name(): i.value for i in Threshold}


def get_threshold_from_name(name: str) -> Threshold:
    """Returns Threshold for a given named string"""

    return Threshold[name.upper()]
