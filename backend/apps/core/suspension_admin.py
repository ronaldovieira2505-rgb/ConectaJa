"""Telas do painel admin para suspender e reativar contas (US76)."""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.accounts.models import Role
from apps.core.exceptions import DomainError
from apps.core.suspension import MAX_DAYS, MIN_DAYS, reactivate_account, suspend_account


class SuspendForm(forms.Form):
    reason = forms.CharField(label="Motivo", widget=forms.Textarea(attrs={"rows": 3}))
    days = forms.IntegerField(
        label="Dias de suspensão",
        min_value=MIN_DAYS,
        max_value=MAX_DAYS,
        required=False,
        help_text=f"De {MIN_DAYS} a {MAX_DAYS}. Deixe em branco se for por tempo indeterminado.",
    )
    indefinite = forms.BooleanField(label="Por tempo indeterminado", required=False)

    def clean_reason(self):
        reason = self.cleaned_data["reason"].strip()
        if not reason:
            raise forms.ValidationError("O motivo é obrigatório.")
        return reason

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("indefinite") and cleaned.get("days") is not None:
            raise forms.ValidationError("Informe os dias ou tempo indeterminado, não os dois.")
        if not cleaned.get("indefinite") and cleaned.get("days") is None:
            raise forms.ValidationError("Informe o número de dias ou marque tempo indeterminado.")
        return cleaned


class ReactivateForm(forms.Form):
    reason = forms.CharField(label="Motivo", widget=forms.Textarea(attrs={"rows": 3}))

    def clean_reason(self):
        reason = self.cleaned_data["reason"].strip()
        if not reason:
            raise forms.ValidationError("O motivo é obrigatório.")
        return reason


class SuspensionAdminMixin:
    """Acrescenta as telas “Suspender conta” e “Reativar conta” a um ModelAdmin."""

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name
        custom = [
            path(
                "<int:pk>/suspender/",
                self.admin_site.admin_view(self.suspend_view),
                name="%s_%s_suspend" % info,
            ),
            path(
                "<int:pk>/reativar/",
                self.admin_site.admin_view(self.reactivate_view),
                name="%s_%s_reactivate" % info,
            ),
        ]
        return custom + super().get_urls()

    @admin.display(description="Suspensão")
    def suspension_actions(self, obj):
        info = self.model._meta.app_label, self.model._meta.model_name
        if obj.is_suspended(timezone.now()):
            url = reverse("admin:%s_%s_reactivate" % info, args=[obj.pk])
            return format_html('<a href="{}">Reativar conta</a>', url)
        url = reverse("admin:%s_%s_suspend" % info, args=[obj.pk])
        return format_html('<a href="{}">Suspender conta</a>', url)

    def _require_admin(self, request):
        if request.user.role != Role.ADMIN:
            raise PermissionDenied

    def _run(self, request, pk, *, form_class, action, title, success):
        self._require_admin(request)
        subject = get_object_or_404(self.model, pk=pk)
        changelist = reverse(
            "admin:%s_%s_changelist" % (self.model._meta.app_label, self.model._meta.model_name)
        )
        form = form_class(request.POST or None)
        if request.method == "POST" and form.is_valid():
            try:
                action(subject, actor=request.user, **form.cleaned_data)
            except DomainError as error:
                self.message_user(request, str(error), messages.ERROR)
            else:
                self.message_user(request, success, messages.SUCCESS)
                return HttpResponseRedirect(changelist)
        context = {
            **self.admin_site.each_context(request),
            "title": f"{title} — {subject}",
            "form": form,
            "subject": subject,
            "back_url": changelist,
        }
        return TemplateResponse(request, "admin/core/suspension_form.html", context)

    def suspend_view(self, request, pk):
        return self._run(
            request,
            pk,
            form_class=SuspendForm,
            action=suspend_account,
            title="Suspender conta",
            success="Conta suspensa.",
        )

    def reactivate_view(self, request, pk):
        return self._run(
            request,
            pk,
            form_class=ReactivateForm,
            action=reactivate_account,
            title="Reativar conta",
            success="Conta reativada.",
        )
