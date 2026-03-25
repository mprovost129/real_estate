from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import CreateView, ListView, UpdateView

from compliance.audit import log_audit_event
from organizations.models import Membership
from organizations.permissions import OrgRoleRequiredMixin, require_org_role
from .engine import preview_trigger
from .forms import AutomationRuleForm, AutomationTestForm
from .models import AutomationRule, AutomationRun


def _get_org(request):
    m = request.user.memberships.filter(is_active=True).select_related("organization").first()
    return m.organization if m else None


class OrgMixin(LoginRequiredMixin):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        m = request.user.memberships.filter(is_active=True).select_related("organization").first()
        self.org = m.organization if m else None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["org"] = self.org
        return ctx


class AutomationRuleListView(OrgMixin, ListView):
    template_name = "automations/list.html"
    context_object_name = "rules"

    def get_queryset(self):
        qs = AutomationRule.objects.for_org(self.org).order_by("name")
        trigger = self.request.GET.get("trigger", "").strip()
        status = self.request.GET.get("status", "").strip()
        q = self.request.GET.get("q", "").strip()
        if trigger:
            qs = qs.filter(trigger_type=trigger)
        if status == "active":
            qs = qs.filter(is_active=True)
        elif status == "inactive":
            qs = qs.filter(is_active=False)
        if q:
            qs = qs.filter(name__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base = AutomationRule.objects.for_org(self.org)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["trigger"] = self.request.GET.get("trigger", "")
        ctx["status"] = self.request.GET.get("status", "")
        ctx["trigger_choices"] = AutomationRule.TriggerType.choices
        ctx["count_all"] = base.count()
        ctx["count_active"] = base.filter(is_active=True).count()
        ctx["count_inactive"] = base.filter(is_active=False).count()
        ctx["recent_runs"] = (
            AutomationRun.objects.for_org(self.org)
            .select_related("rule")
            .order_by("-created_at")[:15]
        )
        return ctx


class AutomationRuleCreateView(OrgRoleRequiredMixin, OrgMixin, CreateView):
    required_role = Membership.Role.ADMIN
    template_name = "automations/rule_form.html"
    form_class = AutomationRuleForm

    def form_valid(self, form):
        rule = form.save(commit=False)
        rule.organization = self.org
        rule.created_by = self.request.user
        rule.save()
        messages.success(self.request, f'Automation rule "{rule.name}" created.')
        log_audit_event(
            organization=self.org,
            actor=self.request.user,
            action="automation.rule_created",
            entity_type="automation_rule",
            entity_id=rule.pk,
            severity="warning",
            message=f'Automation rule "{rule.name}" created.',
            request=self.request,
        )
        return redirect("automations:list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "New Automation Rule"
        ctx["samples"] = _json_samples()
        ctx["builder_options"] = _builder_options()
        return ctx


class AutomationRuleUpdateView(OrgRoleRequiredMixin, OrgMixin, UpdateView):
    required_role = Membership.Role.ADMIN
    template_name = "automations/rule_form.html"
    form_class = AutomationRuleForm

    def get_object(self):
        return get_object_or_404(AutomationRule.objects.for_org(self.org), pk=self.kwargs["pk"])

    def form_valid(self, form):
        rule = form.save()
        messages.success(self.request, f'Automation rule "{rule.name}" updated.')
        log_audit_event(
            organization=self.org,
            actor=self.request.user,
            action="automation.rule_updated",
            entity_type="automation_rule",
            entity_id=rule.pk,
            severity="warning",
            message=f'Automation rule "{rule.name}" updated.',
            request=self.request,
        )
        return redirect("automations:list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Edit Automation Rule"
        ctx["samples"] = _json_samples()
        ctx["builder_options"] = _builder_options()
        return ctx


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def rule_delete(request, pk):
    org = _get_org(request)
    rule = get_object_or_404(AutomationRule.objects.for_org(org), pk=pk)

    if request.method == "POST":
        name = rule.name
        rule_pk = rule.pk
        rule.delete()
        messages.success(request, f'Automation rule "{name}" deleted.')
        log_audit_event(
            organization=org,
            actor=request.user,
            action="automation.rule_deleted",
            entity_type="automation_rule",
            entity_id=rule_pk,
            severity="critical",
            message=f'Automation rule "{name}" deleted.',
            request=request,
        )
        return redirect("automations:list")

    return render(request, "automations/rule_confirm_delete.html", {"rule": rule, "org": org})


def _json_samples():
    return {
        "conditions_lead": '{"all":[{"source_in":["website","open_house"]},{"any":[{"contact_type_in":["buyer"]},{"contact_type_in":["seller"]}]}]}',
        "actions_lead": '[{"type":"create_task","title":"Call new lead","due_in_days":0,"priority":"high"}]',
        "conditions_stage": '{"all":[{"pipeline_type_in":["buyer"]},{"stage_in":["Under Contract"]},{"not":{"source_in":["backfill"]}}]}',
        "actions_stage": '[{"type":"create_note","body":"Deal reached under contract."},{"type":"notify","title":"Deal updated","body":"A deal changed stage."}]',
    }


def _builder_options():
    from contacts.models import Contact, ContactNote
    from pipelines.models import Pipeline
    from tasks.models import Task

    return {
        "contact_type_choices": [{"value": v, "label": l} for v, l in Contact.ContactType.choices],
        "pipeline_type_choices": [{"value": v, "label": l} for v, l in Pipeline.PipelineType.choices],
        "task_type_choices": [{"value": v, "label": l} for v, l in Task.TaskType.choices],
        "priority_choices": [{"value": v, "label": l} for v, l in Task.Priority.choices],
        "note_type_choices": [{"value": v, "label": l} for v, l in ContactNote.NoteType.choices],
    }


@login_required
@require_org_role(Membership.Role.ADMIN, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def rule_test(request):
    org = _get_org(request)
    form = AutomationTestForm(request.POST or None)
    results = []
    context_preview = {}

    if request.method == "POST" and form.is_valid():
        from contacts.models import Contact
        from pipelines.models import Deal, PipelineStage
        from tasks.models import Task

        source = form.cleaned_data.get("source", "").strip()
        contact_id = form.cleaned_data.get("contact_id")
        deal_id = form.cleaned_data.get("deal_id")
        task_id = form.cleaned_data.get("task_id")
        to_stage_id = form.cleaned_data.get("to_stage_id")

        context = {"trigger_user": request.user}
        context_preview = {
            "source": source or None,
            "contact_id": contact_id,
            "deal_id": deal_id,
            "task_id": task_id,
            "to_stage_id": to_stage_id,
        }

        if source:
            context["source"] = source
        if contact_id:
            contact = Contact.objects.for_org(org).filter(pk=contact_id).first()
            if contact:
                context["contact"] = contact
            else:
                messages.warning(request, f"Contact {contact_id} was not found in this organization.")
        if deal_id:
            deal = Deal.objects.for_org(org).select_related("pipeline", "stage", "contact").filter(pk=deal_id).first()
            if deal:
                context["deal"] = deal
                context.setdefault("contact", deal.contact)
            else:
                messages.warning(request, f"Deal {deal_id} was not found in this organization.")
        if task_id:
            task = Task.objects.for_org(org).select_related("contact", "deal").filter(pk=task_id).first()
            if task:
                context["task"] = task
                if task.contact:
                    context.setdefault("contact", task.contact)
                if task.deal:
                    context.setdefault("deal", task.deal)
            else:
                messages.warning(request, f"Task {task_id} was not found in this organization.")
        if to_stage_id:
            to_stage = PipelineStage.objects.filter(pk=to_stage_id, pipeline__organization=org).first()
            if to_stage:
                context["to_stage"] = to_stage
            else:
                messages.warning(request, f"Stage {to_stage_id} was not found in this organization.")

        results = preview_trigger(
            organization=org,
            trigger_type=form.cleaned_data["trigger_type"],
            context=context,
        )

        if not results:
            messages.info(request, "No active rules exist for this trigger.")

    return render(
        request,
        "automations/test.html",
        {
            "org": org,
            "form": form,
            "results": results,
            "context_preview": context_preview,
        },
    )
