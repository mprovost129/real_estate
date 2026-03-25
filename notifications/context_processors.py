def unread_notifications(request):
    """Inject unread notification count into every template context."""
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0}
    from notifications.models import Notification
    count = Notification.objects.filter(
        recipient=request.user,
        is_read=False,
    ).count()
    return {"unread_notification_count": count}
