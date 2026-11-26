"""Fetch public or LAN site icons without forwarding a user's browser identity."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from html.parser import HTMLParser
import http.client
import ipaddress
import re
import socket
import threading
import time
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

MAX_HTML = 256 * 1024
MAX_IMAGE = 512 * 1024
MAX_REDIRECTS = 3
MAX_CACHE = 32
TIME_BUDGET = 8
_cache = OrderedDict()
_cache_lock = threading.Lock()
_requests = threading.BoundedSemaphore(4)
_dns_slots = threading.BoundedSemaphore(4)
_dns = ThreadPoolExecutor(max_workers=4, thread_name_prefix='favicon-dns')
_metadata = {'metadata', 'instance-data', 'metadata.google.internal', 'metadata.azure.internal'}


def normalize_url(value):
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ValueError('Invalid icon URL')
    value = value.strip()
    if any(ord(c) < 33 or ord(c) == 127 for c in value) or '\\' in value:
        raise ValueError('Invalid icon URL')
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError('Invalid icon URL')
    host = parsed.hostname.rstrip('.').lower()
    if '%' in host or host in _metadata or host == 'localhost' or host.endswith('.localhost'):
        raise ValueError('Unsupported icon host')
    host = host.encode('idna').decode('ascii')
    port = parsed.port
    if port is not None and not 1 <= port <= 65535:
        raise ValueError('Invalid icon port')
    authority = '[' + host + ']' if ':' in host else host
    if port is not None:
        authority += ':' + str(port)
    return urlunsplit((parsed.scheme, authority, quote(parsed.path or '/', safe="/%:@!$&'()*+,;=-._~"),
                       quote(parsed.query, safe="/%?:@!$&'()*+,;=-._~"), ''))


def allowed_address(value):
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    # RFC1918 and ULA are intentionally supported for the user's LAN services.
    return not (address.is_loopback or address.is_link_local or address.is_multicast
                or address.is_unspecified or address.is_reserved
                or str(address) in ('100.100.100.200', '168.63.129.16', 'fd00:ec2::254'))


def remaining(deadline):
    timeout = deadline - time.monotonic()
    if timeout <= 0:
        raise TimeoutError('Icon request timed out')
    return min(3, timeout)


def resolve(host, port, deadline):
    try:
        address = ipaddress.ip_address(host)
        addresses = [str(address)]
    except ValueError:
        if not _dns_slots.acquire(blocking=False):
            raise ValueError('Icon resolver busy')
        pending = _dns.submit(socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM)
        pending.add_done_callback(lambda _: _dns_slots.release())
        try:
            addresses = list(dict.fromkeys(item[4][0] for item in pending.result(timeout=remaining(deadline))))
        except FutureTimeout as exc:
            pending.cancel()
            raise TimeoutError('Icon DNS timed out') from exc
    if not addresses or not all(allowed_address(address) for address in addresses):
        raise ValueError('Unsupported icon address')
    return sorted(addresses, key=lambda address: ipaddress.ip_address(address).version)


def close_socket(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


ICON_ACCEPT = 'text/html,image/png,image/x-icon,image/jpeg,image/webp,image/gif;q=0.9,*/*;q=0.1'


def follow(url, deadline, accept, use):
    """Pin each connection to a checked DNS result, including every redirect, and pass the final response to use()."""
    for hop in range(MAX_REDIRECTS + 1):
        url = normalize_url(url)
        parsed = urlsplit(url)
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        addresses = resolve(parsed.hostname, port, deadline)
        connection = (http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection)(
            parsed.hostname, port, timeout=remaining(deadline))
        # HTTPSConnection still verifies the original hostname and sends its SNI.
        connection._create_connection = lambda _address, timeout, source_address=None: socket.create_connection(
            (addresses[0], port), timeout, source_address)
        timer = None
        try:
            connection.connect()
            sock = connection.sock
            timer = threading.Timer(max(.001, deadline - time.monotonic()), close_socket, args=(sock,))
            timer.daemon = True
            timer.start()
            path = urlunsplit(('', '', parsed.path or '/', parsed.query, ''))
            connection.request('GET', path, headers={'User-Agent': 'Gateway-Icon/1.0', 'Accept': accept,
                               'Accept-Encoding': 'identity', 'Connection': 'close'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location or hop == MAX_REDIRECTS:
                    raise ValueError('Too many icon redirects')
                url = urljoin(url, location)
                continue
            return use(response, sock, url)
        finally:
            if timer:
                timer.cancel()
            connection.close()
    raise ValueError('Icon unavailable')


def read_upto(response, sock, size, deadline):
    """Read at most `size` bytes of a response body."""
    chunks, total = [], 0
    while total < size:
        # read1 avoids waiting for an entire chunk when a peer trickles data.
        timeout = remaining(deadline)
        if sock.fileno() >= 0:
            sock.settimeout(timeout)
        chunk = response.read1(min(65536, size - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b''.join(chunks)


def readable(response):
    return response.status == 200 and response.getheader('Content-Encoding', 'identity').lower() == 'identity'


def fetch(url, limit, deadline):
    def read(response, sock, url):
        if not readable(response):
            raise ValueError('Icon unavailable')
        length = response.getheader('Content-Length')
        if length is not None and int(length) > limit:
            raise ValueError('Icon response too large')
        body = read_upto(response, sock, limit + 1, deadline)
        if len(body) > limit:
            raise ValueError('Icon response too large')
        return body, response.getheader('Content-Type', ''), url
    return follow(url, deadline, ICON_ACCEPT, read)


# A site may forbid other pages from showing it in a frame. The browser then shows an
# empty window, and the page cannot read why, so the gateway reads the headers itself.
DEFAULT_PORTS = {'http': 80, 'https': 443}


def parse_origin(value):
    parsed = urlsplit(value if isinstance(value, str) else '')
    if parsed.scheme not in DEFAULT_PORTS or not parsed.hostname or parsed.path not in ('', '/') or parsed.query:
        raise ValueError('Invalid page origin')
    return parsed.scheme, parsed.hostname.lower(), parsed.port or DEFAULT_PORTS[parsed.scheme]


def source_allows(source, page, resource):
    """Match one frame-ancestors source expression (CSP Level 3) against the page's origin."""
    scheme, host, port = page
    source = source.lower()
    if source == "'self'":
        return page == resource
    if source == '*':
        return True
    if source.endswith(':') and '/' not in source:
        return source[:-1] == scheme or (source == 'http:' and scheme == 'https')
    match = re.fullmatch(r'(?:([a-z][a-z0-9+.-]*)://)?(\*|(?:\*\.)?[a-z0-9.-]+|\[[0-9a-f:.]+\])(?::(\*|\d+))?(?:/.*)?', source)
    if not match:
        return False
    want_scheme, want_host, want_port = match.groups()
    want_scheme = want_scheme or resource[0]
    if not (scheme == want_scheme or (want_scheme == 'http' and scheme == 'https')):
        return False
    if want_host == '*':
        pass
    elif want_host.startswith('*.'):
        if not host.endswith(want_host[1:]):
            return False
    elif host != want_host.strip('[]'):
        return False
    if want_port == '*':
        return True
    expected = int(want_port) if want_port else DEFAULT_PORTS.get(want_scheme)
    return port == expected or (not want_port and want_scheme == 'http' and port == 443)


