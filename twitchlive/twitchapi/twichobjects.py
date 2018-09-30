import datetime
import time
from typing import List

import pytz


class TwitchAuthToken(object):

    DATE_HEADER_FORMAT = "%a, %d %b %Y %H:%M:%S GMT"

    def __init__(self, access_token: str, expires_in: int, date_header: str, token_type: str):
        self.access_token = access_token
        self.expires_in = expires_in
        self.token_type = token_type

        self.__date_header = date_header

        self.expires_dt = self.__calc_expires_dt(date_header=date_header, expires_in=expires_in)

    def __calc_expires_dt(self, date_header: str, expires_in: int) -> datetime.datetime:
        response_time = datetime.datetime.strptime(date_header, self.DATE_HEADER_FORMAT).replace(tzinfo=pytz.UTC)

        response_epoch = int(time.mktime(response_time.timetuple()))

        expiration_epoch = response_epoch + expires_in

        expiration_dt = datetime.datetime.fromtimestamp(expiration_epoch, tz=pytz.UTC)

        return expiration_dt

    @property
    def is_valid(self, padding=30):

        now_dt = datetime.datetime.utcnow().replace(tzinfo=pytz.UTC)
        padded_dt = (now_dt - datetime.timedelta(seconds=padding))

        return self.expires_dt > padded_dt


class TwitchStream(object):
    def __init__(self, community_ids: List[str], game_id: str, id: str, language: str, started_at: str,
                 thumbnail_url: str, title: str, type: str, user_id: str, viewer_count: int, pagination=None):

        self.community_ids = community_ids
        self.game_id = game_id
        self.id = id
        self.language = language
        self.pagination = pagination
        self.started_at = self.__create_started_dt(started_at)
        self.thumbnail_url = thumbnail_url
        self.title = title
        self.type = type
        self.user_id = user_id
        self.viewer_count = viewer_count

    def __create_started_dt(self, started_at: str):
        return datetime.datetime.strptime(started_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)


    @property
    def is_live(self):
        return self.type == "live"


class TwitchUser(object):
    def __init__(self, broadcaster_type: str, description: str, display_name: str, id: str, login: str,
                 offline_image_url: str, profile_image_url: str, type: str, view_count: int, email=None):

        self.broadcaster_type = broadcaster_type
        self.description = description
        self.display_name = display_name
        self.id = id
        self.login = login
        self.offline_image_url = offline_image_url
        self.profile_image_url = profile_image_url
        self.type = type
        self.view_count = view_count
        self.email = email

class TwitchAuthError(Exception):
    pass