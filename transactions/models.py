from django.conf import settings
from django.db import models
from django.utils import timezone

from organizations.mixins import OrgScopedModel


class Transaction(OrgScopedModel):

    class TxType(models.TextChoices):
        PURCHASE = "purchase", "Purchase (Buyer)"
        LISTING  = "listing",  "Listing (Seller)"
        DUAL     = "dual",     "Dual Agency"
        LEASE    = "lease",    "Lease / Rental"

    class Status(models.TextChoices):
        ACTIVE          = "active",          "Active"
        PENDING         = "pending",         "Pending"
        CLEAR_TO_CLOSE  = "clear_to_close",  "Clear to Close"
        CLOSED          = "closed",          "Closed"
        ON_HOLD         = "on_hold",         "On Hold"
        FALLEN_THROUGH  = "fallen_through",  "Fallen Through"
        CANCELLED       = "cancelled",       "Cancelled"

    class FinancingType(models.TextChoices):
        CONVENTIONAL = "conventional", "Conventional"
        FHA          = "fha",          "FHA"
        VA           = "va",           "VA"
        USDA         = "usda",         "USDA"
        JUMBO        = "jumbo",        "Jumbo"
        CASH         = "cash",         "Cash"
        OTHER        = "other",        "Other"

    # ------------------------------------------------------------------ #
    # Links
    # ------------------------------------------------------------------ #
    deal = models.OneToOneField(
        "pipelines.Deal",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="transaction",
    )
    buyer_contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="buyer_transactions",
    )
    seller_contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="seller_transactions",
    )
    linked_property = models.ForeignKey(
        "properties.Property",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="transactions",
    )
    # Fallback address if no property FK
    property_address = models.CharField(max_length=255, blank=True)

    # ------------------------------------------------------------------ #
    # Identity
    # ------------------------------------------------------------------ #
    transaction_type = models.CharField(
        max_length=15, choices=TxType.choices, default=TxType.PURCHASE
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    financing_type = models.CharField(
        max_length=15, choices=FinancingType.choices, default=FinancingType.CONVENTIONAL
    )
    mls_number = models.CharField(max_length=50, blank=True)

    # ------------------------------------------------------------------ #
    # Agents
    # ------------------------------------------------------------------ #
    listing_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="listing_transactions",
    )
    buyers_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="buyer_agent_transactions",
    )
    transaction_coordinator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="coordinated_transactions",
    )

    # ------------------------------------------------------------------ #
    # Financial
    # ------------------------------------------------------------------ #
    purchase_price    = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    earnest_money     = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    earnest_money_due = models.DateField(null=True, blank=True)
    earnest_received  = models.BooleanField(default=False)
    down_payment      = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    loan_amount       = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    commission_pct    = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True,
        help_text="Commission percentage (e.g. 3.00)",
    )
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    referral_fee      = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # ------------------------------------------------------------------ #
    # Third parties
    # ------------------------------------------------------------------ #
    lender_name    = models.CharField(max_length=200, blank=True)
    lender_contact = models.CharField(max_length=200, blank=True)
    lender_email   = models.EmailField(blank=True)
    lender_phone   = models.CharField(max_length=30, blank=True)

    title_company  = models.CharField(max_length=200, blank=True)
    title_officer  = models.CharField(max_length=200, blank=True)
    title_email    = models.EmailField(blank=True)
    title_phone    = models.CharField(max_length=30, blank=True)

    closing_attorney = models.CharField(max_length=200, blank=True)
    closing_email    = models.EmailField(blank=True)

    # ------------------------------------------------------------------ #
    # Key dates
    # ------------------------------------------------------------------ #
    contract_date                 = models.DateField(null=True, blank=True)
    inspection_deadline           = models.DateField(null=True, blank=True)
    inspection_objection_deadline = models.DateField(null=True, blank=True)
    inspection_resolution_deadline = models.DateField(null=True, blank=True)
    appraisal_deadline            = models.DateField(null=True, blank=True)
    financing_deadline            = models.DateField(null=True, blank=True)
    title_deadline                = models.DateField(null=True, blank=True)
    closing_date                  = models.DateField(null=True, blank=True)
    possession_date               = models.DateField(null=True, blank=True)

    # ------------------------------------------------------------------ #
    # Milestone status flags
    # ------------------------------------------------------------------ #
    inspection_completed  = models.BooleanField(default=False)
    appraisal_completed   = models.BooleanField(default=False)
    financing_approved    = models.BooleanField(default=False)
    title_clear           = models.BooleanField(default=False)
    final_walkthrough_done = models.BooleanField(default=False)
    closed_at             = models.DateField(null=True, blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        addr = self.display_address
        return f"{self.get_transaction_type_display()} — {addr}"

    @property
    def display_address(self):
        if self.linked_property:
            return self.linked_property.short_address
        return self.property_address or "No address"

    @property
    def days_to_closing(self):
        if self.closing_date:
            return (self.closing_date - timezone.localdate()).days
        return None

    @property
    def overdue_dates(self):
        """Return list of (label, date) tuples that are past and incomplete."""
        today = timezone.localdate()
        checks = [
            ("Inspection", self.inspection_deadline, self.inspection_completed),
            ("Appraisal",  self.appraisal_deadline,  self.appraisal_completed),
            ("Financing",  self.financing_deadline,   self.financing_approved),
            ("Earnest Money", self.earnest_money_due, self.earnest_received),
        ]
        return [
            (label, date)
            for label, date, done in checks
            if date and date < today and not done
        ]

    @property
    def upcoming_dates(self):
        """Return list of (label, date) tuples in the next 14 days."""
        today = timezone.localdate()
        from datetime import timedelta
        window = today + timedelta(days=14)
        all_dates = [
            ("Contract",          self.contract_date),
            ("Earnest Money Due", self.earnest_money_due),
            ("Inspection",        self.inspection_deadline),
            ("Inspection Obj.",   self.inspection_objection_deadline),
            ("Appraisal",         self.appraisal_deadline),
            ("Financing",         self.financing_deadline),
            ("Title",             self.title_deadline),
            ("Closing",           self.closing_date),
            ("Possession",        self.possession_date),
        ]
        return [
            (label, date)
            for label, date in all_dates
            if date and today <= date <= window
        ]


class TransactionChecklistItem(models.Model):
    """A single to-do item attached to a transaction."""

    class Category(models.TextChoices):
        CONTRACT    = "contract",    "Contract"
        INSPECTION  = "inspection",  "Inspection"
        APPRAISAL   = "appraisal",   "Appraisal"
        FINANCING   = "financing",   "Financing"
        TITLE       = "title",       "Title"
        CLOSING     = "closing",     "Closing"
        POST_CLOSE  = "post_close",  "Post-Close"
        OTHER       = "other",       "Other"

    class ItemStatus(models.TextChoices):
        PENDING  = "pending",  "Pending"
        DONE     = "done",     "Done"
        NA       = "na",       "N/A"
        WAIVED   = "waived",   "Waived"

    transaction  = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="checklist_items")
    category     = models.CharField(max_length=15, choices=Category.choices, default=Category.OTHER)
    title        = models.CharField(max_length=255)
    description  = models.TextField(blank=True)
    due_date     = models.DateField(null=True, blank=True)
    assigned_to  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tx_checklist_items",
    )
    is_required  = models.BooleanField(default=True)
    status       = models.CharField(
        max_length=10, choices=ItemStatus.choices, default=ItemStatus.PENDING
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    notes        = models.TextField(blank=True)
    order        = models.SmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "due_date", "title"]

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        return (
            self.status == self.ItemStatus.PENDING
            and self.due_date
            and self.due_date < timezone.localdate()
        )


