from django.urls import path

from . import profile_views, public_views, views

urlpatterns = [
    path("cnpj/<str:cnpj>/", views.CnpjLookupView.as_view(), name="cnpj-lookup"),
    path("companies/register/", views.CompanyRegisterView.as_view(), name="company-register"),
    path("companies/me/", profile_views.CompanyMeView.as_view(), name="company-me"),
    path("companies/me/logo/", profile_views.CompanyLogoView.as_view(), name="company-logo"),
    path(
        "companies/<int:pk>/logo/",
        profile_views.CompanyLogoFileView.as_view(),
        name="company-logo-file",
    ),
    path(
        "companies/<int:pk>/public/",
        public_views.CompanyPublicView.as_view(),
        name="company-public",
    ),
]
