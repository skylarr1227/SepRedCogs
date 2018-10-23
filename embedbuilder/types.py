class BaseEmbed(object):
    def __init__(self, description: str, color_str: str):
        self.description = description
        self.color_str = color_str
        self.color = int(color_str, 0)


class BasicEmbed(BaseEmbed):
    def __init__(self, channel_id: int, description: str, color_str: str):
        super(BasicEmbed, self).__init__(description=description, color_str=color_str)
        self.channel_id = channel_id


class ReplaceEmbed(BasicEmbed):
    def __init__(self, channel_id: int, description: str, color_str: str, message_id: int):
        super(ReplaceEmbed, self).__init__(channel_id=channel_id, description=description, color_str=color_str)
        self.message_id = message_id
