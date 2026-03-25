from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from compliance.audit import log_audit_event
from organizations.models import Membership
from organizations.permissions import OrgRoleRequiredMixin, require_org_role
from .forms import PropertyForm, PropertyNoteForm
from .models import Property, PropertyNote, PropertyPhoto


# ------------------------------------------------------------------ #
# Org mixin
# ------------------------------------------------------------------ #

class OrgMixin(LoginRequiredMixin):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        membership = (
            request.user.memberships
            .filter(is_active=True)
            .select_related("organization")
            .first()
        )
        self.org = membership.organization if membership else None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["org"] = self.org
        return ctx


def _get_org(request):
    m = request.user.memberships.filter(is_active=True).select_related("organization").first()
    return m.organization if m else None


# ------------------------------------------------------------------ #
# List
# ------------------------------------------------------------------ #

class PropertyListView(OrgMixin, ListView):
    template_name = "properties/list.html"
    context_object_name = "properties"
    paginate_by = 24

    def get_queryset(self):
        qs = (
            Property.objects.for_org(self.org)
            .filter(is_active=True)
            .select_related("owner_contact", "listing_agent")
            .prefetch_related("photos")
            .order_by("-created_at")
        )

        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(address__icontains=q)
                | Q(city__icontains=q)
                | Q(zip_code__icontains=q)
                | Q(mls_number__icontains=q)
                | Q(neighborhood__icontains=q)
            )

        status = self.request.GET.get("status", "")
        if status:
            qs = qs.filter(status=status)

        prop_type = self.request.GET.get("type", "")
        if prop_type:
            qs = qs.filter(property_type=prop_type)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"]             = self.request.GET.get("q", "")
        ctx["filter_status"] = self.request.GET.get("status", "")
        ctx["filter_type"]   = self.request.GET.get("type", "")
        ctx["status_choices"] = Property.Status.choices
        ctx["type_choices"]   = Property.PropertyType.choices

        base = Property.objects.for_org(self.org).filter(is_active=True)
        ctx["count_active"]  = base.filter(status=Property.Status.ACTIVE).count()
        ctx["count_pending"] = base.filter(
            status__in=[Property.Status.PENDING, Property.Status.UNDER_CONTRACT]
        ).count()
        ctx["count_sold"]    = base.filter(status=Property.Status.SOLD).count()
        ctx["count_total"]   = base.count()
        return ctx


# ------------------------------------------------------------------ #
# Detail
# ------------------------------------------------------------------ #