def frame_verdict(headers, page, resource):
    """Return the header that stops a page at origin `page` from framing `resource`, or ''."""
    policies = [policy for value in headers.get_all('Content-Security-Policy') or [] for policy in value.split(',')]
    ancestors = []
    for policy in policies:
        for directive in policy.split(';'):
            name, _, value = directive.strip().partition(' ')
            if name.lower() == 'frame-ancestors':
                ancestors.append(value.split())
                break
    if ancestors:
        # Browsers ignore X-Frame-Options once frame-ancestors is present; every policy must allow the page.
        allowed = all(sources and "'none'" not in [s.lower() for s in sources] and any(source_allows(s, page, resource) for s in sources)
                      for sources in ancestors)
        return '' if allowed else 'frame-ancestors'
    options = {item.strip().lower() for value in headers.get_all('X-Frame-Options') or [] for item in value.split(',') if item.strip()}
    if 'deny' in options or ('sameorigin' in options and page != resource):
        return 'x-frame-options'
    return ''


# A page may also run only as the top window. A NAS desktop such as UGOS Pro reads its own
# objects from the window above it; in a frame on another origin that read throws and the
# page stays blank. Only these properties of another origin's window can be used.
CROSS_ORIGIN_WINDOW = {'blur', 'close', 'closed', 'focus', 'frames', 'length', 'location', 'opener',
                       'parent', 'postMessage', 'self', 'top', 'window'}
