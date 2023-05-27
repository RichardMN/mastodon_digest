from __future__ import annotations

from typing import TYPE_CHECKING
from bs4 import BeautifulSoup
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
    
    def from_twitter(self) -> float:
        response = 0.0
        # toot_html = self.info.get("content")
        # toot_bs = BeautifulSoup(toot_html, "html.parser")
        # toot_text = toot_bs.get_text().lower()
        toot_html = self.info.get("content")
        toot_bs = BeautifulSoup(toot_html, "html.parser")
        #for tag in toot_bs.find_all('a'):
        for atag in toot_bs.find_all('a', attrs={'class':''}):
            for stub in ['.*nitter', '.*/n.respublicae.eu', '.*/t.co']:
                if re.match(stub, atag['href']):
                    response += 0.4
        # toot_text = self.content_text().lower()
        # #print(f"testing {toot_text} for matches")
        # words_in_toot = set(re.findall(r"(\w+.)", toot_text))
        # for word in words_in_toot:
        #     if word in ['nitter', 'n.respublicae.eu', 'twitter.com', 'RT']:
        #         response += 0.6
        response = min(response, 1.0)
        return response
    
    def matches_keywords(self, keywords: set[str] ) -> bool:
        # toot_html = self.info.get("content")
        # toot_bs = BeautifulSoup(toot_html, "html.parser")
        # toot_text = toot_bs.get_text().lower()
        toot_text = self.content_text().lower()
        #print(f"testing {toot_text} for matches")
        words_in_toot = set(re.findall(r"(\w+)", toot_text))
        return not set.isdisjoint(words_in_toot, keywords)
    
    def count_keywords(self, keywords: set[str]) -> int:
        toot_text = self.content_text().lower()
        words_in_toot = set(re.findall(r"(\w+)", toot_text))
        return len(set.intersection(words_in_toot,keywords))        
    
    def content_text(self) -> str:
        toot_html = self.info.get("content")
        toot_bs = BeautifulSoup(toot_html, "html.parser")
        return toot_bs.get_text()
    
    def link_urls(self) -> list[str]:
        toot_html = self.info.get("content")
        toot_bs = BeautifulSoup(toot_html, "html.parser")
        #for tag in toot_bs.find_all('a'):
        return [atag['href'] for atag in toot_bs.find_all('a', attrs={'class':''})]


