import collections
from copy import deepcopy
from typing import Callable, Union

class Utils(object):

    @staticmethod
    def recursive_dict_update(d: dict, u: Union[dict, collections.Mapping]) -> dict:
        for k, v, in u.items():
            if isinstance(v, collections.Mapping):
                d[k] = Utils.recursive_dict_update(d.get(k, {}), v)
            else:
                d[k] = v
        return d


    @staticmethod
    async def update_config_keys(field_func: Callable, new_data: dict, update: bool = False):
        """
        This is a very not safe way to update data in the config.
        Gets the existing config value and updates the object, then returns the result.
        With multiple calls running at the same time, it's possible to lose data.
        If you need to safely update the data, consider connecting directly to the DB.

        :param field_func: lambda function which will return the awaitable config Value
        :param new_data: New dictionary to place in the config field
        :param update: Perform a recursive dictionary update rather than an overwrite of each key.
        :return:
        """

        existing_data = await field_func()()  # double call to get the current data

        if update:
            updated_dict = Utils.recursive_dict_update(existing_data, new_data)
        else:
            updated_dict = deepcopy(existing_data)  # type: dict
            for k, v in new_data.items():
                updated_dict[k] = v

        return await field_func().set(updated_dict)

    @staticmethod
    async def delete_config_key(field_func: Callable, key: str):
        existing_data = await field_func()()
        removed_value = existing_data.pop(key, None)
        await field_func().set(existing_data)
        return removed_value

    @staticmethod
    def clean_animated_emoji(emoji_str: str):
        return emoji_str.replace("<a:", "<:", 1)
