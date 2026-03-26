from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, UpdateView

from compliance.audit import log_audit_event
from organizations.models import Membership
from organizations.permissions import OrgRoleRequiredMixin, require_org_role
from organizations.utils import get_active_membership
from .forms import DealForm, DealMoveForm
from .models import Deal, Pipeline, PipelineStage, StageHistory
from .requirements import can_enter_stage, evaluate_stage_requirements, provision_stage_tasks


def _get_org(request):
    membership = get_active_membership(request)
    return membership.organization if membership else None


class OrgMixin(LoginRequiredMixin):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        membership = get_active_membership(request)
        self.org = membership.organization if membership else None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["org"] = self.org
        return ctx


@login_required
def board_view(request, pipeline_pk=None):
    """Main kanban board. Shows one pipeline at a time."""
    membership = get_active_membership(request)
    org = membership.organization if membership else None

    pipelines = Pipeline.objects.filter(organization=org, is_active=True).order_by("pipeline_type")

    # Select which pipeline to display
    if pipeline_pk:
        current_pipeline = get_object_or_404(Pipeline, pk=pipeline_pk, organization=org)
    else:
        current_pipeline = pipelines.first()

    if not current_pipeline:
        return render(request, "pipelines/board.html", {
            "pipelines": pipelines,
            "current_pipeline": None,
            "columns": [],
        })

    stages = current_pipeline.stages.filter(is_active=True).order_by("order")

    # Build column data: stage + deals + aggregates
    columns = []
    for stage in stages:
        deals = (
            Deal.objects
            .filter(pipeline=current_pipeline, stage=stage, organization=org, status=Deal.Status.ACTIVE)
            .select_related("contact", "assigned_to")
            .order_by("-created_at")
        )
        total_value = sum(d.value for d in deals if d.value) or 0
        columns.append({
            "stage": stage,
            "deals": list(deals),
            "count": len(list(deals)),
            "total_value": total_value,
        })
        # Re-evaluate deals as list to avoid double query
        deals_list = list(
            Deal.objects
            .filter(pipeline=current_pipeline, stage=stage, organization=org, status=Deal.Status.ACTIVE)
            .select_related("contact", "assigned_to")
            .order_by("-created_at")
        )
        columns[-1]["deals"] = deals_list
        columns[-1]["count"] = len(deals_list)
        columns[-1]["total_value"] = sum(d.value for d in deals_list if d.value) or 0

    return render(request, "pipelines/board.html", {
        "pipelines": pipelines,
        "current_pipeline": current_pipeline,
        "columns": columns,
        "org": org,
    })


