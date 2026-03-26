from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from compliance.audit import log_audit_event
from organizations.models import Membership
from organizations.permissions import OrgRoleRequiredMixin, require_org_role
from organizations.utils import get_active_membership
from .forms import TaskCompleteForm, TaskForm, TaskSnoozeForm
from .models import Task


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _get_org(request):
    membership = get_active_membership(request)
    return membership.organization if membership else None


class OrgMixin(LoginRequiredMixin):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        membership = get_active_membership(request)
        self.org = membership.organization if membership else None
        self.membership = membership

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["org"] = self.org
        return ctx


# ------------------------------------------------------------------ #
# Task list
# ------------------------------------------------------------------ #

class TaskListView(OrgMixin, ListView):
    template_name = "tasks/list.html"
    context_object_name = "tasks"
    paginate_by = 25

    def get_queryset(self):
        org = self.org
        today = timezone.localdate()
        qs = (
            Task.objects.for_org(org)
            .select_related("assigned_to", "contact", "deal")
            .order_by("due_date", "due_time", "-priority")
        )

        tab = self.request.GET.get("tab", "today")
        if tab == "today":
            qs = qs.filter(
                due_date=today,
                status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
            )
        elif tab == "overdue":
            qs = qs.filter(
                due_date__lt=today,
                status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
            )
        elif tab == "upcoming":
            qs = qs.filter(
                due_date__gt=today,
                status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
            )
        elif tab == "completed":
            qs = qs.filter(status=Task.Status.COMPLETED).order_by("-completed_at")
        # tab == "all" — no extra filter

        # search
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(description__icontains=q)
                | Q(contact__first_name__icontains=q)
                | Q(contact__last_name__icontains=q)
            )

        # type filter
        task_type = self.request.GET.get("type", "")
        if task_type:
            qs = qs.filter(task_type=task_type)

        # assignee filter
        assigned = self.request.GET.get("assigned", "")
        if assigned == "me":
            qs = qs.filter(assigned_to=self.request.user)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        org = self.org
        ctx["tab"] = self.request.GET.get("tab", "today")
        ctx["q"] = self.request.GET.get("q", "")
        ctx["filter_type"] = self.request.GET.get("type", "")
        ctx["filter_assigned"] = self.request.GET.get("assigned", "")
        ctx["task_type_choices"] = Task.TaskType.choices

        # counts for tab badges
        base = Task.objects.for_org(org)
        ctx["count_today"] = base.filter(
            due_date=today,
            status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
        ).count()
        ctx["count_overdue"] = base.filter(
            due_date__lt=today,
            status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
        ).count()
        ctx["count_upcoming"] = base.filter(
            due_date__gt=today,
            status__in=[Task.Status.PENDING, Task.Status.IN_PROGRESS],
        ).count()
        return ctx


# ------------------------------------------------------------------ #
# Task detail
# ------------------------------------------------------------------ #

class TaskDetailView(OrgMixin, DetailView):
    template_name = "tasks/detail.html"
    context_object_name = "task"

    def get_object(self):
        return get_object_or_404(
            Task.objects.for_org(self.org).select_related(
                "assigned_to", "assigned_by", "contact", "deal", "completed_by", "parent_task"
            ),
            pk=self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["complete_form"] = TaskCompleteForm()
        ctx["snooze_form"] = TaskSnoozeForm()
        return ctx


# ------------------------------------------------------------------ #
# Create / Update
# ------------------------------------------------------------------ #

class TaskCreateView(OrgRoleRequiredMixin, OrgMixin, CreateView):
    template_name = "tasks/task_form.html"
    form_class = TaskForm

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["org"] = self.org
        return kw

    def get_initial(self):
        initial = super().get_initial()
        initial["due_date"] = timezone.localdate()
        # Pre-fill contact/deal from query params
        if cid := self.request.GET.get("contact"):
            initial["contact"] = cid
        if did := self.request.GET.get("deal"):
            initial["deal"] = did
        return initial

    def form_valid(self, form):
        task = form.save(commit=False)
        task.organization = self.org
        task.assigned_by = self.request.user
        if not task.assigned_to:
            task.assigned_to = self.request.user
        task.save()
        messages.success(self.request, f'Task "{task.title}" created.')
        return redirect(self._success_url(task))

    def _success_url(self, task):
        # Go back to the contact/deal page if we came from one
        if task.contact_id:
            return reverse("contacts:detail", kwargs={"pk": task.contact_id})
        if task.deal_id:
            return reverse("pipelines:deal_detail", kwargs={"pk": task.deal_id})
        return reverse("tasks:list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "New Task"
        return ctx


class TaskUpdateView(OrgRoleRequiredMixin, OrgMixin, UpdateView):
    template_name = "tasks/task_form.html"
    form_class = TaskForm

    def get_object(self):
        return get_object_or_404(Task.objects.for_org(self.org), pk=self.kwargs["pk"])

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["org"] = self.org
        return kw

    def form_valid(self, form):
        task = form.save()
        messages.success(self.request, f"Task updated.")
        return redirect("tasks:detail", pk=task.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Edit Task"
        return ctx


# ------------------------------------------------------------------ #
# Actions: complete, snooze, delete
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def task_complete(request, pk):
    org = _get_org(request)
    task = get_object_or_404(Task.objects.for_org(org), pk=pk)

    if request.method == "POST":
        form = TaskCompleteForm(request.POST)
        if form.is_valid():
            task.complete(request.user, outcome=form.cleaned_data.get("outcome", ""))
            messages.success(request, f'"{task.title}" marked complete.')
        else:
            messages.error(request, "Could not complete task.")

    next_url = request.POST.get("next") or request.GET.get("next") or reverse("tasks:list")
    return redirect(next_url)


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def task_snooze(request, pk):
    org = _get_org(request)
    task = get_object_or_404(Task.objects.for_org(org), pk=pk)

    if request.method == "POST":
        form = TaskSnoozeForm(request.POST)
        if form.is_valid():
            snooze_map = {
                "1h": timedelta(hours=1),
                "3h": timedelta(hours=3),
                "1d": timedelta(days=1),
                "3d": timedelta(days=3),
                "1w": timedelta(weeks=1),
            }
            delta = snooze_map.get(form.cleaned_data["snooze_for"], timedelta(days=1))
            task.snooze(until=timezone.now() + delta)
            messages.success(request, f'"{task.title}" snoozed.')

    next_url = request.POST.get("next") or reverse("tasks:list")
    return redirect(next_url)


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def task_delete(request, pk):
    org = _get_org(request)
    task = get_object_or_404(Task.objects.for_org(org), pk=pk)

    if request.method == "POST":
        title = task.title
        task_id = task.pk
        task.delete()
        messages.success(request, f'Task "{title}" deleted.')
        log_audit_event(
            organization=org,
            actor=request.user,
            action="task.deleted",
            entity_type="task",
            entity_id=task_id,
            severity="critical",
            message=f'Task "{title}" deleted.',
            request=request,
        )
        return redirect("tasks:list")

    return render(request, "tasks/task_confirm_delete.html", {"task": task})
