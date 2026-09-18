from typing import Iterable, Optional
from django.contrib.auth import get_user_model
from .models import CalendarEvent

User = get_user_model()

def create_or_update_from_source(*, source: str, source_object_id: str,
                                 title: str, start, end,
                                 description: str = "", location: str = "",
                                 attendees: Optional[Iterable[User]] = None,
                                 source_label: str = "", color: str = "#16a34a",
                                 empresa_nome: str = "", all_day: bool = False,
                                 created_by: Optional[User] = None) -> CalendarEvent:
    ev, _ = CalendarEvent.objects.update_or_create(
        source=source, source_object_id=source_object_id,
        defaults=dict(
            title=title, start=start, end=end, description=description,
            location=location, source_label=source_label, color=color,
            empresa_nome=empresa_nome, all_day=all_day, created_by=created_by,
        )
    )
    if attendees is not None:
        ev.attendees.set(attendees)
    return ev

def delete_from_source(*, source: str, source_object_id: str) -> int:
    return CalendarEvent.objects.filter(source=source, source_object_id=source_object_id).delete()[0]
