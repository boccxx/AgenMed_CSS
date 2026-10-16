#!/usr/bin/env python3
from __future__ import annotations

import json
import pandas as pd
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CANONICAL_PROJECT_MODES = {"research", "applied_methods", "workflow_methods"}
LEGACY_PROJECT_MODE_ALIASES = {
    "simulation": "applied_methods",
    "methods_demo": "workflow_methods",
}


def normalize_project_mode(value: object, *, default: str = "research") -> str:
    raw = str(value or default).strip()
    canonical = LEGACY_PROJECT_MODE_ALIASES.get(raw, raw)
    if canonical not in CANONICAL_PROJECT_MODES:
        allowed = ", ".join(sorted(CANONICAL_PROJECT_MODES | set(LEGACY_PROJECT_MODE_ALIASES)))
        raise ValueError(f"project_mode '{raw}' is not valid; expected one of: {allowed}")
    return canonical


STAGE_ORDER = [
    "qc_stage",
    "missingness_stage",
    "descriptive_stage",
    "bivariate_stage",
    "primary_model_stage",
    "interaction_stage",
    "dose_response_stage",
    "sensitivity_stage",
    "registry_finalize_stage",
    "report_stage",
]

STAGE_STATUS_VALUES = {
    "required",
    "conditional",
    "not_applicable",
    "blocked_by_data",
    "degraded_with_deviation",
}

PATH_MODE_VALUES = {"full", "simplified", "degraded"}

MAINLINE_FAMILIES = {
    "prevalence_descriptive",
    "binary_pr",
    "binary_or",
    "binary_sparse_robust",
    "continuous_linear",
    "continuous_mi_weighted",
    "ordinal_clm",
    "interaction_bundle",
    "dose_response_bundle",
    "sensitivity_bundle",
    "adjusted_predictions",
    "marginal_effects",
    "balance_assessment",
    "diagnostic_bundle",
}

COMMON_EXTENDED_FAMILIES = {
    "multinomial_nominal",
    "bounded_proportion",
    "clustered_gee",
    "clustered_mixed",
    "count_outcome",
    "zero_inflated_count",
    "domain_analysis",
    "calibration_performance",
}

SPECIALIZED_EXTENDED_FAMILIES = {
    "mediation",
    "sem",
    "lca",
    "psm",
    "evalue",
    "agreement_reliability",
    "pca_factor_scale",
    "ecological_spatial",
    "advanced_causal_sensitivity",
    "bayesian_ml_highdim",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower().replace("_", " ").replace("-", " ")).strip()


