from datetime import datetime
from decimal import Decimal
import pytz
from app.core.config import settings

def get_now():
    """Returns current time in configured timezone (default Asia/Shanghai)"""
    tz = pytz.timezone(settings.TIMEZONE)
    return datetime.now(tz)

def format_number(val) -> str:
    """Formats numbers with commas and removes trailing zeros for fractional parts, up to 2 decimal places"""
    if val is None:
        return "0"
    try:
        d = Decimal(str(val))
    except Exception:
        return str(val)
        
    if d == d.to_integral_value():
        return f"{int(d):,}"
    
    # Format to at most 2 decimal places, then remove trailing zeros
    # Use quantize to round to 2 decimal places first
    d_rounded = d.quantize(Decimal('0.01'))
    
    if d_rounded == d_rounded.to_integral_value():
        return f"{int(d_rounded):,}"
        
    return f"{d_rounded:,.2f}".rstrip('0').rstrip('.')

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
