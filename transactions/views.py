import itertools

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from compliance.audit import log_audit_event
from organizations.models import Membership
from organizations.permissions import OrgRoleRequiredMixin, require_org_role
from organizations.utils import get_active_membership
from .forms import (
    ChecklistItemUpdateForm,
    TransactionDocumentForm,
    TransactionForm,
    TransactionNoteForm,
)
from .models import (
    Transaction,
    TransactionChecklistItem,
    TransactionDocument,
    TransactionNote,
    seed_checklist,
)


REQUIRED_TRANSACTION_DOCUMENTS = {
    Transaction.TxType.PURCHASE: [
        TransactionDocument.Category.CONTRACT,
        TransactionDocument.Category.DISCLOSURE,
        TransactionDocument.Category.INSPECTION,
        TransactionDocument.Category.FINANCING,
        TransactionDocument.Category.TITLE,
        TransactionDocument.Category.CLOSING,
    ],
    Transaction.TxType.LISTING: [
        TransactionDocument.Category.CONTRACT,
        TransactionDocument.Category.DISCLOSURE,
        TransactionDocument.Category.TITLE,
        TransactionDocument.Category.CLOSING,
    ],
    Transaction.TxType.DUAL: [
        TransactionDocument.Category.CONTRACT,
        TransactionDocument.Category.DISCLOSURE,
        TransactionDocument.Category.FINANCING,
        TransactionDocument.Category.TITLE,
        TransactionDocument.Category.CLOSING,
    ],
    Transaction.TxType.LEASE: [
        TransactionDocument.Category.CONTRACT,
        TransactionDocument.Category.DISCLOSURE,
    ],
}


def _get_org(request):
    m = get_active_membership(request)
    return m.organization if m else None


class OrgMixin(LoginRequiredMixin):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        m = get_active_membership(request)
        self.org = m.organization if m else None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["org"] = self.org
        return ctx


# ------------------------------------------------------------------ #
# List
# ------------------------------------------------------------------ #

class TransactionListView(OrgMixin, ListView):
    template_name = "transactions/list.html"
    context_object_name = "transactions"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            Transaction.objects.for_org(self.org)
            .select_related("buyer_contact", "seller_contact", "linked_property", "buyers_agent", "listing_agent")
        )
        tab = self.request.GET.get("tab", "active")
        if tab == "active":
            qs = qs.filter(status__in=[
                Transaction.Status.ACTIVE,
                Transaction.Status.PENDING,
                Transaction.Status.CLEAR_TO_CLOSE,
                Transaction.Status.ON_HOLD,
            ])
        elif tab == "closed":
            qs = qs.filter(status=Transaction.Status.CLOSED)
        elif tab == "cancelled":
            qs = qs.filter(status__in=[
                Transaction.Status.FALLEN_THROUGH,
                Transaction.Status.CANCELLED,
            ])
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(property_address__icontains=q)
                | Q(linked_property__address__icontains=q)
                | Q(linked_property__city__icontains=q)
                | Q(linked_property__zip_code__icontains=q)
                | Q(mls_number__icontains=q)
                | Q(buyer_contact__first_name__icontains=q)
                | Q(buyer_contact__last_name__icontains=q)
                | Q(seller_contact__first_name__icontains=q)
                | Q(seller_contact__last_name__icontains=q)
            )
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tab"] = self.request.GET.get("tab", "active")
        ctx["q"] = self.request.GET.get("q", "")
        base = Transaction.objects.for_org(self.org)
        ctx["count_active"] = base.filter(status__in=[
            Transaction.Status.ACTIVE, Transaction.Status.PENDING,
            Transaction.Status.CLEAR_TO_CLOSE, Transaction.Status.ON_HOLD,
        ]).count()
        ctx["count_closed"] = base.filter(status=Transaction.Status.CLOSED).count()
        ctx["count_cancelled"] = base.filter(status__in=[
            Transaction.Status.FALLEN_THROUGH, Transaction.Status.CANCELLED,
        ]).count()
        return ctx


# ------------------------------------------------------------------ #
# Detail
# ------------------------------------------------------------------ #

