"""Streamlit investigation workspace for payroll anomaly alerts."""

from decimal import Decimal

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.config import get_settings
from database.enums import AlertSource, AlertStatus, InvestigationOutcome, RiskLevel
from database.models import AnomalyAlert
from database.repositories import PayrollRepository
from database.session import create_database_engine, create_session_factory

RISK_ORDER = {
    RiskLevel.CRITICAL: 0,
    RiskLevel.HIGH: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.LOW: 3,
}


@st.cache_resource
def database_factory(database_url: str):
    """Reuse the connection pool while Streamlit reruns the page."""

    return create_session_factory(create_database_engine(database_url))


def render_dashboard() -> None:
    """Render the end-to-end analyst investigation workflow."""

    settings = get_settings()
    st.set_page_config(
        page_title=settings.app_title,
        page_icon="🔎",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _render_styles()
    st.title(settings.app_title)
    st.caption(
        f"Hybrid payroll review workspace · Version {__version__} · {settings.environment.title()}"
    )

    try:
        factory = database_factory(settings.database_url)
        with factory() as session:
            repository = PayrollRepository(session)
            payroll_runs = repository.get_payroll_runs()
            if not payroll_runs:
                _render_empty_state()
                return
            selected_run = _select_payroll_run(payroll_runs)
            alerts = repository.list_alerts(payroll_run_id=selected_run.id)
            filtered_alerts = _filter_alerts(alerts)
            _render_metrics(filtered_alerts)
            if not filtered_alerts:
                st.info("No alerts match the selected filters.")
                return
            selected_alert = _render_alert_queue(filtered_alerts)
            _render_alert_details(repository, selected_alert)
            _render_investigation_form(repository, selected_alert)
    except SQLAlchemyError as error:
        st.error("The payroll database is not available.")
        st.code("docker compose up --build", language="powershell")
        with st.expander("Technical details"):
            st.text(str(error))


def _select_payroll_run(payroll_runs):
    st.sidebar.header("Review scope")
    run_by_label = {
        f"{payroll_run.period_start:%b %Y} · paid {payroll_run.payment_date:%d %b}": payroll_run
        for payroll_run in payroll_runs
    }
    selected_label = st.sidebar.selectbox("Payroll run", list(run_by_label))
    return run_by_label[selected_label]


def _filter_alerts(alerts: list[AnomalyAlert]) -> list[AnomalyAlert]:
    risk_options = [level.value for level in RiskLevel]
    source_options = [source.value for source in AlertSource]
    status_options = [status.value for status in AlertStatus]
    selected_risks = st.sidebar.multiselect("Risk level", risk_options, default=risk_options)
    selected_sources = st.sidebar.multiselect(
        "Detection source", source_options, default=source_options
    )
    selected_statuses = st.sidebar.multiselect("Status", status_options, default=status_options)
    departments = sorted({alert.payment.employee.department for alert in alerts})
    selected_departments = st.sidebar.multiselect("Department", departments, default=departments)

    filtered = [
        alert
        for alert in alerts
        if alert.risk_level.value in selected_risks
        and alert.source.value in selected_sources
        and alert.status.value in selected_statuses
        and alert.payment.employee.department in selected_departments
    ]
    return sorted(
        filtered,
        key=lambda alert: (RISK_ORDER[alert.risk_level], -alert.risk_score),
    )


def _render_metrics(alerts: list[AnomalyAlert]) -> None:
    review_value = sum((alert.payment.net_pay for alert in alerts), Decimal("0"))
    urgent = sum(alert.risk_level in {RiskLevel.CRITICAL, RiskLevel.HIGH} for alert in alerts)
    open_count = sum(alert.status == AlertStatus.OPEN for alert in alerts)
    resolved_count = sum(alert.status == AlertStatus.RESOLVED for alert in alerts)
    columns = st.columns(4)
    columns[0].metric("Alerts in view", len(alerts))
    columns[1].metric("Critical / high", urgent)
    columns[2].metric("Value under review", _compact_currency(review_value))
    columns[3].metric("Open / resolved", f"{open_count} / {resolved_count}")


def _render_alert_queue(alerts: list[AnomalyAlert]) -> AnomalyAlert:
    st.subheader("Prioritised alert queue")
    table = pd.DataFrame(
        [
            {
                "Risk": alert.risk_level.value.title(),
                "Score": round(alert.risk_score, 3),
                "Employee": alert.payment.employee.employee_code,
                "Department": alert.payment.employee.department,
                "Net pay": float(alert.payment.net_pay),
                "Source": alert.source.value.title(),
                "Status": alert.status.value.replace("_", " ").title(),
                "Reason": alert.summary,
            }
            for alert in alerts
        ]
    )
    st.dataframe(
        table,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Net pay": st.column_config.NumberColumn(format="£%.2f"),
            "Score": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0),
        },
    )
    alert_by_id = {alert.id: alert for alert in alerts}
    selected_id = st.selectbox(
        "Open alert",
        list(alert_by_id),
        format_func=lambda alert_id: _alert_label(alert_by_id[alert_id]),
    )
    return alert_by_id[selected_id]


