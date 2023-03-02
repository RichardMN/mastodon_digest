from __future__ import annotations

import importlib
import inspect
import sys
from abc import ABC, abstractmethod
from math import sqrt
from typing import TYPE_CHECKING
from bs4 import BeautifulSoup

import re

from scipy import stats

from api import get_full_account_name, get_followed_hashtags

if TYPE_CHECKING:
    from models import ScoredPost


class Weight(ABC):
    @classmethod
    @abstractmethod
    def weight(cls, scored_post: ScoredPost):
        pass


class UniformWeight(Weight):
    @classmethod
    def weight(cls, scored_post: ScoredPost) -> UniformWeight:
        return 1


class InverseFollowerWeight(Weight):
    @classmethod
    def weight(cls, scored_post: ScoredPost) -> InverseFollowerWeight:
        # Zero out posts by accounts with zero followers (it happens), or less (count is -1 when the followers count is hidden)
        if scored_post.info["account"]["followers_count"] <= 0:
            weight = 0
        else:
            # inversely weight against how big the account is
            weight = 1 / sqrt(scored_post.info["account"]["followers_count"])

        return weight


class Scorer(ABC):
    @classmethod
    @abstractmethod
    def score(cls, scored_post: ScoredPost):
        pass

    @classmethod
    def get_name(cls):
        return cls.__name__.replace("Scorer", "")


class SimpleScorer(UniformWeight, Scorer):
    @classmethod
    def score(cls, scored_post: ScoredPost) -> SimpleScorer:
        if scored_post.info["reblogs_count"] or scored_post.info["favourites_count"]:
            # If there's at least one metric
            # We don't want zeros in other metrics to multiply that out
            # Inflate every value by 1
            metric_average = stats.gmean(
                [
                    scored_post.info["reblogs_count"] + 1,
                    scored_post.info["favourites_count"] + 1,
                ]
            )
        else:
            metric_average = 0
        return metric_average * super().weight(scored_post)


class SimpleWeightedScorer(InverseFollowerWeight, SimpleScorer):
    @classmethod
    def score(cls, scored_post: ScoredPost) -> SimpleWeightedScorer:
        return super().score(scored_post) * super().weight(scored_post)


class ExtendedSimpleScorer(UniformWeight, Scorer):
    @classmethod
    def score(cls, scored_post: ScoredPost) -> ExtendedSimpleScorer:
        if (
            scored_post.info["reblogs_count"]
            or scored_post.info["favourites_count"]
            or scored_post.info["replies_count"]
        ):
            # If there's at least one metric
            # We don't want zeros in other metrics to multiply that out
            # Inflate every value by 1
            metric_average = stats.gmean(
                [
                    scored_post.info["reblogs_count"] + 1,
                    scored_post.info["favourites_count"] + 1,
                    scored_post.info["replies_count"] + 1,
                ],
            )
        else:
            metric_average = 0
        return metric_average * super().weight(scored_post)


class ExtendedSimpleWeightedScorer(InverseFollowerWeight, ExtendedSimpleScorer):
    @classmethod
    def score(cls, scored_post: ScoredPost) -> ExtendedSimpleWeightedScorer:
        return super().score(scored_post) * super().weight(scored_post)


class ConfiguredScorer(Weight, Scorer):
    @staticmethod
    def get_additional_scorer_pars() -> set:
        # Return a set of parameter names, which modify the behaviour 
        # of a base scorer and require the use of a configured scorer.
        # Add new parameters here to trigger the use of the ConfiguredScorer
        # instead of instanciating a basic scorer directly (see run.py).
        return {"amplify_accounts",}
     
    @classmethod
    def check_params(cls, pars):
        admissible_base_scorers = set(get_scorers()).difference({"Configured"})
        if pars["scorer"] not in admissible_base_scorers:
            sys.exit("Configure scorer '%s' must be one of %s"%admissible_base_scorers)

    # Override class by instance method (I don't know how to solve this better.)
    def get_name(self):
        return "Configured%s"%(self.base_scorer.get_name())

    def score(self, scored_post: ScoredPost) -> ConfiguredScorer:
        s = self.base_scorer.score(scored_post) * self.weight(scored_post)
        return s
    
    def weight(self, scored_post: ScoredPost) -> Weight:
        base_weight = self.base_scorer.weight(scored_post)
        acct = scored_post.info.get("account", {}).get("acct", "")
        acct = get_full_account_name(acct, self.default_host)
        w = base_weight * self.amplify_accounts.get(acct, 1.0)
        return w

    def __init__(self, **pars)->None:
        ConfiguredScorer.check_params(pars)
        self.default_host = pars["default_host"]
        self.base_scorer = get_scorers()[pars["scorer"]]
        self.amplify_accounts = pars.get("amplify_accounts", {})

