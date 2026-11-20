"""Máquina de estados da denúncia (docs/maquina-de-estados.md)."""

from apps.core.state_machine import StateMachine
from apps.reports.models import Report

R = Report.Status

REPORT_MACHINE = StateMachine(
    "Report",
    {
        R.OPEN: {R.REVIEWING, R.UPHELD, R.DISMISSED},
        R.REVIEWING: {R.UPHELD, R.DISMISSED},
        R.UPHELD: set(),
        R.DISMISSED: set(),
    },
)
