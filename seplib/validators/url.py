import collections
from urllib.parse import urlparse


def is_valid_url(url: str, has_protocol=True, allowed_protocols: collections.Iterable = ('http', 'https')) -> bool:
    try:
        parsed_url = urlparse(url)
        if has_protocol:
            if parsed_url.scheme is None or parsed_url.scheme not in allowed_protocols:
                return False
        return True
    except Exception:
        return False
