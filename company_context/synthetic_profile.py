"""Synthetic company context used only for pipeline development."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


SYNTHETIC_CONTEXT_WARNING = (
    "This company profile contains synthetic, unverified testing data. "
    "It must not be used for an actual tender qualification, scoring, "
    "bid, or no-bid decision."
)


SYNTHETIC_COMPANY_PROFILE: dict[str, Any] = {
    "profile_type": "synthetic_unverified",
    "production_decision_allowed": False,
    "warning": SYNTHETIC_CONTEXT_WARNING,
    "company": {
        "legal_name": "Example Digital Services Private Limited",
        "entity_type": "private_limited_company",
        "incorporation_year": 2012,
        "country": "India",
        "head_office_location": "Gurugram, Haryana",
        "operating_locations": [
            "Haryana",
            "Delhi NCR",
            "Punjab",
            "Uttar Pradesh",
        ],
    },
    "registrations": [
        {
            "name": "Permanent Account Number",
            "short_name": "PAN",
            "available": True,
            "verified": False,
            "reference": "synthetic.registrations.pan",
        },
        {
            "name": "Goods and Services Tax Registration",
            "short_name": "GST",
            "available": True,
            "verified": False,
            "reference": "synthetic.registrations.gst",
        },
        {
            "name": "Certificate of Incorporation",
            "short_name": "COI",
            "available": True,
            "verified": False,
            "reference": "synthetic.registrations.incorporation",
        },
        {
            "name": "Employees Provident Fund Registration",
            "short_name": "EPF",
            "available": True,
            "verified": False,
            "reference": "synthetic.registrations.epf",
        },
        {
            "name": "Employees State Insurance Registration",
            "short_name": "ESI",
            "available": True,
            "verified": False,
            "reference": "synthetic.registrations.esi",
        },
    ],
    "certifications": [
        {
            "name": "ISO 9001",
            "status": "valid",
            "scope": "Quality management system",
            "expiry_date": None,
            "verified": False,
            "reference": "synthetic.certifications.iso_9001",
        },
        {
            "name": "ISO 27001",
            "status": "valid",
            "scope": "Information security management system",
            "expiry_date": None,
            "verified": False,
            "reference": "synthetic.certifications.iso_27001",
        },
        {
            "name": "ISO 20000-1",
            "status": "valid",
            "scope": "IT service management system",
            "expiry_date": None,
            "verified": False,
            "reference": "synthetic.certifications.iso_20000",
        },
        {
            "name": "CMMI Level 3",
            "status": "valid",
            "scope": "Software development and delivery processes",
            "expiry_date": None,
            "verified": False,
            "reference": "synthetic.certifications.cmmi_level_3",
        },
    ],
    "financials": {
        "currency": "INR",
        "financial_years": [
            {
                "financial_year": "2023-24",
                "annual_turnover_crore": 68.0,
                "net_worth_crore": 24.0,
                "profit_after_tax_crore": 5.2,
                "audited": True,
                "verified": False,
                "reference": "synthetic.financials.2023_24",
            },
            {
                "financial_year": "2024-25",
                "annual_turnover_crore": 76.0,
                "net_worth_crore": 28.0,
                "profit_after_tax_crore": 6.1,
                "audited": True,
                "verified": False,
                "reference": "synthetic.financials.2024_25",
            },
            {
                "financial_year": "2025-26",
                "annual_turnover_crore": 84.0,
                "net_worth_crore": 32.0,
                "profit_after_tax_crore": 7.4,
                "audited": True,
                "verified": False,
                "reference": "synthetic.financials.2025_26",
            },
        ],
        "average_turnover_last_three_years_crore": 76.0,
        "positive_net_worth": True,
        "profitable_financial_years": 3,
        "verified": False,
    },
    "organization": {
        "total_employees": 220,
        "technical_employees": 160,
        "project_management_employees": 18,
        "support_employees": 30,
        "verified": False,
        "reference": "synthetic.organization.employee_strength",
    },
    "experience_summary": {
        "years_in_business": 14,
        "government_projects_completed": 14,
        "government_projects_in_progress": 4,
        "portal_projects_completed": 8,
        "managed_service_projects_completed": 6,
        "verified": False,
    },
    "projects": [
        {
            "project_id": "SYN-PROJ-001",
            "title": "Government Service Delivery Portal",
            "client_type": "state_government",
            "sector": "citizen_services",
            "scope": [
                "Web portal development",
                "Workflow automation",
                "Department integrations",
                "Citizen authentication",
                "Reporting dashboards",
                "Operations and maintenance",
            ],
            "contract_value_crore": 8.5,
            "start_date": "2021-04-01",
            "completion_date": "2023-03-31",
            "status": "completed",
            "completion_certificate_available": True,
            "work_order_available": True,
            "verified": False,
            "reference": "synthetic.projects.syn_proj_001",
        },
        {
            "project_id": "SYN-PROJ-002",
            "title": "State Scheme Management Platform",
            "client_type": "state_government",
            "sector": "government_schemes",
            "scope": [
                "Scheme configuration",
                "Beneficiary registration",
                "Application processing",
                "Document verification",
                "Payment-system integration",
                "Analytics and reporting",
            ],
            "contract_value_crore": 12.0,
            "start_date": "2020-07-01",
            "completion_date": "2023-06-30",
            "status": "completed",
            "completion_certificate_available": True,
            "work_order_available": True,
            "verified": False,
            "reference": "synthetic.projects.syn_proj_002",
        },
        {
            "project_id": "SYN-PROJ-003",
            "title": "Citizen Grievance Management System",
            "client_type": "government_department",
            "sector": "public_grievance",
            "scope": [
                "Omnichannel grievance intake",
                "Workflow management",
                "Escalation management",
                "SLA monitoring",
                "Department dashboards",
                "Mobile-responsive portal",
            ],
            "contract_value_crore": 6.2,
            "start_date": "2022-01-01",
            "completion_date": "2024-01-31",
            "status": "completed",
            "completion_certificate_available": True,
            "work_order_available": True,
            "verified": False,
            "reference": "synthetic.projects.syn_proj_003",
        },
        {
            "project_id": "SYN-PROJ-004",
            "title": "Government Data Analytics and MIS Platform",
            "client_type": "public_sector_organization",
            "sector": "data_analytics",
            "scope": [
                "Data integration",
                "Management information system",
                "Executive dashboards",
                "Role-based access control",
                "Automated reports",
                "Data-quality monitoring",
            ],
            "contract_value_crore": 5.4,
            "start_date": "2023-02-01",
            "completion_date": "2025-02-28",
            "status": "completed",
            "completion_certificate_available": True,
            "work_order_available": True,
            "verified": False,
            "reference": "synthetic.projects.syn_proj_004",
        },
    ],
    "personnel": [
        {
            "role": "Project Manager",
            "available_count": 4,
            "minimum_experience_years": 10,
            "qualifications": [
                "B.Tech",
                "MBA",
                "PMP",
            ],
            "verified": False,
            "reference": "synthetic.personnel.project_manager",
        },
        {
            "role": "Solution Architect",
            "available_count": 3,
            "minimum_experience_years": 10,
            "qualifications": [
                "B.Tech",
                "Cloud architecture certification",
            ],
            "verified": False,
            "reference": "synthetic.personnel.solution_architect",
        },
        {
            "role": "Business Analyst",
            "available_count": 8,
            "minimum_experience_years": 5,
            "qualifications": [
                "B.Tech",
                "MBA",
            ],
            "verified": False,
            "reference": "synthetic.personnel.business_analyst",
        },
        {
            "role": "Software Developer",
            "available_count": 65,
            "minimum_experience_years": 3,
            "qualifications": [
                "B.Tech",
                "MCA",
                "M.Tech",
            ],
            "verified": False,
            "reference": "synthetic.personnel.software_developer",
        },
        {
            "role": "Database Administrator",
            "available_count": 5,
            "minimum_experience_years": 5,
            "qualifications": [
                "B.Tech",
                "MCA",
                "Database certification",
            ],
            "verified": False,
            "reference": "synthetic.personnel.database_administrator",
        },
        {
            "role": "Information Security Specialist",
            "available_count": 3,
            "minimum_experience_years": 6,
            "qualifications": [
                "B.Tech",
                "Information security certification",
            ],
            "verified": False,
            "reference": "synthetic.personnel.security_specialist",
        },
    ],
    "technical_capabilities": [
        "Web application development",
        "Mobile application development",
        "Cloud deployment",
        "API development and integration",
        "Workflow automation",
        "Data analytics and dashboards",
        "Document management",
        "Identity and access management",
        "Operations and maintenance",
        "Help-desk support",
        "Information security implementation",
    ],
    "legal_declarations": {
        "currently_blacklisted": False,
        "insolvency_proceedings": False,
        "conflict_of_interest_declared": False,
        "verified": False,
        "reference": "synthetic.legal_declarations",
    },
    "evidence_availability": {
        "audited_financial_statements": True,
        "turnover_certificate": True,
        "net_worth_certificate": True,
        "work_orders": True,
        "completion_certificates": True,
        "client_certificates": True,
        "employee_cv_documents": True,
        "certification_documents": True,
        "legal_declarations": True,
        "verified": False,
    },
}


def get_synthetic_company_profile() -> dict[str, Any]:
    """
    Return an isolated copy of the synthetic company profile.

    A deep copy prevents callers from changing the module-level profile.
    """

    return deepcopy(SYNTHETIC_COMPANY_PROFILE)


def get_synthetic_context_warning() -> str:
    """Return the mandatory warning attached to synthetic assessments."""

    return SYNTHETIC_CONTEXT_WARNING


def validate_synthetic_profile(
    profile: dict[str, Any],
) -> None:
    """Validate mandatory safety markers in a synthetic profile."""

    if profile.get("profile_type") != "synthetic_unverified":
        raise ValueError(
            "Synthetic profile must use the "
            "'synthetic_unverified' profile type."
        )

    if profile.get("production_decision_allowed") is not False:
        raise ValueError(
            "Synthetic profile must prohibit production decisions."
        )

    if not profile.get("warning"):
        raise ValueError(
            "Synthetic profile must include a visible warning."
        )

    company = profile.get("company")

    if not isinstance(company, dict):
        raise ValueError(
            "Synthetic profile must contain company information."
        )

    if not company.get("legal_name"):
        raise ValueError(
            "Synthetic profile must contain a company legal name."
        )