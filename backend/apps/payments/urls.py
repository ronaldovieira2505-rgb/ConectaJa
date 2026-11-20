from django.urls import path

from . import wallet_views

urlpatterns = [
    path("workers/me/wallet/", wallet_views.WorkerWalletView.as_view(), name="worker-wallet"),
    path(
        "workers/me/statement.csv",
        wallet_views.WorkerStatementView.as_view(),
        name="worker-statement",
    ),
]