def slugify(text: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", normalize(text)).strip("_")
    return slug[:60] or fallback


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def load_structured(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {} if default is None else default
    return json.loads(text)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def discover_data_csv(project_root: Path) -> Path | None:
    direct = project_root / "data" / "study_dataset.csv"
    if direct.exists():
        return direct
    candidates = sorted((project_root / "data").glob("*.csv")) if (project_root / "data").exists() else []
    return candidates[0] if candidates else None


def discover_inputs(project_root: Path) -> dict[str, Path | None]:
    contracts_dir = project_root / "contracts"
    protocol_dir = project_root / "protocol"
    return {
        "intake_json": first_existing(
            [
                project_root / "intake.json",
                project_root / "analysis" / "intake.json",
            ]
        ),
        "protocol_contract": first_existing(
            [
                contracts_dir / "protocol_contract.json",
                protocol_dir / "protocol_contract.json",
            ]
        ),
        "sap_contract": first_existing(
            [
                contracts_dir / "sap_contract.json",
                protocol_dir / "sap_contract.json",
            ]
        ),
        "design_intake_v2": first_existing(
            [
                contracts_dir / "design_intake_v2.json",
                protocol_dir / "design_intake_v2.json",
                project_root / "design_intake_v2.json",
            ]
        ),
        "data_csv": discover_data_csv(project_root),
        "data_profile": first_existing(
            [
                project_root / "analysis" / "profile" / "data_profile.json",
                project_root / "analysis" / "output" / "data_profile.json",
            ]
        ),
    }


def ensure_data_profile(project_root: Path, explicit_csv: Path | None = None) -> tuple[dict, Path | None]:
    discovered = discover_inputs(project_root)
    profile_path = discovered["data_profile"]
    if profile_path:
        return load_json(profile_path), profile_path

    data_csv = explicit_csv or discovered["data_csv"]
    if not data_csv:
        return {"file": "", "schema": [], "n_columns": 0, "sample_rows_read": 0}, None

    payload = profile_csv(data_csv)
    out = project_root / "analysis" / "profile" / "data_profile.json"
    write_json(out, payload)
    return payload, out


def detect_design_columns(profile: dict) -> dict[str, str]:
    columns = [item["name"] for item in profile.get("schema", [])]

    def first_match(tokens: list[str]) -> str:
        for column in columns:
            lowered = normalize(column)
            if any(token in lowered for token in tokens):
                return column
        return ""

    return {
        "weight_variable": first_match(["weight", "wt"]),
        "strata_variable": first_match(["strata", "stratum"]),
        "psu_variable": first_match(["psu", "cluster", "primary sampling"]),
    }


def find_variable_info(profile: dict, variable: str) -> dict:
    for item in profile.get("schema", []):
        if item.get("name") == variable:
            return item
    return {}


def is_integer_like(variable_info: dict) -> bool:
    return bool(variable_info.get("integer_like"))


def is_bounded(variable_info: dict) -> bool:
    return bool(variable_info.get("proportion_candidate"))


def is_count_like(variable_info: dict) -> bool:
    return bool(variable_info.get("count_candidate"))


def infer_outcome_family(variable_info: dict, objective: dict) -> str:
    if objective.get("primary_outcome_family"):
        return normalize(objective["primary_outcome_family"]).replace(" ", "_")
    if objective.get("objective_type") == "prevalence":
        return "prevalence"

    explicit = normalize(
        " ".join(
            [
                objective.get("analysis_family", ""),
                objective.get("requested_method_family", ""),
                objective.get("effect_measure", ""),
            ]
        )
    )
    if "multinomial" in explicit or "nominal" in explicit:
        return "multinomial"
    if "beta regression" in explicit or "bounded" in explicit or "proportion" in explicit:
        return "bounded"
    if "zero inflated" in explicit or "hurdle" in explicit:
        return "zero_inflated_count"
    if "gee" in explicit or "cluster" in explicit or "mixed" in explicit:
        return "clustered"
    if any(token in explicit for token in ["prevalence ratio", "odds ratio", "risk ratio"]):
        return "binary"
    if "count" in explicit or "negative binomial" in explicit:
        return "count"
    if "ordinal" in explicit:
        return "ordinal"
    if "continuous" in explicit or "linear" in explicit:
        return "continuous"

    dtype = normalize(variable_info.get("dtype", ""))
    n_unique = int(variable_info.get("n_unique", 0) or 0)
    if n_unique <= 2:
        return "binary"
    if is_bounded(variable_info):
        return "bounded"
    if is_count_like(variable_info):
        return "count"
    if "float" in dtype or "double" in dtype:
        return "continuous"
    if 3 <= n_unique <= 6 and not is_integer_like(variable_info):
        return "multinomial"
    if 3 <= n_unique <= 7:
        return "ordinal"
    return "continuous"


def infer_exposure_form(variable_info: dict, objective: dict) -> str:
    explicit = normalize(objective.get("exposure", "") or objective.get("primary_exposure_form", ""))
    if "continuous" in explicit:
        return "continuous"
    if "ordinal" in explicit or "quartile" in explicit:
        return "ordinal"
    if "binary" in explicit or "dichotom" in explicit:
        return "binary"
    if "count" in explicit:
        return "count"
    if "proportion" in explicit or "percent" in explicit:
        return "continuous"

    dtype = normalize(variable_info.get("dtype", ""))
    n_unique = int(variable_info.get("n_unique", 0) or 0)
    if n_unique <= 2:
        return "binary"
    if n_unique <= 10 and is_integer_like(variable_info):
        return "ordinal"
    if "float" in dtype or n_unique > 10:
        return "continuous"
    return "categorical"


def objective_from_architect_v2(protocol_contract: dict) -> list[dict]:
    return protocol_contract.get("study_objectives", [])


def objective_from_legacy(protocol_contract: dict, sap_contract: dict) -> list[dict]:
    if not protocol_contract:
        return []
    effect_measure = "prevalence ratio" if "prevalence ratio" in normalize(sap_contract.get("primary_estimand", "")) else "odds ratio"
    analysis_family = "modified Poisson regression" if effect_measure == "prevalence ratio" else "logistic regression"
    return [
        {
            "objective_id": "OBJ1",
            "priority": "primary",
            "objective_type": "association",
            "framework": protocol_contract.get("framework", "PECO"),
            "purpose": protocol_contract.get("primary_question", ""),
            "population": protocol_contract.get("population", protocol_contract.get("target_population", "")),
            "exposure": protocol_contract.get("exposure", ""),
            "comparison": protocol_contract.get("comparison", ""),
            "outcome": protocol_contract.get("outcome", ""),
            "effect_measure": effect_measure,
            "analysis_family": analysis_family,
            "hypothesis_policy": "formal",
            "reporting_role": "main_text",
            "requires_causal_language": False,
            "table_figure_targets": [],
            "adjustment_strategy": {
                "adjustment_set": [
                    row["variable"]
                    for row in protocol_contract.get("variable_roles", [])
                    if "adjustment" in normalize(row.get("planned_analysis_role", ""))
                ]
            },
            "diagnostics": sap_contract.get("diagnostic_plan", []),
            "sensitivity_analyses": sap_contract.get("extended_package", []),
            "interaction_candidates": [
                row["variable"]
                for row in protocol_contract.get("variable_roles", [])
                if "interaction" in normalize(row.get("planned_analysis_role", ""))
                or "modifier" in normalize(row.get("role", ""))
            ],
            "missing_data_strategy": sap_contract.get("missing_data_strategy", ""),
            "primary_model": sap_contract.get("primary_model", ""),
        }
    ]


def load_objectives(project_root: Path, protocol_contract: dict, design_intake: dict, sap_contract: dict) -> list[dict]:
    if design_intake.get("study_objectives"):
        return design_intake["study_objectives"]
    if protocol_contract.get("study_objectives"):
        return objective_from_architect_v2(protocol_contract)
    return objective_from_legacy(protocol_contract, sap_contract)


def resolve_method_family(outcome_family: str, effect_measure: str, analysis_family: str = "") -> str:
    explicit = normalize(analysis_family)
    effect = normalize(effect_measure)
    family = normalize(outcome_family)

    if "multinomial" in explicit or family == "multinomial":
        return "multinomial_nominal"
    if "beta regression" in explicit or family == "bounded":
        return "bounded_proportion"
    if "zero inflated" in explicit or family == "zero_inflated_count":
        return "zero_inflated_count"
    if "gee" in explicit or "cluster" in explicit or family == "clustered":
        return "clustered_gee"
    if family == "count":
        return "count_outcome"
    if family == "prevalence":
        return "prevalence_descriptive"
    if family == "continuous":
        return "continuous_linear"
    if family == "ordinal":
        return "ordinal_clm"
    if effect == "prevalence ratio":
        return "binary_pr"
    if effect == "odds ratio":
        return "binary_or"
    return "binary_pr"


def primary_method_id(method_family: str) -> str:
    mapping = {
        "prevalence_descriptive": "weighted_table1_nonnormal_smd",
        "binary_pr": "weighted_modified_poisson_pr",
        "binary_or": "logistic_regression_or",
        "binary_sparse_robust": "weighted_modified_poisson_pr",
        "continuous_linear": "weighted_linear_model",
        "continuous_mi_weighted": "mi_survey_pooling_wrapper",
        "ordinal_clm": "ordinal_model",
        "multinomial_nominal": "multinomial_nominal_model",
        "bounded_proportion": "bounded_proportion_model",
        "clustered_gee": "clustered_gee_model",
        "clustered_mixed": "clustered_gee_model",
        "count_outcome": "count_outcome_model",
        "zero_inflated_count": "zero_inflated_count_model",
    }
    return mapping.get(method_family, "weighted_modified_poisson_pr")


def method_tier(method_family: str) -> str:
    if method_family in MAINLINE_FAMILIES:
        return "default_mainline"
    if method_family in COMMON_EXTENDED_FAMILIES:
        return "common_extended"
    return "specialized_extended"


def result_schema_name(method_family: str, effect_measure: str) -> str:
    effect = normalize(effect_measure)
    if method_family == "prevalence_descriptive":
        return "prevalence_descriptive_result"
    if method_family == "ordinal_clm":
        return "ordinal_association_result"
    if method_family == "multinomial_nominal":
        return "multinomial_association_result"
    if method_family in {"count_outcome", "zero_inflated_count"}:
        return "count_association_result"
    if method_family in {"adjusted_predictions", "marginal_effects"}:
        return "marginal_effect_prediction_result"
    if effect in {"beta", "beta coefficient", "mean difference", "logit scale coefficient"} or method_family == "bounded_proportion":
        return "continuous_association_result"
    return "binary_association_result"


def default_figure_families(method_family: str) -> list[str]:
    figure_map = {
        "prevalence_descriptive": ["plot_distribution", "plot_balance"],
        "binary_pr": ["plot_forest", "plot_marginal_effects"],
        "binary_or": ["plot_forest", "plot_marginal_effects"],
        "binary_sparse_robust": ["plot_forest"],
        "continuous_linear": ["plot_forest", "plot_distribution"],
        "continuous_mi_weighted": ["plot_forest", "plot_missingness"],
        "ordinal_clm": ["plot_forest"],
        "multinomial_nominal": ["plot_marginal_effects"],
        "bounded_proportion": ["plot_distribution", "plot_marginal_effects"],
        "clustered_gee": ["plot_forest"],
        "count_outcome": ["plot_forest", "plot_distribution"],
        "zero_inflated_count": ["plot_forest", "plot_distribution"],
    }
    return figure_map.get(method_family, ["plot_forest"])


def make_id(prefix: str, index: int) -> str:
    return f"{prefix}{index:03d}"
def profile_csv(path: Path, sample_rows: int | None = None) -> dict:
    """Profile the full file by default; sampled profiles are explicitly marked non-release."""
    df = pd.read_csv(path, nrows=sample_rows)
    schema = []
    sparse = {}
    missingness = {}
    binary_prevalence = {}
    raw_levels = {}
    parse_diagnostics = {}
    for col in df.columns:
        series = df[col]
        non_na = series.dropna()
        value_counts = non_na.value_counts()
        missingness[col] = {
            "n_missing": int(series.isna().sum()),
            "pct_missing": round(float(series.isna().mean() * 100), 2),
        }
        if series.dtype == "object" or non_na.nunique() <= 20:
            raw_levels[col] = {
                "n_unique": int(non_na.nunique()),
                "levels": [str(value) for value in value_counts.index[:100]],
                "truncated": bool(non_na.nunique() > 100),
            }
            sparse_levels = value_counts[value_counts < 10]
            if not sparse_levels.empty:
                sparse[col] = sparse_levels.to_dict()
        if non_na.nunique() == 2:
            positive = value_counts.iloc[0] if len(value_counts) == 1 else value_counts.min()
            binary_prevalence[col] = {
                "n_levels": int(non_na.nunique()),
                "min_level_count": int(positive),
                "value_counts": {str(k): int(v) for k, v in value_counts.to_dict().items()},
            }
        min_value = None
        max_value = None
        integer_like = False
        proportion_candidate = False
        count_candidate = False
        if pd.api.types.is_numeric_dtype(series):
            numeric_non_na = pd.to_numeric(non_na, errors="coerce").dropna()
            if not numeric_non_na.empty:
                min_value = float(numeric_non_na.min())
                max_value = float(numeric_non_na.max())
                integer_like = bool((numeric_non_na % 1 == 0).all())
                proportion_candidate = bool(min_value >= 0 and max_value <= 1 and numeric_non_na.nunique() > 2)
                count_candidate = bool(integer_like and min_value >= 0 and numeric_non_na.nunique() > 2)
        elif not non_na.empty:
            parsed = pd.to_numeric(non_na.astype(str).str.strip(), errors="coerce")
            parse_rate = float(parsed.notna().mean())
            if parse_rate >= 0.5:
                parse_diagnostics[col] = {
                    "numeric_parse_candidate": True,
                    "n_parse_failures": int(parsed.isna().sum()),
                    "pct_parse_failures": round(float(parsed.isna().mean() * 100), 2),
                }
        schema.append(
            {
                "name": col,
                "dtype": str(series.dtype),
                "n_unique": int(non_na.nunique()),
                "sample_values": non_na.astype(str).head(5).tolist(),
                "min_value": min_value,
                "max_value": max_value,
                "integer_like": integer_like,
                "proportion_candidate": proportion_candidate,
                "count_candidate": count_candidate,
            }
        )

    weight_vars = [c for c in df.columns if "weight" in c.lower()]
    weight_diagnostics = {}
    for col in weight_vars:
        values = pd.to_numeric(df[col], errors="coerce")
        valid = values.dropna()
        positive = valid[valid > 0]
        ess = None
        if not positive.empty and float((positive ** 2).sum()) > 0:
            ess = float(positive.sum() ** 2 / (positive ** 2).sum())
        weight_diagnostics[col] = {
            "n_missing_or_non_numeric": int(values.isna().sum()),
            "n_zero": int((valid == 0).sum()),
            "n_negative": int((valid < 0).sum()),
            "min_positive": float(positive.min()) if not positive.empty else None,
            "max_positive": float(positive.max()) if not positive.empty else None,
            "coefficient_of_variation": float(positive.std(ddof=1) / positive.mean()) if len(positive) > 1 and positive.mean() else None,
            "kish_effective_sample_size": ess,
        }
    id_candidates = []
    for col in df.columns:
        lowered = col.lower()
        if lowered in {"id", "record_id", "participant_id", "subject_id", "person_id"} or lowered.endswith("_id"):
            id_candidates.append({
                "variable": col,
                "n_missing": int(df[col].isna().sum()),
                "n_duplicated_nonmissing": int(df.loc[df[col].notna(), col].duplicated(keep=False).sum()),
                "n_unique": int(df[col].nunique(dropna=True)),
            })
    strata_vars = [c for c in df.columns if "strat" in c.lower() or "stratum" in c.lower()]
    psu_vars = [c for c in df.columns if "psu" in c.lower() or "cluster" in c.lower()]
    nesting = []
    for strata in strata_vars:
        for psu in psu_vars:
            pairs = df[[strata, psu]].dropna().drop_duplicates()
            nesting.append({
                "strata_variable": strata,
                "psu_variable": psu,
                "psus_in_multiple_strata": int((pairs.groupby(psu)[strata].nunique() > 1).sum()),
                "lonely_strata": int((pairs.groupby(strata)[psu].nunique() == 1).sum()),
            })

    return {
        "file": str(path),
        "profile_scope": "sampled_nonrelease" if sample_rows is not None else "full_dataset",
        "sample_rows_read": len(df),
        "n_rows_profiled": len(df),
        "n_columns": len(df.columns),
        "schema": schema,
        "detected_weight_vars": weight_vars,
        "detected_strata_vars": strata_vars,
        "detected_psu_vars": psu_vars,
        "duplicate_full_rows": int(df.duplicated(keep=False).sum()),
        "identifier_candidates": id_candidates,
        "parse_diagnostics": parse_diagnostics,
        "raw_levels": raw_levels,
        "weight_diagnostics": weight_diagnostics,
        "design_nesting_diagnostics": nesting,
        "sparse_levels": sparse,
        "missingness_by_column": missingness,
        "binary_prevalence": binary_prevalence,
    }
