import binascii
import os


def random_string(bits=16) -> str:
    return binascii.hexlify(os.urandom(bits)).decode("UTF-8")
