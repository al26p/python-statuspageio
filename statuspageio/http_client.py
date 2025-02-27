import http.client as http_client
import json
import logging

import requests
from dotmap import DotMap  # type: ignore

from statuspageio.errors import (
    RateLimitError,
    RequestError,
    ResourceError,
    ServerError
)


class HttpClient:
    """
    Wrapper over :module:`requests` that understands StatusPage.io envelope, encoding and decoding schema.
    """

    # Supported REST API version prefix.
    API_VERSION = '/v1'

    def __init__(self, config):
        """
        :param :class:`statuspageio.Configuration` config: StatusPage.io client configuration.
        """
        self.config = config

    def get(self, url, params=None, **kwargs):
        """
        Send a GET request.

        :param str url: Sub URL for the request. You MUST not specify neither base url nor api version prefix.
        :param dict params: (optional) Dictionary of query parameters.
        :param dict **kwargs: (optional) Other parameters which are directly passed to :func:`requests.request`.
        :return: Tuple of three elements: (http status code, headers, response - either parsed json or plain text)
        :rtype: tuple
        """

        return self.request('get', url, params=params, **kwargs)

    def post(self, url, body=None, **kwargs):
        """
        Send a POST request.

        :param str url: Sub URL for the request. You MUST not specify neither base url nor api version prefix.
        :param dict body: (optional) Dictionary of body attributes that will be wrapped with envelope and json encoded.
        :param dict **kwargs: (optional) Other parameters which are directly passed to :func:`requests.request`.
        :return: Tuple of three elements: (http status code, headers, response - either parsed json or plain text)
        :rtype: tuple
        """

        return self.request('post', url, body=body, **kwargs)

    def put(self, url, body=None, **kwargs):
        """
        Send a PUT request.

        :param str url: Sub URL for the request. You MUST not specify neither base url nor api version prefix.
        :param dict body: (optional) Dictionary of body attributes that will be wrapped with envelope and json encoded.
        :param dict **kwargs: (optional) Other parameters which are directly passed to :func:`requests.request`.
        :return: Tuple of three elements: (http status code, headers, response - either parsed json or plain text)
        :rtype: tuple
        """

        return self.request('put', url, body=body, **kwargs)

    def patch(self, url, body=None, **kwargs):
        """
        Send a PATCH request.

        :param str url: Sub URL for the request. You MUST not specify neither base url nor api version prefix.
        :param dict body: (optional) Dictionary of body attributes that will be wrapped with envelope and json encoded.
        :param dict **kwargs: (optional) Other parameters which are directly passed to :func:`requests.request`.
        :return: Tuple of three elements: (http status code, headers, response - either parsed json or plain text)
        :rtype: tuple
        """

        return self.request('patch', url, body=body, **kwargs)

    def delete(self, url, params=None, **kwargs):
        """
        Send a DELETE request.

        :param str url: Sub URL for the request. You MUST not specify neither base url nor api version prefix.
        :param dict params: (optional) Dictionary of query parameters.
        :param dict **kwargs: (optional) Other parameters which are directly passed to :func:`requests.request`.
        :return: Tuple of three elements: (http status code, headers, response - either parsed json or plain text)
        :rtype: tuple
        """

        return self.request('delete', url, params=params, **kwargs)

    def request(self, method, url, params=None, body=None, **kwargs):
        """
        Send an HTTP request.

        The :param:`params` will be properly encoded, as well as :param:`body` which
        will be wrapped with envelope the API expects and json encoded.

        When you get a reponse the method will try to json decode the response,
        if the media type represents json, unwrap the envelope and munchify what has left,
        for JavaScript like access.

        :param str url: Sub URL for the request. You MUST not specify neither base url nor api version prefix.
        :param dict params: (optional) Dictionary of query parameters.
        :param dict body: (optional) Dictionary of body attributes that will be wrapped with envelope and json encoded.
        :param dict **kwargs: (optional) Other parameters which are directly passed to :func:`requests.request`.
        :raises RequestError: if authentication failed, invalid query parameter etc.
        :raises RateLimitError: if rate limit exceeded.
        :raises ResourceError: if requests payload included invalid attributes or were missing.
        :raises ServerError: if StatusPage.io backend servers encounterered an unexpected condition.
        :return: Tuple of three elements: (http status code, headers, response - either parsed json or plain text)
        :rtype: tuple

        :Keyword Arguments:
            * :param dict headers: (optional) Dictionary of headers. Default: ``{}``.
            * :param bool raw: (optional) Whether to wrap and uwrap the envelope. Default: ``False``.
        """

        url = f"{self.config.base_url}{self.API_VERSION}{url}"

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": "OAuth " + self.config.api_key
        }

        user_headers = {}
        if 'headers' in kwargs and isinstance(kwargs['headers'], dict):
            user_headers = kwargs['headers']

        headers.update(user_headers)

        raw = bool(kwargs['raw']) if 'raw' in kwargs else False

        if body is not None:
            headers['Content-Type'] = 'application/json'
            payload = body if raw else self.wrap_envelope(kwargs['container'], body)
            body = json.dumps(payload)

        resp = requests.request(method, url,
                                params=params,
                                data=body,
                                headers=headers,
                                timeout=float(self.config.timeout),
                                verify=self.config.verify_ssl)

        if not 200 <= resp.status_code < 300:
            self.handle_error_response(resp)

        if 'Content-Type' in resp.headers and 'json' in resp.headers['Content-Type']:
            resp_body = DotMap(resp.json()) if raw else self.unwrap_envelope(resp.json())
        else:
            resp_body = resp.content

        return (resp.status_code, resp.headers, resp_body)

    @staticmethod
    def handle_error_response(resp):
        try:
            errors = resp.json()
        except Exception as e:
            raise Exception('Unknown HTTP error response. Json expected. '
                            f'HTTP response code={resp.status_code}. '
                            f'HTTP response body={resp.text}') from e

        resp_code = resp.status_code
        if resp_code == 422:
            raise ResourceError(resp_code, errors)
        if resp_code == 420:
            raise RateLimitError()
        if 400 <= resp_code < 500:
            raise RequestError(resp_code, errors)
        if 500 <= resp_code < 600:
            raise ServerError(resp_code, errors)
        raise Exception('Unknown HTTP error response')

    @staticmethod
    def wrap_envelope(container, body):
        """ Wrap the body with the correct container to match the API """
        return {container: body}

    @staticmethod
    def unwrap_envelope(body):
        return [DotMap(item) for item in body['items']] if 'items' in body else DotMap(body)

    @staticmethod
    def enable_logging():
        http_client.HTTPConnection.debuglevel = 1
        logging.basicConfig()
        logging.getLogger().setLevel(logging.DEBUG)
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True
