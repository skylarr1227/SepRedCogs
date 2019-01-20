from memento.embeds.mementoembed import MementoEmbedReply


class AlarmReply(MementoEmbedReply):
    def __init__(self, message):
        super(AlarmReply, self).__init__(message=message, title="Reminder!")