# ------------------------------------------------------------------ #
# Default checklist items seeded on transaction creation
# ------------------------------------------------------------------ #

BUYER_CHECKLIST = [
    ("contract",   "Execute purchase contract",            0),
    ("contract",   "Collect earnest money",                1),
    ("contract",   "Deliver earnest money to title",       2),
    ("inspection", "Schedule home inspection",             3),
    ("inspection", "Review inspection report",             4),
    ("inspection", "Submit inspection objection",          5),
    ("inspection", "Resolve inspection items",             6),
    ("appraisal",  "Appraisal ordered",                    7),
    ("appraisal",  "Appraisal received",                   8),
    ("appraisal",  "Appraisal meets contract price",       9),
    ("financing",  "Loan application submitted",           10),
    ("financing",  "Loan approval received",               11),
    ("financing",  "Financing contingency removed",        12),
    ("title",      "Title commitment received",            13),
    ("title",      "Review title commitment",              14),
    ("title",      "Title insurance ordered",              15),
    ("closing",    "Final walkthrough scheduled",          16),
    ("closing",    "Final walkthrough completed",          17),
    ("closing",    "Closing disclosure reviewed",          18),
    ("closing",    "Confirm wire transfer instructions",   19),
    ("closing",    "Closing completed",                    20),
    ("post_close", "Confirm keys received",                21),
    ("post_close", "Send thank-you note",                  22),
    ("post_close", "Schedule 30-day check-in",             23),
]

SELLER_CHECKLIST = [
    ("contract",   "Execute listing agreement",            0),
    ("contract",   "Execute purchase contract",            1),
    ("contract",   "Confirm earnest money received",       2),
    ("inspection", "Coordinate access for inspection",     3),
    ("inspection", "Review inspection objection",          4),
    ("inspection", "Negotiate inspection resolution",      5),
    ("appraisal",  "Coordinate access for appraisal",      6),
    ("appraisal",  "Review appraisal",                     7),
    ("title",      "Title commitment received",            8),
    ("title",      "Clear title issues",                   9),
    ("closing",    "Confirm final walkthrough time",       10),
    ("closing",    "Gather keys, garage openers, etc.",    11),
    ("closing",    "Closing completed",                    12),
    ("post_close", "Confirm proceeds received",            13),
    ("post_close", "Send thank-you note",                  14),
    ("post_close", "Request testimonial/review",           15),
    ("post_close", "Schedule home anniversary follow-up",  16),
]


def seed_checklist(transaction):
    """Create default checklist items based on transaction type."""
    items_def = (
        SELLER_CHECKLIST
        if transaction.transaction_type == Transaction.TxType.LISTING
        else BUYER_CHECKLIST
    )
    TransactionChecklistItem.objects.bulk_create([
        TransactionChecklistItem(
            transaction=transaction,
            category=cat,
            title=title,
            order=order,
        )
        for cat, title, order in items_def
    ])


class TransactionNote(models.Model):
    """Notes / activity log on a transaction."""

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="tx_notes")
    author      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    body        = models.TextField()
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class TransactionDocument(OrgScopedModel):
    class Category(models.TextChoices):
        CONTRACT = "contract", "Contract"
        DISCLOSURE = "disclosure", "Disclosure"
        INSPECTION = "inspection", "Inspection"
        APPRAISAL = "appraisal", "Appraisal"
        FINANCING = "financing", "Financing"
        TITLE = "title", "Title"
        CLOSING = "closing", "Closing"
        OTHER = "other", "Other"

    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.OTHER,
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="transactions/documents/%Y/%m/")
    notes = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_transaction_documents",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
