"""
    flask-simple-crypt
    ------------------

    A Flask extension providing simple, secure encryption and decryption for Python.
    Original work and credit goes to Andrew Cooke, https://github.com/andrewcooke/simple-crypt

    :copyright: (c) 2016 by Carlos Rivas, carlos@twobitcoder.com
                (c) 2012-2015 Andrew Cooke, andrew@acooke.org
                (c) 2013 d10n, https://github.com/d10/ & david@bitinvert.com

    :license: MIT, see LICENSE for more details.

"""

from Crypto.Cipher import AES
from Crypto.Hash import SHA256, HMAC
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Random.random import getrandbits
from Crypto.Util import Counter

__version_info__ = ("0", "2", "0")
__version__ = ".".join(__version_info__)
__author__ = "Carlos Rivas"
__license__ = "BSD"
__copyright__ = "(c) 2016 by Carlos Rivas\n" \
                "(c) 2012-2015 Andrew Cooke\n" \
                "(c) 2013 d10n, https://github.com/d10/\n" \
                "               david@bitinvert.com"
__all__ = ["SimpleCrypt"]


class SimpleCrypt(object):
    def __init__(self, app=None):
        self.AES_KEY_LEN = 256
        self.SALT_LEN = 256
        self.HASH = SHA256
        self.PREFIX = b"fsc"
        self.HEADER = self.PREFIX + b"\x00\x02"
        self.HALF_BLOCK = AES.block_size * 8 // 2
        self.HEADER_LEN = len(self.HEADER)
        self.EXPANSION_COUNT = None
        self.FSC_KEY = None

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        self.EXPANSION_COUNT = app.config.get('FSC_EXPANSION_COUNT', 10000)
        key = app.config.get("SECRET_KEY")
        if not key:
            raise RuntimeError("flask-simple-crypt requires the usage of SECRET_KEY")
        self.FSC_KEY = key

    def encrypt(self, data):
        data = self._str_to_bytes(data)
        self._assert_encrypt_length(data)
        salt = bytes(self._random_bytes(self.SALT_LEN // 8))
        hmac_key, cipher_key = self._expand_keys(self.FSC_KEY, salt, self.EXPANSION_COUNT)
        counter = Counter.new(self.HALF_BLOCK, prefix=salt[:self.HALF_BLOCK // 8])
        cipher = AES.new(cipher_key, AES.MODE_CTR, counter=counter)
        encrypted = cipher.encrypt(data)
        hmac = self._hmac(hmac_key, self.HEADER + salt + encrypted)
        return self.HEADER + salt + encrypted + hmac

    def decrypt(self, data):
        self._assert_not_unicode(data)
        self._assert_header_prefix(data)
        self._assert_decrypt_length(data)
        raw = data[self.HEADER_LEN:]
        salt = raw[:self.SALT_LEN // 8]
        hmac_key, cipher_key = self._expand_keys(self.FSC_KEY, salt, self.EXPANSION_COUNT)
        hmac = raw[-self.HASH.digest_size:]
        hmac2 = self._hmac(hmac_key, data[:-self.HASH.digest_size])
        self._assert_hmac(hmac_key, hmac, hmac2)
        counter = Counter.new(self.HALF_BLOCK, prefix=salt[:self.HALF_BLOCK // 8])
        cipher = AES.new(cipher_key, AES.MODE_CTR, counter=counter)
        return cipher.decrypt(raw[self.SALT_LEN // 8:-self.HASH.digest_size])

    def _assert_not_unicode(self, data):
        u_type = type(b"".decode("utf8"))
        if isinstance(data, u_type):
            raise DecryptionException("Data to decrypt must be bytes; " +
                                      "you cannot use a string because " +
                                      "no string encoding will accept all " +
                                      "possible characters.")

    def _assert_encrypt_length(self, data):
        if len(data) > 2 ** self.HALF_BLOCK:
            raise EncryptionException("Message is too long.")

    def _assert_decrypt_length(self, data):
        if len(data) < self.HEADER_LEN + self.SALT_LEN // 8 + self.HASH.digest_size:
            raise DecryptionException("Missing data.")

    def _assert_header_prefix(self, data):
        if len(data) >= 3 and data[:3] != self.PREFIX:
            raise DecryptionException("Data passed to decrypt were not generated by simple-crypt (bad header).")

    def _assert_hmac(self, key, hmac, hmac2):
        if self._hmac(key, hmac) != self._hmac(key, hmac2):
            raise DecryptionException("Bad password or corrupt / modified data.")

    def _pbkdf2(self, password, salt, n_bytes, count):
        return PBKDF2(password, salt, dkLen=n_bytes,
                      count=count, prf=lambda p, s: HMAC.new(p, s, self.HASH).digest())

    def _expand_keys(self, password, salt, expansion_count):
        if not salt: raise ValueError("Missing salt.")
        if not password: raise ValueError("Missing password.")
        key_len = self.AES_KEY_LEN // 8
        keys = self._pbkdf2(self._str_to_bytes(password), salt, 2 * key_len, expansion_count)
        return keys[:key_len], keys[key_len:]

    def _hide(self, ranbytes):
        return bytearray(self._pbkdf2(bytes(ranbytes), b"", len(ranbytes), 1))

    def _random_bytes(self, n):
        return self._hide(bytearray(getrandbits(8) for _ in range(n)))

    def _hmac(self, key, data):
        return HMAC.new(key, data, self.HASH).digest()

    def _str_to_bytes(self, data):
        u_type = type(b"".decode("utf8"))
        if isinstance(data, u_type):
            return data.encode("utf8")
        return data


class DecryptionException(Exception): pass


class EncryptionException(Exception): pass
