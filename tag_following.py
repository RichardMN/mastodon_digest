# Local extension of the Mastodon class so that we can
# access the list of followed hashtags
#

import mastodon

class Mastodon(mastodon.Mastodon):
    # Copied from https://github.com/halcy/Mastodon.py/issues/309
    # Code by @BackSeat (Keith Edmunds)
    #@api_version("4.0.0", "4.0.0", _DICT_VERSION_ACCOUNT)
    def tag_following(self , max_id=None, min_id=None, since_id=None, limit=None):
        """
        Fetch tags the given user is following.

        Returns a list of tags dicts
        """
        if max_id is not None:
            max_id = self.__unpack_id(max_id, dateconv=True)

        if min_id is not None:
            min_id = self.__unpack_id(min_id, dateconv=True)

        if since_id is not None:
            since_id = self.__unpack_id(since_id, dateconv=True)

        params = self.__generate_params(locals(), ['id'])
        url = '/api/v1/followed_tags'
        return self.__api_request('GET', url, params)
