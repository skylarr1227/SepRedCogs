from collections import defaultdict
from typing import Optional, List, Tuple, Union, Dict

import aiohttp

from .twichobjects import TwitchAuthToken, TwitchStream, TwitchAuthError, TwitchUser


class TwitchApi(object):

    TWITCH_AUTH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
    TWITCH_API_PREFIX = "https://api.twitch.tv/helix"
    STREAMS_PATH = "/streams"
    USERS_PATH = "/users"


    def __init__(self, client_id: str, client_secret: str):
        self.__client_id = client_id
        self.__client_secret = client_secret

        self.__twitch_auth_token = None  # type: Optional[TwitchAuthToken]

    async def __get_new_auth_token(self, client_id: str,
                             client_secret: str,
                             grant_type: str = "client_credentials") -> TwitchAuthToken:

        params = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": grant_type
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url=self.TWITCH_AUTH_TOKEN_URL, params=params) as resp:
                json_response = await resp.json()
                date_header = resp.headers.get('date')

                json_response['date_header'] = date_header

                if not str(resp.status).startswith('2'):
                    raise TwitchAuthError(f"Error generating Auth token with Twitch. Dump: {json_response}")

                return TwitchAuthToken(**json_response)

    def __get_auth_header(self, access_token: str):
        return {
            "Authorization": f"Bearer {access_token}"
        }

    async def _get_access_token(self) -> str:
        token_valid = self.__twitch_auth_token is not None and self.__twitch_auth_token.is_valid

        if not token_valid:
            self.__twitch_auth_token = await self.__get_new_auth_token(client_id=self.__client_id,
                                                                       client_secret=self.__client_secret)
        return self.__twitch_auth_token.access_token

    async def _get_session(self):
        return aiohttp.ClientSession(headers=self.__get_auth_header(await self._get_access_token()))

    async def _sanity_check(self) -> Tuple[bool, Optional[Exception]]:
        try:
            await self._get_access_token()
            return True, None
        except TwitchAuthError as e:
            return False, e

    async def get_user_ids_for_logins(self, username_list: List[str]) -> Dict[str, Optional[str]]:
        map = defaultdict()

        for username in username_list:
            map[username] = None
        username_str = "&login=".join(username_list)
        users = await self.get_users_by_login(username=username_str)

        for user in users:
            map[user.login] = str(user.id)
        return map

    async def get_users_by_login(self, username: str) -> List[TwitchUser]:
        url_suffix = "?login={}".format(username)

        async with await self._get_session() as session:
            async with session.get(self.TWITCH_API_PREFIX + self.USERS_PATH + url_suffix) as resp:
                json_response = await resp.json()

                users = []

                user_data = json_response.get('data', {})
                if not user_data:
                    print(f"Invalid twitch response for Users. Full response: {json_response}")

                for user in user_data:
                    users.append(TwitchUser(**user))
                return users

    async def get_streams_for_multiple(self, user_id_list: List[str]) -> List[TwitchStream]:
        username_str = "&user_id=".join(user_id_list) # really, twitch?
        return await self.get_streams_by_user_id(user_id=username_str)

    async def get_streams_by_user_id(self, user_id: str) -> List[TwitchStream]:
        url_suffix = "?user_id={}".format(user_id) # really, twitch?

        async with await self._get_session() as session:
            async with session.get(self.TWITCH_API_PREFIX + self.STREAMS_PATH + url_suffix) as resp:
                json_response =  await resp.json()

                streams = []

                stream_data = json_response.get('data', {})
                if not stream_data:
                    print(f"Invalid twitch response for Streams. Full response: {json_response}")

                for stream in stream_data:
                    streams.append(TwitchStream(**stream))
                return streams

    async def get_live_stream_by_user_id(self, user_id: str) -> Optional[TwitchStream]:
        for stream in await self.get_streams_by_user_id(user_id):
            if stream.is_live:
                return stream

    async def contains_live_stream(self, streams_list: List[TwitchStream]):
        for stream in streams_list:
            if stream.is_live:
                return True
        return False