class DealCreateView(OrgRoleRequiredMixin, OrgMixin, CreateView):
    template_name = "pipelines/deal_form.html"
    form_class = DealForm

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["org"] = self.org
        return kw

    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill pipeline/stage/contact from query params
        if self.request.GET.get("pipeline"):
            initial["pipeline"] = self.request.GET["pipeline"]
        if self.request.GET.get("stage"):
            initial["stage"] = self.request.GET["stage"]
        if self.request.GET.get("contact"):
            initial["contact"] = self.request.GET["contact"]
        return initial

    def form_valid(self, form):
        form.instance.organization = self.org
        form.instance.assigned_to = form.instance.assigned_to or self.request.user
        response = super().form_valid(form)
        # Record initial stage history
        StageHistory.objects.create(
            deal=self.object,
            from_stage=None,
            to_stage=self.object.stage,
            changed_by=self.request.user,
            note="Deal created",
        )
        return response

    def get_success_url(self):
        return reverse("pipelines:board_pipeline", kwargs={"pipeline_pk": self.object.pipeline.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["action"] = "Add Deal"
        return ctx


class DealUpdateView(OrgRoleRequiredMixin, OrgMixin, UpdateView):
    template_name = "pipelines/deal_form.html"
    form_class = DealForm

    def get_queryset(self):
        return Deal.objects.filter(organization=self.org)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["org"] = self.org
        return kw

    def get_success_url(self):
        return reverse("pipelines:board_pipeline", kwargs={"pipeline_pk": self.object.pipeline.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["action"] = f"Edit Deal — {self.object.title}"
        return ctx


class DealDetailView(OrgMixin, DetailView):
    template_name = "pipelines/deal_detail.html"
    context_object_name = "deal"

    def get_queryset(self):
        return Deal.objects.filter(organization=self.org).select_related(
            "contact", "pipeline", "stage", "assigned_to"
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["stage_history"] = (
            self.object.stage_history
            .select_related("from_stage", "to_stage", "changed_by")
            .order_by("-changed_at")
        )
        ctx["move_form"] = DealMoveForm(pipeline=self.object.pipeline)
        ctx["tasks"] = self.object.tasks.filter(
            status__in=["pending", "in_progress"]
        ).order_by("due_date")[:5]
        ctx["stage_requirements"] = evaluate_stage_requirements(deal=self.object, stage=self.object.stage)
        return ctx


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def deal_move(request, pk):
    """POST: move a deal to a new stage, record history."""
    membership = get_active_membership(request)
    org = membership.organization if membership else None
    deal = get_object_or_404(Deal, pk=pk, organization=org)

    if request.method == "POST":
        new_stage_pk = request.POST.get("stage")
        note_text = request.POST.get("note", "")
        new_stage = get_object_or_404(PipelineStage, pk=new_stage_pk, pipeline=deal.pipeline)

        allowed, requirement_status, blocking = can_enter_stage(deal=deal, stage=new_stage)
        if not allowed:
            blocking_message = ", ".join(blocking)
            from django.contrib import messages as django_messages
            django_messages.error(request, f"Cannot move deal to '{new_stage.name}' because {blocking_message}.")
            return redirect("pipelines:deal_detail", pk=deal.pk)

        created_tasks = provision_stage_tasks(deal=deal, stage=new_stage, trigger_user=request.user)

        old_stage = deal.stage

        # Update stage + timing
        deal.stage = new_stage
        deal.entered_stage_at = timezone.now()

        # Handle terminal stages
        if new_stage.is_won:
            deal.status = Deal.Status.WON
            deal.actual_close_date = timezone.localdate()
        elif new_stage.is_lost:
            deal.status = Deal.Status.LOST
            deal.lost_reason = note_text
        else:
            deal.status = Deal.Status.ACTIVE

        deal.save(update_fields=["stage", "entered_stage_at", "status", "actual_close_date", "lost_reason"])

        StageHistory.objects.create(
            deal=deal,
            from_stage=old_stage,
            to_stage=new_stage,
            changed_by=request.user,
            note=note_text,
        )
        if created_tasks:
            from django.contrib import messages as django_messages

            django_messages.success(
                request,
                f"Moved to '{new_stage.name}'. Created {len(created_tasks)} stage requirement task(s).",
            )
        elif requirement_status["unmet_forms"] or requirement_status["unmet_automations"]:
            from django.contrib import messages as django_messages

            django_messages.warning(
                request,
                f"Moved to '{new_stage.name}', but some stage requirements still need attention.",
            )
        log_audit_event(
            organization=org,
            actor=request.user,
            action="deal.stage_moved",
            entity_type="deal",
            entity_id=deal.pk,
            message=f"Deal moved from {old_stage.name} to {new_stage.name}.",
            metadata={
                "from_stage_id": old_stage.pk,
                "to_stage_id": new_stage.pk,
                "created_requirement_tasks": len(created_tasks),
            },
            request=request,
        )
        try:
            from automations.engine import run_trigger
            from automations.models import AutomationRule

            run_trigger(
                organization=org,
                trigger_type=AutomationRule.TriggerType.DEAL_STAGE_CHANGED,
                context={
                    "deal": deal,
                    "contact": deal.contact,
                    "from_stage": old_stage,
                    "to_stage": new_stage,
                    "trigger_user": request.user,
                    "source": "deal_stage_changed",
                },
                object_ref=f"deal:{deal.pk}:{new_stage.pk}",
            )
        except Exception:
            pass

    return redirect("pipelines:board_pipeline", pipeline_pk=deal.pipeline.pk)


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def deal_delete(request, pk):
    membership = get_active_membership(request)
    org = membership.organization if membership else None
    deal = get_object_or_404(Deal, pk=pk, organization=org)
    pipeline_pk = deal.pipeline.pk
    if request.method == "POST":
        log_audit_event(
            organization=org,
            actor=request.user,
            action="deal.deleted",
            entity_type="deal",
            entity_id=deal.pk,
            severity="critical",
            message=f"Deal '{deal.title}' deleted.",
            metadata={"pipeline_id": pipeline_pk},
            request=request,
        )
        deal.delete()
    return redirect("pipelines:board_pipeline", pipeline_pk=pipeline_pk)
