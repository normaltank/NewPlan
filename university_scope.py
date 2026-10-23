"""Follow a named roster link within the university, without crawling its peer college."""
from urllib.parse import urlparse

def university_domain(url):
    host=(urlparse(url).hostname or '').lower().rstrip('.')
    labels=host.split('.')
    if host.endswith('.edu.cn') and len(labels)>=3:return '.'.join(labels[-3:])
    if host.endswith('.edu') and len(labels)>=2:return '.'.join(labels[-2:])
    return None

def same_university(home,url):
    domain=university_domain(home);p=urlparse(url)
    try:port=p.port
    except ValueError:return False
    host=(p.hostname or '').lower().rstrip('.')
    return bool(domain and p.scheme in ('http','https') and not(p.username or p.password or port)
                and (host==domain or host.endswith('.'+domain)))