class TransactionDetailView(OrgMixin, DetailView):
    template_name = "transactions/detail.html"
    context_object_name = "tx"

    def get_object(self):
        return get_object_or_404(
            Transaction.objects.for_org(self.org).select_related(
                "buyer_contact", "seller_contact", "linked_property",
                "listing_agent", "buyers_agent", "transaction_coordinator", "deal",
            ),
            pk=self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tx = self.object
        documents = tx.documents.select_related("uploaded_by").all()

        checklist_qs = tx.checklist_items.select_related("assigned_to").order_by("order", "due_date")
        total = checklist_qs.count()
        done  = checklist_qs.filter(status__in=["done", "na", "waived"]).count()
        ctx["checklist_progress"] = int(done / total * 100) if total else 0
        ctx["checklist_done"]  = done
        ctx["checklist_total"] = total

        # Group by category
        grouped = {}
        for item in checklist_qs:
            grouped.setdefault(item.get_category_display(), []).append(item)
        ctx["checklist_grouped"] = grouped

        ctx["note_form"] = TransactionNoteForm()
        ctx["notes"] = tx.tx_notes.select_related("author").all()
        ctx["documents"] = documents
        ctx["document_form"] = TransactionDocumentForm()
        category_counts = {}
        for doc in documents:
            category_counts[doc.category] = category_counts.get(doc.category, 0) + 1
        required_codes = REQUIRED_TRANSACTION_DOCUMENTS.get(tx.transaction_type, [])
        category_labels = dict(TransactionDocument.Category.choices)
        checklist = []
        missing = []
        for code in required_codes:
            count = category_counts.get(code, 0)
            is_present = count > 0
            checklist.append({
                "code": code,
                "label": category_labels.get(code, code),
                "count": count,
                "is_present": is_present,
            })
            if not is_present:
                missing.append(category_labels.get(code, code))
        ctx["document_required_checklist"] = checklist
        ctx["missing_document_labels"] = missing
        ctx["missing_document_count"] = len(missing)
        ctx["item_update_form"] = ChecklistItemUpdateForm(self.org)
        ctx["overdue_dates"] = tx.overdue_dates
        ctx["upcoming_dates"] = tx.upcoming_dates
        ctx["milestones"] = [
            ("Inspection Completed",   tx.inspection_completed),
            ("Appraisal Completed",    tx.appraisal_completed),
            ("Financing Approved",     tx.financing_approved),
            ("Title Clear",            tx.title_clear),
            ("Final Walkthrough Done", tx.final_walkthrough_done),
        ]
        return ctx


# ------------------------------------------------------------------ #
# Create / Update
# ------------------------------------------------------------------ #

class TransactionCreateView(OrgRoleRequiredMixin, OrgMixin, CreateView):
    template_name = "transactions/transaction_form.html"
    form_class = TransactionForm

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["org"] = self.org
        return kw

    def form_valid(self, form):
        tx = form.save(commit=False)
        tx.organization = self.org
        tx.save()
        seed_checklist(tx)
        messages.success(self.request, f'Transaction for "{tx.display_address}" created.')
        return redirect("transactions:detail", pk=tx.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "New Transaction"
        return ctx


class TransactionUpdateView(OrgRoleRequiredMixin, OrgMixin, UpdateView):
    template_name = "transactions/transaction_form.html"
    form_class = TransactionForm

    def get_object(self):
        return get_object_or_404(Transaction.objects.for_org(self.org), pk=self.kwargs["pk"])

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["org"] = self.org
        return kw

    def form_valid(self, form):
        tx = form.save()
        messages.success(self.request, "Transaction updated.")
        return redirect("transactions:detail", pk=tx.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Edit Transaction"
        return ctx


# ------------------------------------------------------------------ #
# Checklist
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def checklist_toggle(request, pk, item_pk):
    """Quick toggle: pending → done, done → pending."""
    org  = _get_org(request)
    tx   = get_object_or_404(Transaction.objects.for_org(org), pk=pk)
    item = get_object_or_404(TransactionChecklistItem, pk=item_pk, transaction=tx)

    if request.method == "POST":
        if item.status == TransactionChecklistItem.ItemStatus.DONE:
            item.status       = TransactionChecklistItem.ItemStatus.PENDING
            item.completed_at = None
        else:
            item.status       = TransactionChecklistItem.ItemStatus.DONE
            item.completed_at = timezone.now()
        item.save(update_fields=["status", "completed_at"])

    return redirect("transactions:detail", pk=pk)


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def checklist_item_update(request, pk, item_pk):
    org  = _get_org(request)
    tx   = get_object_or_404(Transaction.objects.for_org(org), pk=pk)
    item = get_object_or_404(TransactionChecklistItem, pk=item_pk, transaction=tx)

    if request.method == "POST":
        form = ChecklistItemUpdateForm(org, request.POST, instance=item)
        if form.is_valid():
            saved = form.save(commit=False)
            if saved.status == TransactionChecklistItem.ItemStatus.DONE and not saved.completed_at:
                saved.completed_at = timezone.now()
            elif saved.status != TransactionChecklistItem.ItemStatus.DONE:
                saved.completed_at = None
            saved.save()
            messages.success(request, f'"{item.title}" updated.')
        else:
            messages.error(request, "Could not update checklist item.")

    return redirect("transactions:detail", pk=pk)


# ------------------------------------------------------------------ #
# Notes
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def add_note(request, pk):
    org = _get_org(request)
    tx  = get_object_or_404(Transaction.objects.for_org(org), pk=pk)

    if request.method == "POST":
        form = TransactionNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.transaction = tx
            note.author      = request.user
            note.save()
        else:
            messages.error(request, "Could not add note.")

    return redirect("transactions:detail", pk=pk)


# ------------------------------------------------------------------ #
# Delete
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def transaction_delete(request, pk):
    org = _get_org(request)
    tx  = get_object_or_404(Transaction.objects.for_org(org), pk=pk)

    if request.method == "POST":
        addr = tx.display_address
        tx_id = tx.pk
        tx.delete()
        messages.success(request, f'Transaction for "{addr}" deleted.')
        log_audit_event(
            organization=org,
            actor=request.user,
            action="transaction.deleted",
            entity_type="transaction",
            entity_id=tx_id,
            severity="critical",
            message=f'Transaction for "{addr}" deleted.',
            request=request,
        )
        return redirect("transactions:list")

    return render(request, "transactions/transaction_confirm_delete.html", {"tx": tx})


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def document_upload(request, pk):
    org = _get_org(request)
    tx = get_object_or_404(Transaction.objects.for_org(org), pk=pk)

    if request.method == "POST":
        form = TransactionDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.organization = org
            doc.transaction = tx
            doc.uploaded_by = request.user
            doc.save()
            messages.success(request, f'Document "{doc.title}" uploaded.')
        else:
            messages.error(request, "Could not upload document. Check the form and try again.")
    return redirect("transactions:detail", pk=pk)


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def document_delete(request, pk, doc_pk):
    org = _get_org(request)
    tx = get_object_or_404(Transaction.objects.for_org(org), pk=pk)
    doc = get_object_or_404(TransactionDocument.objects.for_org(org), pk=doc_pk, transaction=tx)

    if request.method == "POST":
        title = doc.title
        if doc.file:
            doc.file.delete(save=False)
        doc.delete()
        messages.success(request, f'Document "{title}" deleted.')

    return redirect("transactions:detail", pk=pk)