class FilteredScorer(Weight, Scorer):
    @staticmethod
    def get_additional_scorer_pars() -> set:
        # Return a set of parameter names, which modify the behaviour 
        # of a base scorer and require the use of a configured scorer.
        # Add new parameters here to trigger the use of the ConfiguredScorer
        # instead of instanciating a basic scorer directly (see run.py).
        return {"filtered_accounts","keywords"}
     
    @classmethod
    def check_params(cls, pars):
        admissible_base_scorers = set(get_scorers()).difference({"Filtered"})
        if pars["scorer"] not in admissible_base_scorers:
            sys.exit(f"Configure filtered scorer {pars['scorer']} must be one of {admissible_base_scorers}")

    # Override class by instance method (I don't know how to solve this better.)
    def get_name(self):
        return "Filtered%s"%(self.base_scorer.get_name())

    def score(self, scored_post: ScoredPost) -> FilteredScorer:
        w = self.weight(scored_post)
        if (w < 0):
            s = -1.0
        else:
            acct = scored_post.info.get("account", {}).get("acct", "")
            acct = get_full_account_name(acct, self.default_host)
            s = self.base_scorer.score(scored_post) * w
            if acct in self.filtered_accounts:
                s = s + self.filtered_account_boost
        return s
    
    def is_filtered(self, scored_post: ScoredPost) -> bool:
        acct = scored_post.info.get("account", {}).get("acct", "")
        acct = get_full_account_name(acct, self.default_host)
        if acct in self.filtered_accounts:
            return True
        else:
            return False

    # def is_hashtag_in_text(text, hashtags: list):
    #     #findwords = re.compile(r'(\w*)?')
    #     # words_in_toot = set(re.findall(r"(\w+)",
    #     # "<p>[sorry - test driving my bot on something new]<br>disarmament is an important topic.<br>[I'm trying out code so that <span class=\"h-card\"><a href=\"https://botsin.space/@icymi_adn\" class=\"u-url mention\" rel=\"nofollow noopener noreferrer\" target=\"_blank\">@<span>icymi_adn</span></a></span> can listen to general-purpose accounts but only notice when they use keywords, even if they're not in hashtags.]</p>"))
    #     words_in_toot = set(re.findall(r"(\w+)", text))
    #     print(words_in_toot)
    #     for word in words_in_toot:
    #         if word in hashtags:
    #             print(f"found {word}!")
    #             return True
    #     return False

    def weight(self, scored_post: ScoredPost) -> Weight:
        base_weight = self.base_scorer.weight(scored_post)
        acct = scored_post.info.get("account", {}).get("acct", "")
        acct = get_full_account_name(acct, self.default_host)
        if acct in self.filtered_accounts:
            toot_html = scored_post.info.get("content")
            toot_bs = BeautifulSoup(toot_html, "html.parser")
            toot_text = toot_bs.get_text().lower()
            print(f"testing {toot_text} for matches")
            words_in_toot = set(re.findall(r"(\w+)", toot_text))
            for word in words_in_toot:
                if word in self.keywords:
                    print(f"###FOUND {word}!")
                    return base_weight + 1.0
            return -1.0
        else:
        #w = base_weight * self.filtered_accounts.get(acct, 1.0)
            return base_weight

    def __init__(self, **pars)->None:
        FilteredScorer.check_params(pars)
        self.default_host = pars["default_host"]
        self.base_scorer = get_scorers()[pars["scorer"]]
        self.filtered_accounts = pars.get("filtered_accounts", {})
        self.filtered_account_boost = -0.05
        print (self.filtered_accounts)
        #self.keywords = get_followed_hashtags()
        keywords = pars.get("keywords", {})
        self.keywords = [ word.lower() for word in keywords]
        print( self.keywords )

def get_scorers():
    all_classes = inspect.getmembers(importlib.import_module(__name__), inspect.isclass)
    scorers = [c for c in all_classes if c[1] != Scorer and issubclass(c[1], Scorer)]
    return {scorer[1].get_name(): scorer[1] for scorer in scorers if scorer[1] not in [ConfiguredScorer, FilteredScorer]}
