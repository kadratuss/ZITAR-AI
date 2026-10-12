"""Conversation identity follows explicit project selection, never client guessing."""
import hashlib
from assistant_foundation.project_memory import scope, fold


def conversation_session(base, session):
    project = scope(base, session)
    return 'project_'+hashlib.sha256(fold(project).encode()).hexdigest() if project else session
