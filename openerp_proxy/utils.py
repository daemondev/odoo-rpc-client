import six
import sys
import json
import functools

__all__ = ('ustr', 'AttrDict', 'wpartial')

# Python 2/3 workaround in raw_input
try:
    xinput = raw_input
except NameError:
    xinput = input


def json_read(file_path):
    """ Read specified json file
    """
    with open(file_path, 'rt') as json_data:
        data = json.load(json_data)
    return data


def json_write(file_path, *args, **kwargs):
    """ Write data to specified json file

        Note, this function uses dumps function to convert data to json first,
        and write only if conversion is successfule. This allows to avoid loss of data
        when rewriting file.
    """
    json_data = json.dumps(*args, **kwargs)

    with open(file_path, 'wt') as json_file:
        json_file.write(json_data)


def wpartial(func, *args, **kwargs):
    """Wrapped partial, same as functools.partial decorator,
       but also calls functools.wrap on its result thus shwing correct
       function name and representation.
    """
    partial = functools.partial(func, *args, **kwargs)

    return functools.wraps(func)(partial)


# Copied from OpenERP source ustr function
def get_encodings(hint_encoding='utf-8'):
    fallbacks = {
        'latin1': 'latin9',
        'iso-8859-1': 'iso8859-15',
        'cp1252': '1252',
    }
    if hint_encoding:
        yield hint_encoding
        if hint_encoding.lower() in fallbacks:
            yield fallbacks[hint_encoding.lower()]

    # some defaults (also taking care of pure ASCII)
    for charset in ['utf8', 'latin1']:
        if not hint_encoding or (charset.lower() != hint_encoding.lower()):
            yield charset

    from locale import getpreferredencoding
    prefenc = getpreferredencoding()
    if prefenc and prefenc.lower() != 'utf-8':
        yield prefenc
        prefenc = fallbacks.get(prefenc.lower())
        if prefenc:
            yield prefenc


def exception_to_unicode(e):
    if hasattr(e, 'args'):
        return "\n".join((ustr(a) for a in e.args))

    try:
        return six.text_type(e)
    except Exception:
        return u"Unknown message"


def ustr(value, hint_encoding='utf-8', errors='strict'):
    """This method is similar to the builtin `unicode`, except
    that it may try multiple encodings to find one that works
    for decoding `value`, and defaults to 'utf-8' first.

    :param: value: the value to convert
    :param: hint_encoding: an optional encoding that was detecte
        upstream and should be tried first to decode ``value``.
    :param str errors: optional `errors` flag to pass to the unicode
        built-in to indicate how illegal character values should be
        treated when converting a string: 'strict', 'ignore' or 'replace'
        (see ``unicode()`` constructor).
        Passing anything other than 'strict' means that the first
        encoding tried will be used, even if it's not the correct
        one to use, so be careful! Ignored if value is not a string/unicode.
    :raise: UnicodeError if value cannot be coerced to unicode
    :return: unicode string representing the given value
    """
    if isinstance(value, Exception):
        return exception_to_unicode(value)

    if isinstance(value, six.text_type):
        return value

    if not isinstance(value, six.string_types):
        try:
            return six.text_type(value)
        except Exception:
            raise UnicodeError('unable to convert %r' % (value,))

    for ln in get_encodings(hint_encoding):
        try:
            return six.text_type(value, ln, errors=errors)
        except Exception:
            pass
    raise UnicodeError('unable to convert %r' % (value,))


class AttrDict(dict):
    """ Simple class to make dictionary able to use attribute get operation
        to get elements it contains using syntax like:

        >>> d = AttrDict(arg1=1, arg2='hello')
        >>> print(d.arg1)
            1
        >>> print(d.arg2)
            hello
        >>> print(d['arg2'])
            hello
        >>> print(d['arg1'])
            1
    """
    def __getattr__(self, name):
        res = None
        try:
            res = super(AttrDict, self).__getitem__(name)
        except KeyError:
            raise AttributeError(name)
        return res

    def __dir__(self):
        return dir(super(AttrDict, self)) + self.keys()
