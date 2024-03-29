import asyncio
import hashlib
import logging
from abc import ABC, abstractmethod
from typing import List, Coroutine

from redbot.core import Config
from redbot.core.bot import Red


class BaseSepCog(ABC):

    COG_CONFIG_SALT = "twitch.tv/seputaes"

    def __init__(self, bot: Red):
        self.bot = bot
        cog_name = self.__class__.__name__

        self.config = self._setup_config()

        self.logger = logging.getLogger(f"red.SepRedCogs.{cog_name.lower()}")
        self.logger.setLevel(logging.INFO)

        self._futures = []  # type: List[Coroutine]
        self._futures.append(self._init_cache())

    @abstractmethod
    async def _init_cache(self):
        pass

    def _setup_config(self):
        """
        Generates an awaitable Red configuration object unique to this module.
        :return: awaitable Config
        """
        encoded_bytes = (self.COG_CONFIG_SALT + self.__class__.__name__).encode()
        identifier = int(hashlib.sha512(encoded_bytes).hexdigest(), 16)

        config = Config.get_conf(self, identifier=identifier, force_registration=False)
        self._register_config_entities(config)

        return config

    @abstractmethod
    def _register_config_entities(self, config: Config):
        """
        Register the configuration entities which will be used by the Cog.
        :param config: Config object generated by Config.get_conf()
        :return: None, modifies Config object in place.
        """
        pass

    def _add_future(self, coroutine: Coroutine):
        self._futures.append(coroutine)

    def _ensure_futures(self):
        for coroutine in self._futures:
            asyncio.ensure_future(coroutine)
