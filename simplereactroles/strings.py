from redbot.core.i18n import Translator


_ = Translator("SimpleReactRoles", __file__)


class ErrorStrings(object):

    # Permissions
    perm_not_manage_roles = _("This bot does not have permission to manage roles on the server.")
    perm_not_add_react = _("This bot does not have permission to add reactions in that channel.")

    # Queues
    channel_not_part_of_server = _("The specified channel is not part of a server.")
    queue_exists_f = _("A queue with the name `{}` already exists on the server.")
    queue_not_exists_f = _("queue named `{}` doesn't exist on the server.")
    activate_no_mapped_f = _("There are no mapped reaction/roles for queue `{}`, so it cannot be activated.")

    emoji_bot_no_access_f = _("Reaction {} not accessible by the bot. Is the bot in the server for it?")
    emoji_exists_f = _("Reaction {} already exists for queue `{}`. It is assigned to role `{}`.")
    emoji_not_exists_f = _("Reaction {} does not exist in queue `{}`.")
    emoji_not_found_in_queue = _("Reactions were not not found in the cache/config for that message.")

    message_not_found_f = _("Message with ID `{}` not found in channel `{}`.")

    discord_add_reaction_error = _("Received error while calling Discord add_reaction API. " +
                                   "Check logs for more details.")
    discord_remove_reaction_error = _("Received error while calling Discord remove_reaction API. " +
                                      "Check logs for more details.")
    unknown_error_check_logs = _("Encountered an unknown error. Check logs for more details.")


class SuccessStrings(object):

    # Queues
    queue_created_f = _("Created a queue named `{}`.")
    queue_deleted_f = _("Deleted the queue named `{}`.")
    emoji_added_f = _("Assigned role `{}` to reaction {} in queue `{}`.")
    emoji_deleted_f = _("Deleted reaction {} in queue `{}`. It was assigned to role: `{}`")

    activated_queue_f = _("**Queue Activated:** {}, **Message:** `{}`, **Channel:** `{}`")
    deactivated_queue_f = _("Deactivated reaction roles. **Message:** `{}`, **Channel:** `{}`")


class MiscStrings(object):
    # Permissions check. Not surfaced to the client.
    perm_passed = _("Permissions check passed.")


class DateTimeStrings(object):
    iso = "%Y-%m-%dT%H:%M:%SZ"
