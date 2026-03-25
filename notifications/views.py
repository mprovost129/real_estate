from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Notification


def _get_org(request):
    membership = (
        request.user.memberships
        .filter(is_active=True)
        .select_related("organization")
        .first()
    )
    return membership.organization if membership else None


@login_required
def notification_list(request):
    org = _get_org(request)
    notifications = (
        Notification.objects
        .filter(recipient=request.user)
        .select_related("contact", "task")
        .order_by("-created_at")
    )
    unread_count = notifications.filter(is_read=False).count()

    # Filter: all / unread
    show = request.GET.get("show", "all")
    if show == "unread":
        notifications = notifications.filter(is_read=False)

    return render(request, "notifications/list.html", {
        "notifications": notifications[:100],
        "unread_count": unread_count,
        "show": show,
        "org": org,
    })


@login_required
@require_POST
def mark_read(request, pk):
    notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notif.is_read = True
    notif.save(update_fields=["is_read"])

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})

    # If there's a link, follow it
    if notif.link:
        return redirect(notif.link)
    return redirect("notifications:list")


@login_required
@require_POST
def mark_all_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return redirect("notifications:list")


@login_required
@require_POST
def delete_notification(request, pk):
    notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notif.delete()
    return redirect("notifications:list")


@login_required
def unread_count_api(request):
    """Lightweight JSON endpoint for polling the bell count."""
    count = Notification.objects.filter(
        recipient=request.user, is_read=False
    ).count()
    return JsonResponse({"count": count})
