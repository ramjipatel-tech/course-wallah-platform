from .models import (
    Base, App, Batch, Subject, Folder, Lecture, Video, VideoPart, PDF, 
    Playlist, PlaylistItem, WatermarkProfile, Job, JobStep, JobStatus, 
    PublicationStatus, YouTubeAccount, YouTubeAccountStatus, YouTubeUpload, AdminUser, AuditLog, Setting,
    Student, StudentBatchAccess, StudentActivity
)
from .connection import init_db, get_db_session, get_db_dependency, engine
from .repository import ContentRepository, slugify

# Backward compatibility with root helper/itsgolu imports
try:
    import importlib.util
    from pathlib import Path
    _root_db_file = Path(__file__).resolve().parent.parent.parent / "db.py"
    if _root_db_file.exists():
        _spec = importlib.util.spec_from_file_location("root_db_module", str(_root_db_file))
        _root_db_mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_root_db_mod)
        Database = getattr(_root_db_mod, "Database", None)
        db = getattr(_root_db_mod, "db", None)
except Exception:
    db = None
    Database = None
