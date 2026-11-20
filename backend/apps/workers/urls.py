from django.urls import path

from . import deletion_views, portfolio_views, views

urlpatterns = [
    path(
        "workers/me/portfolio/",
        portfolio_views.WorkerPortfolioView.as_view(),
        name="worker-portfolio",
    ),
    path(
        "workers/me/portfolio/<int:pk>/",
        portfolio_views.WorkerPortfolioItemView.as_view(),
        name="worker-portfolio-item",
    ),
    path(
        "workers/portfolio/<int:pk>/file/",
        portfolio_views.PortfolioFileView.as_view(),
        name="worker-portfolio-file",
    ),
    path("workers/me/delete/", deletion_views.WorkerDeleteView.as_view(), name="worker-delete"),
    path("workers/register/", views.WorkerRegisterView.as_view(), name="worker-register"),
    path("workers/me/", views.WorkerMeView.as_view(), name="worker-me"),
    path("workers/me/documents/", views.WorkerDocumentsView.as_view(), name="worker-documents"),
    path("workers/me/pix/", views.WorkerPixView.as_view(), name="worker-pix"),
    path(
        "workers/<int:worker_id>/documents/<str:kind>/",
        views.WorkerDocumentFileView.as_view(),
        name="worker-document-file",
    ),
]