def _render_alert_details(
    repository: PayrollRepository,
    alert: AnomalyAlert,
) -> None:
    payment = alert.payment
    employee = payment.employee
    st.divider()
    st.subheader(f"{alert.risk_level.value.title()} risk · {employee.employee_code}")
    st.write(alert.summary)

    employee_column, payment_column, peer_column = st.columns(3)
    with employee_column:
        st.markdown("**Employee context**")
        st.write(employee.job_title)
        st.caption(f"{employee.department} · {employee.job_grade} · {employee.location}")
        st.caption(f"Employment status: {employee.employment_status.value.title()}")
    with payment_column:
        st.markdown("**Payment context**")
        st.write(f"Gross: {_currency(payment.gross_pay)}")
        st.caption(f"Deductions: {_currency(payment.total_deductions)}")
        st.caption(f"Net: {_currency(payment.net_pay)}")
    with peer_column:
        peer_payments = [
            peer
            for peer in repository.get_payments_for_run(payment.payroll_run_id)
            if peer.employee.department == employee.department
            and peer.employee.job_grade == employee.job_grade
        ]
        peer_median = (
            pd.Series([float(peer.gross_pay) for peer in peer_payments]).median()
            if peer_payments
            else float(payment.gross_pay)
        )
        variance = float(payment.gross_pay) / peer_median - 1 if peer_median else 0
        st.markdown("**Peer comparison**")
        st.write(f"Peer median: {_currency(peer_median)}")
        st.caption(f"This payment is {variance:+.1%} versus comparable peers.")

    history = repository.get_employee_payment_history(employee.id)
    history_frame = pd.DataFrame(
        [
            {
                "Period": historical.payroll_run.period_end,
                "Gross pay": float(historical.gross_pay),
                "Net pay": float(historical.net_pay),
            }
            for historical in history
        ]
    ).set_index("Period")
    st.markdown("**Payment history**")
    st.line_chart(history_frame, use_container_width=True)

    _render_evidence(alert)
    _render_history(alert)


def _render_evidence(alert: AnomalyAlert) -> None:
    st.markdown("**Why this alert exists**")
    rule_findings = alert.evidence.get("rule_findings", [])
    for finding in rule_findings:
        with st.expander(f"{finding['rule_code']} · score {finding['risk_score']:.2f}"):
            st.write(finding["summary"])
            st.json(finding["evidence"])

    model = alert.evidence.get("model", {})
    if model.get("risk_score") is not None:
        with st.expander(
            f"Isolation Forest signal · score {model['risk_score']:.2f}",
            expanded=not rule_findings,
        ):
            st.caption("This is an anomaly ranking signal, not a probability of fraud or error.")
            for reason in model.get("reasons", []):
                st.write(f"• {reason['explanation']}")


def _render_history(alert: AnomalyAlert) -> None:
    if not alert.investigations:
        return
    st.markdown("**Investigation history**")
    for investigation in sorted(alert.investigations, key=lambda item: item.created_at):
        st.write(
            f"{investigation.outcome.value.replace('_', ' ').title()} · "
            f"{investigation.investigator}"
        )
        st.caption(investigation.notes)


def _render_investigation_form(
    repository: PayrollRepository,
    alert: AnomalyAlert,
) -> None:
    st.subheader("Record an investigation outcome")
    with st.form(f"investigation-{alert.id}", clear_on_submit=True):
        outcome_value = st.selectbox(
            "Outcome",
            [outcome.value for outcome in InvestigationOutcome],
            format_func=lambda value: value.replace("_", " ").title(),
        )
        investigator = st.text_input("Investigator", value="Portfolio reviewer")
        notes = st.text_area("Notes", placeholder="Document the evidence considered.")
        submitted = st.form_submit_button("Save outcome", type="primary")
    if submitted:
        if not investigator.strip() or not notes.strip():
            st.warning("Investigator and notes are required.")
            return
        repository.record_investigation(
            alert,
            outcome=InvestigationOutcome(outcome_value),
            notes=notes,
            investigator=investigator,
        )
        repository.session.commit()
        st.success("Investigation outcome saved.")
        st.rerun()


def _render_empty_state() -> None:
    st.info("The database is connected but contains no payroll runs.")
    st.code(
        "python scripts/init_db.py\npython scripts/bootstrap_demo.py",
        language="powershell",
    )


def _render_styles() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.045);
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 0.75rem;
            padding: 0.9rem;
        }
        [data-testid="stSidebar"] {
            border-right: 1px solid rgba(255, 255, 255, 0.14);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _alert_label(alert: AnomalyAlert) -> str:
    return (
        f"{alert.risk_level.value.upper()} · {alert.payment.employee.employee_code} · "
        f"{alert.summary}"
    )


def _currency(value: Decimal | float) -> str:
    return f"£{float(value):,.2f}"


def _compact_currency(value: Decimal | float) -> str:
    amount = float(value)
    return f"£{amount / 1000:.1f}k" if abs(amount) >= 10_000 else _currency(amount)


if __name__ == "__main__":
    render_dashboard()
