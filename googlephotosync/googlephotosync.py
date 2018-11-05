import json
import os
from typing import Tuple, List, Optional

import aiohttp
import discord
from cog_shared.seplib.classes.basesepcog import BaseSepCog
from cog_shared.seplib.responses.embeds import ErrorReply
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from httplib2 import Http
from oauth2client.client import OAuth2Credentials
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.commands import Context


class GooglePhotoSync(BaseSepCog, commands.Cog):

    DISCORD_IMG_REQ_HEADERS = {
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:62.0) Gecko/20100101 Firefox/62.0"
    }

    SCOPES = ['https://www.googleapis.com/auth/photoslibrary',
              'https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata',
              'https://www.googleapis.com/auth/photoslibrary.sharing']

    UPLOAD_URL = 'https://photoslibrary.googleapis.com/v1/uploads'

    def __init__(self, bot: Red):
        super(GooglePhotoSync, self).__init__(bot=bot)

        self.watching_channel_cache = {}
        self.photo_library_creds = {}

        self._ensure_futures()

    def _register_config_entities(self, config: Config):
        config.register_global(photo_library_creds={})
        config.register_guild(watching_channels={})

    async def _init_cache(self):
        await self.bot.wait_until_ready()

        photo_library_creds = await self.config.photo_library_creds()
        self.photo_library_creds = photo_library_creds

        guilds = await self.config.all_guilds()

        watching_channels = {}

        for guild_id, guild_dict in guilds.items():
            watching = guild_dict.get("watching_channels")
            if watching is not None:
                watching_channels[str(guild_id)] = watching

        self.watching_channel_cache = watching_channels

    async def _get_upload_session(self):
        cred_json = (await self._get_working_creds()).to_json()
        cred_dict = json.loads(cred_json)
        upload_creds = Credentials.from_authorized_user_info(cred_dict, self.SCOPES)
        return AuthorizedSession(upload_creds)

    async def _get_working_creds(self):
        creds = OAuth2Credentials.from_json(json.dumps(self.photo_library_creds))

        if creds.invalid or creds.access_token_expired:
            creds.refresh(Http())
            await self._update_creds(creds)
        return creds

    async def _update_creds(self, creds: OAuth2Credentials):
        cred_json = creds.to_json()
        json_dict = json.loads(cred_json)

        # update cache of new Credentials
        self.photo_library_creds = json_dict
        # Save it to the database
        await self.config.photo_library_creds.set(json_dict)

    async def _upload_photo_and_get_token(self, session: AuthorizedSession, photo_bytes: bytes):

        session.headers["Content-type"] = "application/octet-stream"
        session.headers["X-Goog-Upload-Protocol"] = "raw"

        upload_response = session.post(self.UPLOAD_URL, data=photo_bytes)
        return upload_response.text

    async def _get_album_id(self, album_name: str) -> str:

        service = await self._get_photo_lib_service()

        album_respone = service.albums().list().execute()
        albums = album_respone.get('albums')
        for album in albums:
            if album_name.lower() == album.get('title', '').lower():
                return album.get('id')

        create_payload = {
            'album': {
                'title': album_name
            }
        }
        create_response = service.albums().create(body=create_payload).execute()

        album_id = create_response.get('id')

        # share the album
        share_payload = {
            'sharedAlbumOptions': {
                'isCollaborative': False,
                'isCommentable': True
            }
        }
        service.albums().share(albumId=album_id, body=share_payload).execute()
        return album_id

    async def _get_photo_lib_service(self):
        creds = await self._get_working_creds()
        return build('photoslibrary', 'v1', http=creds.authorize(Http()))

    async def _add_photo_to_album(self, session: AuthorizedSession, file_name: str, photo_bytes: bytes,
                                  album_name: str):
        album_id = await self._get_album_id(album_name)
        upload_token = await self._upload_photo_and_get_token(session=session, photo_bytes=photo_bytes)

        payload = {
            'albumId': album_id,
            'newMediaItems': [
                {
                    'description': file_name,
                    'simpleMediaItem': {
                        'uploadToken': upload_token
                    }
                }
            ],
        }
        service = await self._get_photo_lib_service()
        service.mediaItems().batchCreate(body=payload).execute()

    @staticmethod
    async def _check_channel_permissions(channel: discord.TextChannel) -> Tuple[bool, str]:
        bot_member = channel.guild.me  # type: discord.Member

        if channel.guild is None:
            response = (False, "Specified channel is not part of the server")
        elif not channel.permissions_for(bot_member).read_messages:
            response = (False, "Bot does not have permissions to read that channel.")
        else:
            response = (True, "Permissions Passed")
        return response

    async def _is_not_guild_and_delete(self, ctx: Context) -> Tuple[bool, str]:
        if ctx.guild is not None and not isinstance(ctx.channel, discord.DMChannel):
            # we're not in a guild. Delete the command message if we can.
            self.logger.warn(f"{ctx.author} Attempted to put Google access keys in a chat channel! "
                             f"Deleting! g:{ctx.guild.id}|c:{ctx.channel.id}")
            await ctx.channel.delete_messages([ctx.message])
            return (False, f"{ctx.author.mention} For security purposes, "
                           f"this command must be run via whisper/DM to me.")
        self.logger.info("Command not executed in a guild. Continuing...")
        return True, ""

    async def _get_guild_watching_channels(self, guild: discord.Guild):
        return await self.config.guild(guild).watching_channels()

    async def _map_channel_to_album(self, channel: discord.TextChannel, album_name: str):
        cur_watching = await self._get_guild_watching_channels(guild=channel.guild)

        cur_watching[str(channel.id)] = album_name

        # update the cache
        if not self.watching_channel_cache.get(str(channel.guild.id)):
            self.watching_channel_cache[str(channel.guild.id)] = {}
        self.watching_channel_cache[str(channel.guild.id)] = cur_watching
        await self.config.guild(channel.guild).watching_channels.set(cur_watching)

    def _get_album_name(self, channel: discord.TextChannel):
        guild_id = str(channel.guild.id)
        channel_id = str(channel.id)

        return self.watching_channel_cache.get(guild_id, {}).get(channel_id)

    @staticmethod
    def _get_message_photo_urls(message: discord.Message) -> Optional[List[str]]:
        attachments = message.attachments  # type: List[discord.Attachment]

        photo_urls = set()

        for attachment in attachments:
            # width and height will be defined if it's an image
            if attachment.height is not None and attachment.width is not None:
                photo_urls.add(attachment.url)
        return list(photo_urls)

    async def _get_message_image(self, url: str):

        async with aiohttp.ClientSession(headers=self.DISCORD_IMG_REQ_HEADERS) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()

    async def on_message(self, message: discord.Message):
        album_name = self._get_album_name(message.channel)
        photo_urls = self._get_message_photo_urls(message)
        if album_name is not None and photo_urls:
            try:
                for url in photo_urls:
                    file_name = os.path.basename(url)
                    # get the image via HTTP
                    photo_data = await self._get_message_image(url)
                    upload_session = await self._get_upload_session()
                    await self._add_photo_to_album(file_name=file_name,
                                                   photo_bytes=photo_data, album_name=album_name,
                                                   session=upload_session)
                await message.add_reaction("✅")
            except (HttpError, Exception) as e:
                self.logger.error(f"Error retrieving image from Discord Server. URL: {photo_url} | Error: {e}")
                return await message.add_reaction("❌")

    @commands.group(name="photosync", invoke_without_command=True)
    @commands.is_owner()
    async def _photosync(self, ctx: Context):
        await ctx.send_help()

    @_photosync.command(name="map")
    @commands.is_owner()
    async def _photosync_map(self, ctx: Context, channel: discord.TextChannel, album_id: str):

        has_permissions, response = await self._check_channel_permissions(channel)

        if not has_permissions:
            return await ErrorReply(response).send(ctx)

        await self._map_channel_to_album(channel, album_id)
        await ctx.tick()