class PropertyDetailView(OrgMixin, DetailView):
    template_name = "properties/detail.html"
    context_object_name = "prop"

    def get_object(self):
        return get_object_or_404(
            Property.objects.for_org(self.org)
            .select_related("owner_contact", "listing_agent"),
            pk=self.kwargs["pk"],
            is_active=True,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        prop = self.object
        ctx["notes"]     = prop.prop_notes.select_related("author").all()[:20]
        ctx["note_form"] = PropertyNoteForm()
        ctx["photos"]    = prop.photos.all()
        return ctx


# ------------------------------------------------------------------ #
# Create / Update
# ------------------------------------------------------------------ #

class PropertyCreateView(OrgRoleRequiredMixin, OrgMixin, CreateView):
    template_name = "properties/property_form.html"
    form_class = PropertyForm

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["org"] = self.org
        return kw

    def form_valid(self, form):
        prop = form.save(commit=False)
        prop.organization = self.org
        prop.save()
        messages.success(self.request, f'Property "{prop.short_address}" added.')
        return redirect("properties:detail", pk=prop.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Add Property"
        return ctx


class PropertyUpdateView(OrgRoleRequiredMixin, OrgMixin, UpdateView):
    template_name = "properties/property_form.html"
    form_class = PropertyForm

    def get_object(self):
        return get_object_or_404(
            Property.objects.for_org(self.org), pk=self.kwargs["pk"], is_active=True
        )

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["org"] = self.org
        return kw

    def form_valid(self, form):
        prop = form.save()
        messages.success(self.request, "Property updated.")
        return redirect("properties:detail", pk=prop.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Edit Property"
        return ctx


# ------------------------------------------------------------------ #
# Add note
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def property_add_note(request, pk):
    org  = _get_org(request)
    prop = get_object_or_404(Property.objects.for_org(org), pk=pk, is_active=True)

    if request.method == "POST":
        form = PropertyNoteForm(request.POST)
        if form.is_valid():
            note          = form.save(commit=False)
            note.property = prop
            note.author   = request.user
            note.save()
            messages.success(request, "Note added.")
        else:
            messages.error(request, "Could not save note.")

    return redirect("properties:detail", pk=pk)


# ------------------------------------------------------------------ #
# Delete (soft)
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def property_delete(request, pk):
    org  = _get_org(request)
    prop = get_object_or_404(Property.objects.for_org(org), pk=pk)

    if request.method == "POST":
        prop.is_active = False
        prop.save(update_fields=["is_active"])
        messages.success(request, f'Property "{prop.short_address}" removed.')
        log_audit_event(
            organization=org,
            actor=request.user,
            action="property.deactivated",
            entity_type="property",
            entity_id=prop.pk,
            severity="critical",
            message=f'Property "{prop.short_address}" removed.',
            request=request,
        )
        return redirect("properties:list")

    return render(request, "properties/property_confirm_delete.html", {"prop": prop})


# ------------------------------------------------------------------ #
# Photo management
# ------------------------------------------------------------------ #

@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def photo_upload(request, pk):
    org  = _get_org(request)
    prop = get_object_or_404(Property.objects.for_org(org), pk=pk, is_active=True)

    if request.method == "POST":
        files = request.FILES.getlist("images")
        if not files:
            messages.error(request, "No files selected.")
            return redirect("properties:detail", pk=pk)

        has_primary = prop.photos.filter(is_primary=True).exists()
        caption = request.POST.get("caption", "").strip()
        for i, f in enumerate(files):
            photo = PropertyPhoto(
                property=prop,
                image=f,
                caption=caption,
                order=prop.photos.count() + i,
                is_primary=(not has_primary and i == 0),
            )
            photo.save()
            has_primary = True  # only first ever is auto-primary

        count = len(files)
        messages.success(request, f"{count} photo{'s' if count > 1 else ''} uploaded.")

    return redirect("properties:detail", pk=pk)


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def photo_delete(request, pk, photo_pk):
    org   = _get_org(request)
    prop  = get_object_or_404(Property.objects.for_org(org), pk=pk, is_active=True)
    photo = get_object_or_404(PropertyPhoto, pk=photo_pk, property=prop)

    if request.method == "POST":
        was_primary = photo.is_primary
        photo.image.delete(save=False)
        photo.delete()
        # Promote next photo to primary if needed
        if was_primary:
            next_photo = prop.photos.first()
            if next_photo:
                next_photo.is_primary = True
                next_photo.save(update_fields=["is_primary"])
        messages.success(request, "Photo deleted.")

    return redirect("properties:detail", pk=pk)


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def photo_set_primary(request, pk, photo_pk):
    org   = _get_org(request)
    prop  = get_object_or_404(Property.objects.for_org(org), pk=pk, is_active=True)
    photo = get_object_or_404(PropertyPhoto, pk=photo_pk, property=prop)

    if request.method == "POST":
        prop.photos.update(is_primary=False)
        photo.is_primary = True
        photo.save(update_fields=["is_primary"])
        messages.success(request, "Cover photo updated.")

    return redirect("properties:detail", pk=pk)


@login_required
@require_org_role(Membership.Role.MEMBER, org_resolver=lambda request, *args, **kwargs: _get_org(request))
def photo_caption(request, pk, photo_pk):
    org   = _get_org(request)
    prop  = get_object_or_404(Property.objects.for_org(org), pk=pk, is_active=True)
    photo = get_object_or_404(PropertyPhoto, pk=photo_pk, property=prop)

    if request.method == "POST":
        caption = request.POST.get("caption", "").strip()[:200]
        photo.caption = caption
        photo.save(update_fields=["caption"])

    return redirect("properties:detail", pk=pk)