SCRIPT = re.compile(r'<script\b([^>]*)>(.*?)</script\s*>', re.I | re.S)
SCRIPT_TYPE = re.compile(r'\btype\s*=\s*["\']?([^"\'\s>]+)', re.I)
PARENT_READ = re.compile(r'(?<![\w$.])(?:(?:window|self|globalThis)\s*\.\s*)?(?:parent|top)\s*'
                         r'(?:\.\s*([A-Za-z_$][\w$]*)|\[\s*(["\'])([^"\'\\]+)\2\s*\])')


def reads_parent_window(html):
    """Whether an inline script of the page reads a property another origin's window does not expose."""
    for attributes, code in SCRIPT.findall(html):
        kind = SCRIPT_TYPE.search(attributes)
        kind = kind.group(1).lower() if kind else ''
        if re.search(r'\bsrc\s*=', attributes, re.I) or (kind and kind != 'module' and 'javascript' not in kind and 'ecmascript' not in kind):
            continue
        for match in PARENT_READ.finditer(code):
            if (match.group(1) or match.group(3)) not in CROSS_ORIGIN_WINDOW:
                return True
    return False


def frame_check(value, origin):
    """Whether a page at `origin` can show `value` in a frame: True, False, or None when the site cannot be read."""
    page = parse_origin(origin)
    url = normalize_url(value)
    if not _requests.acquire(blocking=False):
        return None, ''
    try:
        deadline = time.monotonic() + TIME_BUDGET

        def verdict(response, sock, final):
            parsed = urlsplit(final)
            resource = parsed.scheme, parsed.hostname.lower(), parsed.port or DEFAULT_PORTS[parsed.scheme]
            reason = frame_verdict(response.headers, page, resource)
            if reason or resource == page or not readable(response) or 'html' not in response.getheader('Content-Type', '').lower():
                return reason
            try:
                html = read_upto(response, sock, MAX_HTML, deadline)
            except (OSError, http.client.HTTPException):
                return ''
            return 'parent-window' if reads_parent_window(html.decode('utf-8', errors='replace')) else ''
        reason = follow(url, deadline, 'text/html,*/*;q=0.8', verdict)
    except (ValueError, OSError, http.client.HTTPException):
        return None, ''
    finally:
        _requests.release()
    return not reason, reason


def image_type(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data.startswith(b'\x00\x00\x01\x00') and len(data) >= 22:
        return 'image/x-icon'
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return 'image/webp'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    return None


class IconLinks(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.links = base, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'base' and attrs.get('href') and not self.links:
            self.base = urljoin(self.base, attrs['href'])
        rel = (attrs.get('rel') or '').lower().split()
        if tag == 'link' and ('icon' in rel or 'apple-touch-icon' in rel) and attrs.get('href'):
            if 'svg' not in (attrs.get('type') or '').lower() and len(self.links) < 5:
                self.links.append(urljoin(self.base, attrs['href']))


def discover(url):
    deadline = time.monotonic() + TIME_BUDGET
    final_url, links = url, []
    try:
        body, content_type, final_url = fetch(url, MAX_HTML, deadline)
        mime = image_type(body)
        if mime:
            return body, mime
        if not content_type or 'html' in content_type.lower():
            parser = IconLinks(final_url)
            parser.feed(body.decode('utf-8', errors='replace'))
            links = parser.links
    except (ValueError, OSError, http.client.HTTPException):
        pass
    origin = urlsplit(final_url)
    links.append(urlunsplit((origin.scheme, origin.netloc, '/favicon.ico', '', '')))
    for candidate in dict.fromkeys(links):
        try:
            body, _, _ = fetch(candidate, MAX_IMAGE, deadline)
            mime = image_type(body)
            if mime:
                return body, mime
        except (ValueError, OSError, http.client.HTTPException):
            continue
    return None


def get_icon(value):
    url = normalize_url(value)
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(url)
        if entry and entry[0] > now:
            _cache.move_to_end(url)
            return entry[1]
        _cache.pop(url, None)
    if not _requests.acquire(blocking=False):
        return None
    try:
        result = discover(url)
    finally:
        _requests.release()
    with _cache_lock:
        _cache[url] = (time.monotonic() + (3600 if result else 60), result)
        _cache.move_to_end(url)
        while len(_cache) > MAX_CACHE:
            _cache.popitem(last=False)
    return result
