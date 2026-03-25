from django.contrib import admin

from .models import Transaction, TransactionChecklistItem, TransactionDocument, TransactionNote


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["display_address", "transaction_type", "status", "organization", "created_at"]
    list_filter = ["transaction_type", "status", "organization"]
    search_fields = ["property_address", "mls_number"]


@admin.register(TransactionChecklistItem)
class TransactionChecklistItemAdmin(admin.ModelAdmin):
    list_display = ["title", "transaction", "category", "status", "due_date", "assigned_to"]
    list_filter = ["category", "status", "is_required"]
    search_fields = ["title", "transaction__property_address"]


@admin.register(TransactionNote)
class TransactionNoteAdmin(admin.ModelAdmin):
    list_display = ["transaction", "author", "created_at"]
    search_fields = ["transaction__property_address", "body"]


@admin.register(TransactionDocument)
class TransactionDocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "transaction", "category", "uploaded_by", "created_at"]
    list_filter = ["category", "organization"]
    search_fields = ["title", "transaction__property_address"]
