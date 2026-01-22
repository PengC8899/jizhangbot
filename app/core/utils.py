from datetime import datetime
import pytz
from app.core.config import settings

def get_now():
    """Returns current time in configured timezone (default Asia/Shanghai)"""
    tz = pytz.timezone(settings.TIMEZONE)
    return datetime.now(tz)

def to_timezone(dt: datetime):
    """Converts a datetime to configured timezone"""
    if dt is None:
        return None
    tz = pytz.timezone(settings.TIMEZONE)
    if dt.tzinfo is None:
        # Assume UTC if naive, or system local? 
        # Best practice with SQLAlchemy + SQLite: stored as naive (usually UTC or Local).
        # We will assume stored as naive in target timezone if we control insertion.
        # But if we rely on func.now(), it's likely UTC.
        
        # Let's assume input is UTC if naive, then convert.
        # OR just localize it if we know it was created as local time.
        
        # If we insert using get_now(), it is timezone-aware. 
        # SQLAlchemy with SQLite usually drops timezone info and stores string.
        # When retrieving, it comes back as naive.
        # So we treat retrieved naive datetime as "already in target timezone" 
        # IF we consistently insert in target timezone.
        return tz.localize(dt)
    return dt.astimezone(tz)
