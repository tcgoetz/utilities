"""Class that encapsilates REST functionality for a single API endpoint."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"

import os
import logging
import json
import enum


class RestException(Exception):
    """Exception caught while making REST calls."""

    def __init__(self, e, error):
        """Create a new instance of the RestException class."""
        self.data = {
            'inner_exception'   : e,
            'error'             : error
        }
        Exception.__init__(self)

    def __repr__(self):
        """Return a string representation of a RestException instance."""
        classname = self.__class__.__name__
        return "<%s() %r>" % (classname, self.data)

    def __str__(self):
        """Return a string representation of a RestException instance."""
        self.__repr__()


class RestCallException(RestException):
    """Exception caught while processing REST responses."""

    def __init__(self, e, url, error):
        """Create a new instance of the RestException class."""
        RestException.__init__(self, e, url, error)
        self.data['url'] = url


class RestResponseException(RestException):
    """Exception caught while processing REST responses."""

    def __init__(self, e, response, error):
        """Create a new instance of the RestException class."""
        RestException.__init__(self, e, error)
        self.data['response'] = response


class RestProtocol(enum.Enum):
    """Enums for the protocols used for REST requests."""

    http    = 'http'
    https   = 'https'


class RestClient(object):
    """Class that encapsilates REST functionality for a single API endpoint."""

    logger = logging.getLogger(__file__)

    agents = {
        'Chrome_Linux'  : 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/1337 Safari/537.36',
        'Firefox_MacOS' : 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:66.0) Gecko/20100101 Firefox/66.0'
    }
    agent = agents['Firefox_MacOS']

    default_headers = {
        'User-Agent'    : agent,
        'Accept'        : 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }

    def __init__(self, session, host, base_route, protocol=RestProtocol.https, port=443):
        """Return a new RestClient instance given a requests session and the base URL of the API."""
        self.session = session
        self.host = host
        self.protocol = protocol
        self.port = port
        self.base_route = base_route

    @classmethod
    def inherit(cls, rest_client, route):
        """Create a new RestClient object from a RestClient object. The new object will handle an API endpoint that is a child of the old RestClient."""
        return RestClient(rest_client.session, rest_client.host, '%s/%s' % (rest_client.base_route, route),
                          protocol=rest_client.protocol, port=rest_client.port)

    def url(self, leaf_route=None):
        """Return the url for the REST endpoint including leaf if supplied."""
        if leaf_route is not None:
            path = '%s/%s' % (self.base_route, leaf_route)
        else:
            path = self.base_route
        if (self.protocol == RestProtocol.https and self.port == 443) or (self.protocol == RestProtocol.http and self.port == 80):
            return '%s://%s/%s' % (self.protocol.name, self.host, path)
        return '%s://%s:%s/%s' % (self.protocol.name, self.host, self.port, path)

    def get(self, leaf_route, aditional_headers={}, params={}):
        """Make a REST API call using the GET method."""
        total_headers = self.default_headers.copy()
        total_headers.update(aditional_headers)
        try:
            response = self.session.get(self.url(leaf_route), headers=total_headers, params=params)
            response.raise_for_status()
        except Exception as e:
            raise RestCallException(e, leaf_route, "GET %s failed (%d): %s" % (response.url, response.status_code, response.text))
        return response

    def post(self, leaf_route, aditional_headers, params, data):
        """Make a REST API call using the POST method."""
        total_headers = self.default_headers.copy()
        total_headers.update(aditional_headers)
        try:
            response = self.session.post(self.url(leaf_route), headers=total_headers, params=params, data=data)
            response.raise_for_status()
        except Exception as e:
            raise RestCallException(e, leaf_route, "POST %s failed (%d): %s" % (response.url, response.status_code, response.text))
        return response

    @classmethod
    def __convert_to_json(cls, object):
        return object.__str__()

    @classmethod
    def save_json_to_file(cls, filename, json_data):
        """Save JSON formatted data to a file."""
        with open(filename, 'w') as file:
            file.write(json.dumps(json_data, default=cls.__convert_to_json))

    def __download_file(self, save_func, leaf_route, filename, overwite, params=None):
        """Download data from a REST API and save it to a file."""
        exists = os.path.isfile(filename)
        if not exists or overwite:
            self.logger.info("%s %s", 'Overwriting' if exists else 'Downloading', filename)
            response = self.get(leaf_route, params=params)
            save_func(filename, response)
        else:
            self.logger.info("Ignoring %s (exists)", filename)

    def ___save_json_to_file(self, filename, response):
        try:
            self.save_json_to_file(filename, response.json())
        except Exception as e:
            raise RestResponseException(e, response, error="failed to save as json: %s (%r)" % (e, response.content))

    def download_json_file(self, leaf_route, filename, overwite=True, params=None):
        """Download JSON formatted data from a REST API and save it to a file."""
        self.__download_file(self.___save_json_to_file, leaf_route, filename + '.json', overwite, params)

    @classmethod
    def save_binary_file(cls, filename, response):
        """Save binary data to a file."""
        try:
            with open(filename, 'wb') as file:
                for chunk in response:
                    file.write(chunk)
        except Exception as e:
            raise RestResponseException(e, response, error="failed to save as binary: %s (%r)" % (e, response.content))

    def download_binary_file(self, leaf_route, filename, overwite=True, params=None):
        """Download binary data from a REST API and save it to a file."""
        self.__download_file(self.save_binary_file, leaf_route, filename, overwite, params)
