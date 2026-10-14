"""Event context is diagnostic/application metadata, never matching evidence."""
from .security import mac


def public_project(project):
    return {**{k: v for k, v in project.items() if k != 'serverKeyHash'},
            'serverKeyConfigured': bool(project.get('serverKeyHash'))}


def server_key_hash(secret, project, key):
    return mac(secret, 'server-key/v1:' + project + ':' + key)


def history(store, project, visitor, at):
    result = dict(visitorFound=False, firstSeenAt=None, previousSeenAt=None)
    if visitor is None:
        return result
    query = dict(project=project, visitorId=visitor, expiresAt={'$gt': at})
    first = store.events.find_one(query, {'createdAt': 1}, sort=[('createdAt', 1), ('_id', 1)], max_time_ms=1000)
    previous = store.events.find_one(query, {'createdAt': 1}, sort=[('createdAt', -1), ('_id', -1)], max_time_ms=1000)
    return dict(visitorFound=first is not None, firstSeenAt=first['createdAt'] if first else at,
                previousSeenAt=previous['createdAt'] if previous else None)
