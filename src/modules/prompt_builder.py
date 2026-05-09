#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Structured prompt and contract generation tool.

This module is responsible for assembling the four-part System/Contract/Context/Instruction
prompt based on model profile (GPT series / Claude series), and provides minimal method
contract and context clipping capabilities. As the project evolves, Method Contract and
Data Semantics Contract will be loaded from external JSON; the current implementation
is a progressive transition version.
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


DEFAULT_DELIVERABLES = ["main_output.csv", "analysis_summary.json"]


@dataclass
class MethodContract:
    """Minimal method contract.

    In the future, more complete fields will be loaded from external JSON. Here we provide
    default values and serialization capabilities for validation before and after code generation.
    """

    id: str
    stage: str
    method: str
    required_packages: List[str] = field(default_factory=list)
    required_patterns: List[str] = field(default_factory=list)
    forbidden_packages: List[str] = field(default_factory=list)
    forbidden_functions: List[str] = field(default_factory=list)
    deliverables: List[str] = field(default_factory=lambda: DEFAULT_DELIVERABLES.copy())
    allowed_adjustments: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    notes: Optional[str] = None

    def to_payload(self) -> Dict[str, Any]:
        payload = {
            "id": self.id,
            "stage": self.stage,
            "method": self.method,
            "required_packages": self.required_packages,
            "required_patterns": self.required_patterns,
            "forbidden_packages": self.forbidden_packages,
            "forbidden_functions": self.forbidden_functions,
            "deliverables": self.deliverables,
            "allowed_adjustments": self.allowed_adjustments,
            "preconditions": self.preconditions,
        }
        if self.notes:
            payload["notes"] = self.notes
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), ensure_ascii=False, indent=2)


class PromptBuilder:
    """Unified prompt assembler."""

    def __init__(self, model_profile: str = "gpt", max_context_chars: int = 20000):
        self.model_profile = (model_profile or "gpt").lower()
        self.max_context_chars = max_context_chars

    def build_method_contract(
        self,
        section: str,
        stage_name: str,
        method_description: str,
        hints: Optional[Dict[str, Any]] = None,
    ) -> MethodContract:
        """Generate minimal method contract based on stage and description.

        hints can include `required_packages`, `required_patterns`, `preconditions`, etc.,
        to connect with external configuration in future iterations.
        """

        hints = hints or {}
        contract_id = hints.get("id") or f"stage-{section}"
        required_packages = hints.get("required_packages", [])
        required_patterns = hints.get("required_patterns", [])
        forbidden_packages = hints.get("forbidden_packages", [])
        forbidden_functions = hints.get("forbidden_functions", [])
        deliverables = hints.get("deliverables") or DEFAULT_DELIVERABLES.copy()
        allowed_adjustments = hints.get("allowed_adjustments", [
            "Expand or simplify variable list (core variables must not be removed)",
            "Model optimization parameters (optimizer / control)",
            "Missing value and outlier cleaning strategies",
        ])
        preconditions = hints.get("preconditions", [
            "Must verify that core variables exist and are non-empty",
            "If method requires binary/factor variables, standardization must be completed before execution",
        ])

        notes = hints.get("notes") or textwrap.shorten(method_description.strip(), width=280, placeholder="…")

        return MethodContract(
            id=contract_id,
            stage=str(section),
            method=stage_name,
            required_packages=list(dict.fromkeys(required_packages)),  # Remove duplicates while preserving order
            required_patterns=required_patterns,
            forbidden_packages=list(dict.fromkeys(forbidden_packages)),
            forbidden_functions=list(dict.fromkeys(forbidden_functions)),
            deliverables=deliverables,
            allowed_adjustments=allowed_adjustments,
            preconditions=preconditions,
            notes=notes,
        )

    def build_code_messages(
        self,
        *,
        section: str,
        stage_name: str,
        method_description: str,
        sub_prompt: str,
        variable_schema: Optional[List[Dict[str, Any]]] = None,
        global_guidance: Optional[str] = None,
        path_strategy: Optional[str] = None,
        method_contract: Optional[MethodContract] = None,
        data_snapshot: Optional[str] = None,
        sparse_analysis: Optional[Dict[str, Any]] = None,
        research_framework: Optional[Dict[str, Any]] = None,
        survey_design_guidance: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Build message list for code generation stage."""

        contract = method_contract or self.build_method_contract(section, stage_name, method_description)

        system_prompt = self._build_system_prompt()
        contract_block = f"<method_contract>\n{contract.to_json()}\n</method_contract>"
        context_block = self._build_context_block(variable_schema, global_guidance, path_strategy, data_snapshot, sparse_analysis)

        analysis_plan = textwrap.dedent(
            f"""
            <analysis_plan>
            {sub_prompt.strip()}
            </analysis_plan>
            """
        ).strip()

        # Build research framework constraints
        framework_instructions = ""
        if research_framework:
            from src.modules.estimand_classifier import EstimandClassifier
            classifier = EstimandClassifier()
            framework_instructions = classifier.generate_analysis_constraints(
                research_framework['research_type']
            ) + "\n\n"
            
            covariate_strategy = research_framework.get('covariate_strategy', {})
            if covariate_strategy.get('mode') == 'DAG_prespecified':
                framework_instructions += textwrap.dedent(
                    f"""
                    **COVARIATE ADJUSTMENT ENFORCEMENT (DAG MODE - STRICT)**:
                    - ONLY use pre-specified covariates from DAG adjustment set: {covariate_strategy.get('covariates', [])}
                    - DO NOT add/remove variables based on baseline imbalance or p-values
                    - DO NOT include mediators in main model: {covariate_strategy.get('mediators', [])}
                    - Forbidden practices: {', '.join(covariate_strategy.get('forbidden_practices', []))}
                    - Any deviation from pre-specified set is a violation
                    - **CRITICAL**: Check which DAG-specified variables exist in actual data
                    - **CRITICAL**: Document missing variables in analysis_summary.json$protocol_deviations
                    
                    """
                ).strip() + "\n\n"
            elif covariate_strategy.get('mode') == 'data_driven':
                framework_instructions += textwrap.dedent(
                    """
                    **COVARIATE ADJUSTMENT ENFORCEMENT (DATA-DRIVEN MODE)**:
                    - May select variables based on baseline imbalance (SMD threshold)
                    - Document selection criteria in analysis_summary.json
                    - DO NOT include outcomes or colliders
                    - State clearly: "Covariate selection based on baseline imbalance"
                    
                    """
                ).strip() + "\n\n"
        
        # Build survey design guidance
        design_instructions = ""
        if survey_design_guidance:
            design_instructions = textwrap.dedent(
                f"""
                **SURVEY DESIGN CONSISTENCY (MANDATORY):**
                {survey_design_guidance}
                
                **Multiple Imputation + Complex Survey Integration:**
                If using MICE for missing data:
                1. Include weight/strata/PSU as predictors in imputation model
                2. After imputation: Create svydesign() object for EACH imputed dataset
                3. Run analysis on each svydesign object
                4. Pool results using Rubin's rules with proper variance estimation
                5. Code template (replace variable names with actual names from your data):
                   ```r
                   imp_list <- complete(mice_obj, "all")
                   results <- lapply(imp_list, function(dat) {{
                     design <- svydesign(ids=~psu_var, strata=~strata_var, weights=~weight_var, data=dat)
                     svyglm(outcome_var ~ exposure_var + covariate1 + covariate2, design=design, family=quasipoisson(link="log"))
                   }})
                   pooled <- pool(results)
                   ```
                
                **If design variables NOT verified**: Downgrade language to "exploratory analysis without design adjustment"
                """
            ).strip() + "\n\n"

        controlled_deviation_instructions = textwrap.dedent(
            """
            **CONTROLLED DEVIATION HANDLING (SAP-AUTHORITATIVE):**

            The submitted protocol/SAP is the final pre-execution contract. Before generating code, inspect all available `deviation_record` fields in the analysis_plan.

            - If `deviation_record.is_deviation_from_default` is false, follow the SAP method specified in that component.
            - If `deviation_record.is_deviation_from_default` is true, follow `deviation_record.accepted_method` rather than reverting to the original default recommendation, provided the submitted protocol is final.
            - Do not silently override an accepted SAP deviation with a default decision-tree pathway.
            - If a deviation_record says human confirmation is required but the protocol is not clearly finalized or approved, flag that deviation for investigator confirmation instead of silently executing it.

            For each accepted deviation, record a `controlled_deviation_audit` entry in analysis_summary.json and print a "Controlled deviation audit" section in the execution log with:
            1. SAP component,
            2. default recommendation,
            3. accepted method,
            4. rationale,
            5. human confirmation status,
            6. code implementation or verification.

            If no accepted controlled deviation is identified, record: "No accepted controlled deviation was identified in the core SAP components. The execution followed the final SAP-specified methodological pathway."
            """
        ).strip() + "\n\n"
        
        # Build sparse variable handling instructions if needed
        sparse_instructions = ""
        if sparse_analysis and sparse_analysis.get('has_separation_risk', False):
            sparse_vars = sparse_analysis.get('sparse_variables', [])
            sparse_instructions = textwrap.dedent(
                f"""
                **CRITICAL: Sparse Variable Auto-Handling (MANDATORY):**
                The system has detected {len(sparse_vars)} sparse variable(s) that require automatic processing: {', '.join(sparse_vars[:5])}{'...' if len(sparse_vars) > 5 else ''}
                
                **You MUST automatically handle these variables in your R code:**
                1. **Before modeling**: Check event counts per category (at least 10 events required)
                2. **High-risk variables** (>50% sparse levels): Automatically EXCLUDE from model, add comment explaining
                3. **Medium-risk variables**: Merge sparse levels (n<10) into 'Other' before modeling
                4. **Alternative**: Use Firth penalized likelihood (logistf::logistf) with explicit comment
                5. **In forest plots**: Filter out OR/PR>1000 or <0.001 (separation artifacts)
                6. **Post-modeling check**: Verify no Inf/NA coefficients, if found, re-run with that variable excluded
                
                **Example code pattern:**
                ```r
                # Check sparse levels (replace "outcome_var" with actual outcome variable name)
                for(var in categorical_vars) {{
                  tab <- table(data[[var]], data[[outcome_var]])
                  if(min(tab) < 10) {{
                    cat("WARNING:", var, "has sparse levels, excluding from model\\n")
                    model_formula <- update(model_formula, paste("~ . -", var))
                  }}
                }}
                ```
                
                **Do NOT proceed to modeling without handling sparse variables - convergence will fail.**
                """
            ).strip() + "\n\n"
        
        mice_export_instructions = ""
        missing_visualization_instructions = ""
        mice_convergence_instructions = ""
        mice_density_instructions = ""
        if "missing" in stage_name.lower() or "imputation" in stage_name.lower() or section == "7.2":
            from .r_code_templates import RCodeTemplates
            mice_export_instructions = textwrap.dedent(
                f"""
                **MISSING DATA HANDLING - DATA EXPORT (SAP-CONDITIONAL TEMPLATE):**
                The final SAP is authoritative. Before generating code, inspect the SAP-specified missing-data strategy and any available `deviation_record`.
                If the SAP specifies Multiple Imputation by Chained Equations (MICE), implement MICE and use the MICE export template to generate the analysis-ready dataset.
                If the SAP specifies an alternative missing-data strategy, such as complete-case analysis, survey-compatible imputation, model-based missing-data handling, pattern-mixture/selection models, or variable exclusion, implement the SAP-specified strategy instead of forcing MICE.
                In all cases, the code must write the required main_output.csv file. If no MICE object exists, use the template's non-MICE branch or equivalent direct export logic to save the final analysis-ready dataset.
                Do not introduce MICE solely because a default template exists. Do not override an accepted SAP deviation unless the SAP itself requires human reconfirmation before execution.
                Template to use when MICE is actually implemented, or to reuse for its non-MICE direct export branch:
                ```r
                {RCodeTemplates.mice_export_template()}
                ```
                **CRITICAL REQUIREMENTS**:
                - Subsequent stages cannot read .rds objects; CSV export is mandatory.
                - main_output.csv must always be written, whether MICE is used or not.
                - If SAP requires MICE, export imputed_data_*.csv and main_output.csv from the MICE object.
                - If SAP does not require MICE, do not create a MICE object solely for pipeline continuity; directly write the SAP-consistent analysis-ready data to main_output.csv.
                """
            ).strip() + "\n\n"
            
            missing_visualization_instructions = textwrap.dedent(
                f"""
                **MISSING DATA VISUALIZATION (MANDATORY for Stage 7.2 - MUST USE TEMPLATE EXACTLY):**
                
                You MUST use the following template code EXACTLY to generate missing data visualizations:
                
                ```r
                {RCodeTemplates.missing_data_visualization_template()}
                ```
                
                **CRITICAL REQUIREMENTS**:
                - You MUST copy and use the template code above EXACTLY as provided
                - DO NOT write your own visualization code
                - DO NOT modify the template logic or function calls
                - DO NOT replace with simplified implementations
                - **MANDATORY**: For VIM::aggr() and VIM::matrixplot(), you MUST use print() to render graphics
                - **FORBIDDEN**: DO NOT call aggr() or matrixplot() without print() - graphics will not render in non-interactive environments
                - The template code shows: aggr_result <- aggr(...); print(aggr_result) and matrix_result <- matrixplot(...); print(matrix_result)
                - You MUST follow this exact pattern, including the print() calls
                - The template automatically handles dynamic cex.axis calculation, missing data checks, and proper plot rendering
                - Output files: missing_data_pattern.csv, missing_data_aggr_plot.png, missing_data_matrixplot.png
                - All plots use professional colors and English labels (12x8 inches, 300 DPI)
                """
            ).strip() + "\n\n"
            
            mice_convergence_instructions = textwrap.dedent(
                f"""
                **MICE CONVERGENCE DIAGNOSTICS (MANDATORY if MICE used - MUST USE TEMPLATE EXACTLY):**
                
                After MICE imputation, you MUST use the following template code EXACTLY to generate convergence trace plots:
                
                **CRITICAL PRINT() REQUIREMENT**:
                - **MANDATORY**: You MUST use print(plot_result) after plot(imp, ...) to render graphics
                - **FORBIDDEN**: DO NOT call plot(imp, ...) without print() - graphics will not render in non-interactive environments
                - The template code shows: plot_result <- plot(imp, layout = layout_dim); if(!is.null(plot_result)) print(plot_result)
                - You MUST follow this exact pattern, including the print() call
                
                ```r
                {RCodeTemplates.mice_convergence_template()}
                ```
                
                **CRITICAL REQUIREMENTS**:
                - You MUST copy and use the template code above EXACTLY as provided
                - DO NOT write your own convergence plot code
                - DO NOT use fixed layout like layout = c(3, 3)
                - DO NOT modify the dynamic layout calculation logic
                - The template automatically calculates optimal layout based on number of imputed variables
                - The template only plots variables that were actually imputed
                - The template uses print() to ensure proper rendering in non-interactive environments
                - Output file: mice_convergence_trace_plots.png (12x8 inches, 300 DPI)
                """
            ).strip() + "\n\n"
            
            mice_density_instructions = textwrap.dedent(
                f"""
                **MICE DENSITY PLOTS (MANDATORY if MICE used - MUST USE TEMPLATE EXACTLY):**
                
                After MICE imputation, you MUST use the following template code EXACTLY to generate density comparison plots:
                
                ```r
                {RCodeTemplates.mice_density_template()}
                ```
                
                **CRITICAL REQUIREMENTS**:
                - You MUST copy and use the template code above EXACTLY as provided
                - DO NOT write your own density plot code
                - DO NOT modify the data sufficiency checks or fallback logic
                - The template automatically checks data sufficiency (>= 10 non-missing values)
                - The template automatically falls back to ggplot2 bar chart if density plots fail
                - The template limits to top 6 variables for readability
                - **MANDATORY**: You MUST use print(density_plot) after densityplot(imp, ...) to render graphics
                - **FORBIDDEN**: DO NOT call densityplot(imp, ...) without print() - graphics will not render in non-interactive environments
                - The template code shows: density_plot <- densityplot(imp, ...); print(density_plot)
                - You MUST follow this exact pattern, including the print() call
                - Output file: mice_density_plots.png (12x6 inches, 300 DPI)
                """
            ).strip() + "\n\n"
        
        tableone_instructions = ""
        if section == "7.3" or "table1" in stage_name.lower() or "descriptive" in stage_name.lower():
            from .r_code_templates import RCodeTemplates
            tableone_instructions = textwrap.dedent(
                f"""
                **TABLE 1 GENERATION (MANDATORY for Stage 7.3 - MUST USE TEMPLATE EXACTLY):**
                
                You MUST use the following template code EXACTLY to generate Table 1:
                
                ```r
                {RCodeTemplates.tableone_template()}
                ```
                
                **CRITICAL REQUIREMENTS**:
                - You MUST copy and use the template code above EXACTLY as provided
                - DO NOT write your own Table 1 code
                - DO NOT modify the normality testing logic or variable classification
                - The template automatically tests normality for all continuous variables (Shapiro-Wilk test, by strata)
                - The template automatically uses svyCreateTableOne if weights are available, otherwise CreateTableOne
                - The template automatically applies median [IQR] for non-normal variables, mean (SD) for normal variables
                - The template automatically identifies numeric variables with n_unique <= 20 as categorical
                - Output files: table1_weighted_baseline.csv and table1_variable_dictionary.csv
                """
            ).strip() + "\n\n"
        
        correlation_matrix_instructions = ""
        if section == "7.4" or "bivariate" in stage_name.lower() or "exploratory" in stage_name.lower():
            from .r_code_templates import RCodeTemplates
            correlation_matrix_instructions = textwrap.dedent(
                f"""
                **CORRELATION MATRIX GENERATION (MANDATORY for Stage 7.4 - MUST USE TEMPLATE):**
                
                You MUST use the following template code EXACTLY to generate correlation matrix table and heatmap:
                
                ```r
                {RCodeTemplates.correlation_matrix_template()}
                ```
                
                **CRITICAL REQUIREMENTS**:
                - You MUST use the template code above, do NOT write your own correlation code
                - The template automatically detects survey weights and uses appropriate method (weighted/unweighted)
                - MUST export correlation_matrix.csv (table format with Variable column)
                - MUST export correlation_heatmap.png (ggplot2 heatmap with correlation values as text labels)
                - These files are REQUIRED deliverables and MUST be generated regardless of protocol requirements
                - Do NOT skip this step or replace with simplified code
                """
            ).strip() + "\n\n"
        
        factor_validation_instructions = ""
        mice_reading_instructions = ""
        pooled_extraction_instructions = ""
        all_variables_modeling_instructions = ""
        if section in ["7.5", "7.7"] or "multivariable" in stage_name.lower() or "interaction" in stage_name.lower() or "modeling" in stage_name.lower():
            from .r_code_templates import RCodeTemplates
            factor_validation_instructions = textwrap.dedent(
                f"""
                **FACTOR LEVEL VALIDATION (MANDATORY for modeling stages):**
                
                You MUST use the following template functions to validate factor levels before modeling:
                
                ```r
                {RCodeTemplates.factor_level_validation_template()}
                ```
                
                **CRITICAL REQUIREMENTS**:
                - BEFORE converting variables to factors: Use `validate_factor_levels()` to check all categorical variables
                - AFTER factor conversion: Use `safe_factor_conversion()` to safely convert with level preservation
                - AFTER creating survey design with strata: Re-validate factor levels WITHIN each stratum using `validate_factor_levels(data, var_list, check_strata=TRUE, strata_var="strata_variable_name")`
                - BEFORE building model: Final validation to ensure all formula variables have >= 2 levels
                - If any variable has < 2 levels in ANY stratum: EXCLUDE from model or merge strata
                - DO NOT proceed to model building if validation fails
                
                **Example usage**:
                ```r
                # Initial validation
                validation_result <- validate_factor_levels(data, c("Gender", "Geographic_Region", "Self_Rated_Health"))
                valid_vars <- validation_result$valid
                
                # Safe factor conversion
                data <- safe_factor_conversion(data, valid_vars)
                
                # After creating survey design with strata, validate within strata
                validation_strata <- validate_factor_levels(data, valid_vars, check_strata=TRUE, strata_var="Geographic_Region")
                final_valid_vars <- validation_strata$valid
                ```
                """
            ).strip() + "\n\n"
            
            mice_reading_instructions = textwrap.dedent(
                f"""
                **MICE DATA READING (SAP-CONDITIONAL for stages requiring multiple imputation):**
                
                Read data from the previous stage's main_output.csv FIRST. Only read and prioritize MICE datasets when the final SAP/sub-prompt requires multiple imputation:
                
                ```r
                {RCodeTemplates.mice_data_reading_template()}
                ```
                
                **CRITICAL REQUIREMENTS**:
                - PRIMARY data source: Read from previous stage's main_output.csv (e.g., "../7.4/main_output.csv")
                - SECONDARY data source: If and only if MICE is required by the final SAP, read imputed datasets from stage 7.2 (e.g., "../7.2/imputed_data_*.csv")
                - Use `read_mice_datasets()` function which handles both sources automatically
                - If SAP requires MICE and MICE datasets are found, they take precedence for multiple-imputation analysis
                - If SAP specifies a non-MICE strategy, do not switch to MICE just because imputed_data_*.csv files exist; set `prefer_mice = FALSE` and use the previous stage data or SAP-specific dataset
                - If only previous stage data is available, use it as a single dataset
                - DO NOT hardcode data paths - use relative paths from current stage directory
                
                **Example usage**:
                ```r
                # Read data. Set prefer_mice=TRUE only when the final SAP requires MICE.
                imp_list <- read_mice_datasets(
                  prev_stage_path = "../7.4/main_output.csv",
                  mice_stage_path = "../7.2",
                  n_imputations = 20,
                  prefer_mice = TRUE
                )
                ```
                """
            ).strip() + "\n\n"
            
            pooled_extraction_instructions = textwrap.dedent(
                f"""
                **POOLED RESULTS EXTRACTION (MANDATORY for modeling stages - MUST USE TEMPLATE):**
                
                When extracting coefficients from MIcombine() pooled results, you MUST use the following template functions:
                
                ```r
                {RCodeTemplates.pooled_results_extraction_template()}
                ```
                
                **CRITICAL REQUIREMENTS (STRICTLY ENFORCED)**:
                - FORBIDDEN: Hardcoding coefficient names (e.g., "VarNameLevel1", "Exercise_FrequencyDaily")
                - FORBIDDEN: Assuming coefficient name format without verification
                - FORBIDDEN: Using direct string matching like `var_name %in% names(coefs)` without smart matching
                - MANDATORY: Define the template functions at the beginning of your R script (copy the template code above)
                - MANDATORY: Use extract_coefficient_by_levels() function for ALL coefficient extraction
                - MANDATORY: Use get_factor_levels_from_data() to get actual factor levels from current stage data
                - MANDATORY: Use extract_interaction_terms() for interaction analysis
                - These functions automatically detect coefficient name format and match correctly
                - If extraction fails, the functions will print available coefficient names for debugging
                - If you write code like `extract_pr_ci(pooled_obj, "VarNameLevel")`, you MUST replace it with `extract_coefficient_by_levels()`
                
                **Example usage**:
                ```r
                # Get actual factor levels from data (replace "YourVariable" with actual variable name)
                var_levels <- get_factor_levels_from_data(data, "YourVariable")
                # Extract coefficients using smart matching (replace "YourVariable" and "ReferenceLevel" with actual names)
                var_results <- extract_coefficient_by_levels(pooled_obj, "YourVariable", var_levels, reference_level = "ReferenceLevel")
                ```
                """
            ).strip() + "\n\n"
        
        if section == "7.5" or ("multivariable" in stage_name.lower() and "primary" in stage_name.lower()):
            all_variables_modeling_instructions = textwrap.dedent(
                """
                **ALL VARIABLES MODELING (MANDATORY for primary multivariable analysis):**
                
                In addition to the DAG-specified adjustment set, you MUST also fit a model with ALL available variables (excluding sparse variables):
                
                **REQUIREMENTS**:
                1. **Primary model**: Use DAG-specified adjustment set (if DAG mode) or protocol-specified covariates
                2. **Sensitivity model**: Fit additional model with ALL variables (excluding sparse variables, outcomes, exposure)
                3. **Variable exclusion criteria for sensitivity model**:
                   - Exclude variables identified as sparse (from sparse_analysis or previous stages)
                   - Exclude outcome variables
                   - Exclude exposure variable (if single exposure analysis)
                   - Include all other variables from data
                4. **Output requirements**:
                   - Save primary model results as: multivariable_[outcome]_table.csv (or similar)
                   - Save sensitivity model results as: all_variables_[outcome]_table.csv
                   - Document in analysis_summary.json: "primary_model_covariates" and "sensitivity_model_covariates"
                5. **Purpose**: This sensitivity analysis explores whether conclusions are robust to inclusion of additional variables
                
                **Example code structure**:
                ```r
                # Primary model (DAG-specified)
                primary_model <- svyglm(outcome ~ exposure + covariate1 + covariate2, design=design, family=...)
                
                # Sensitivity model (all variables, excluding sparse)
                all_vars <- setdiff(names(data), c(outcome_var, exposure_var, sparse_vars, weight_vars, design_vars))
                sensitivity_model <- svyglm(outcome ~ exposure + ., data=data[, c(outcome_var, exposure_var, all_vars)], design=design, family=...)
                ```
                """
            ).strip() + "\n\n"
        else:
            all_variables_modeling_instructions = ""
        
        weight_detection_rules = ""
        if section in ["7.0", "7.1"]:
            weight_detection_rules = textwrap.dedent(
                """
                **WEIGHT AUTO-DETECTION (MANDATORY - Execute ONCE at data load):**
                
                Before any analysis, perform weight variable detection:
                
                1. Search for weight variable (priority order):
                   - Exact match: common weight variable names (e.g., "weight", "weights", "wgt", "sampling_weight", "survey_weight")
                   - Fuzzy match: any column containing "weight" (case-insensitive)
                   - Check previous stage summary: read weight_detection from stage 7.1 analysis_summary.json if available
                
                2. Validate detected weight:
                   ```r
                   if(!is.null(weight_col)) {
                     weight_stats <- list(
                       variable = weight_col,
                       min = min(data[[weight_col]], na.rm=TRUE),
                       median = median(data[[weight_col]], na.rm=TRUE),
                       max = max(data[[weight_col]], na.rm=TRUE),
                       n_unique = length(unique(data[[weight_col]][!is.na(data[[weight_col]])])),
                       pct_missing = mean(is.na(data[[weight_col]])) * 100,
                       has_nonpositive = any(data[[weight_col]] <= 0, na.rm=TRUE),
                       all_equal_one = all(data[[weight_col]] == 1, na.rm=TRUE)
                     )
                     usable_weight <- weight_stats$n_unique > 1 && 
                                      !weight_stats$has_nonpositive && 
                                      weight_stats$pct_missing < 5
                   } else {
                     usable_weight <- FALSE
                   }
                   ```
                
                3. Write to analysis_summary.json:
                   - `weight_detection`: {`weight_variable`, `usable_weight`, `weight_summary`, `detection_reason`}
                   - If `usable_weight=FALSE`: document reason ("all_ones" / "nonpositive_values" / "high_missing" / "not_found")
                
                4. Enforcement:
                   - If `usable_weight=TRUE`: MUST use this weight in all later stages, FORBIDDEN to create placeholder
                   - If `usable_weight=FALSE`: May proceed with placeholder weight=1, but MUST set `weight_is_placeholder=true`
                
                This detection runs ONCE; later stages ONLY read from 7.1 analysis_summary.json.
                
                """
            ).strip() + "\n\n"
        
        statistical_rules = textwrap.dedent(
            """
            **STATISTICAL INTERPRETATION RULES (MANDATORY):**
            
            1. MCAR Test Interpretation:
               - Little's MCAR test p > 0.05: "Failed to reject MCAR" (data consistent with MCAR)
               - Little's MCAR test p <= 0.05: "Reject MCAR" (data NOT consistent with MCAR)
               - NEVER reverse this logic
            
            2. Missing Data Strategy Consistency:
               - If simple imputation (mean/mode): State "simple imputation, no MICE"
               - If MICE: State "MICE with m imputations" and provide trace plots
               - NEVER claim both in same report
               - In analysis_summary.json: Specify "missing_method": "simple" or "MICE"
            
            3. Sample Size Consistency:
               - Track n at each stage: Add comments like "n = XXX after [operation]"
               - Final tables MUST use consistent n across all outputs
               - If n changes: Explain in analysis_summary.json
            
            4. Survey Weight Verification:
               - Check: if(all(data[[weight_col]] == 1)) then state "equal weight (unweighted analysis)" (use detected weight variable name, not hardcoded "weight")
               - NEVER claim "survey-weighted" or "population representative" when all weights equal 1
               - Add weight check code: if(length(unique(data[[weight_col]])) == 1 && unique(data[[weight_col]]) == 1) cat("WARNING: Placeholder weights\\n")
               - Use the weight variable name from weight_detection, not hardcoded variable names
            
            5. Output Quality Validation:
               - Check all numeric results for NA/NaN/Inf before writing tables
               - If Inf detected: Flag as separation issue, exclude from forest plots
               - If NA/failed tests: Document in analysis_summary.json, do not silently include
            
            6. Survey Design Reporting Contract (MANDATORY):
               - In `analysis_summary.json`, you MUST write a `design` object with the following keys:
                 * `design_verified_level`: one of ["design_based", "sample_based", "unknown"]
                   - "design_based": if you used svydesign/svyglm with actual weights (not all equal to 1)
                   - "sample_based": if you used unweighted analysis OR weights are all equal to 1 (placeholder)
                 * `weight_variable`: actual variable name used (or null)
                 * `strata_variable`: actual variable name used (or null)
                 * `psu_variable`: actual variable name used (or null)
                 * `weight_is_placeholder`: true/false (true if all weights are 1 or weights were auto-created)
                 * `weights_actually_used`: true/false (true if svydesign/svyglm was called with weights parameter)
                 * `design_limitations`: short, factual statements describing missing inputs and implication
               - CRITICAL: `design_verified_level` MUST reflect actual analysis method:
                 * If you called svydesign(weights=~weight_var) where weight_var has >1 unique values: `design_verified_level="design_based"`
                 * If you called svydesign(weights=~weight_var) but all weights=1: `design_verified_level="sample_based"` AND `weight_is_placeholder=true`
                 * If you did NOT use svydesign/svyglm: `design_verified_level="sample_based"` AND `weights_actually_used=false`
               - If `weight_is_placeholder=true` OR `weights_actually_used=false`:
                 * You MUST set `design_verified_level="sample_based"`
                 * You MUST state in `analysis_summary.json` and console logs: "Exploratory unweighted analysis; no design-based inference"
            
            7. No Silent Placeholder Rule:
               - If you create any placeholder variable (e.g., `weight <- 1`) for pipeline continuity, you MUST:
                 * print a WARNING in console,
                 * set `weight_is_placeholder=true`,
                 * and ensure report language is downgraded accordingly.
            
            8. Weight Detection Inheritance (for stages after 7.1):
               - Read `weight_detection` from stage 7.1 analysis_summary.json
               - If `usable_weight=TRUE`: MUST use that weight variable, DO NOT create placeholder
               - If `usable_weight=FALSE`: May use placeholder, but document in your own analysis_summary
               - DO NOT re-detect or override the global weight decision from stage 7.1
            
            9. Design Information Inheritance (MANDATORY for ALL stages after 7.1):
               - Read `design` object from stage 7.1 analysis_summary.json (or earliest stage that has it)
               - You MUST include a `design` object in your own analysis_summary.json
               - For stages that do NOT use svydesign/svyglm (e.g., 7.2 missing data handling):
                 * Inherit design information from prev_summary$design
                 * Set `weights_actually_used=false` (because you did not call svydesign/svyglm)
                 * Set `design_verified_level` to match inherited value (usually "design_based" if weights are valid, "sample_based" if placeholder)
                 * Preserve `weight_variable`, `strata_variable`, `psu_variable` from previous stage
               - This ensures design information is consistently passed through all stages
            
            10. Design Variable Level Preservation (MANDATORY):
               - Read design variables (strata, PSU) from prev_summary$design
               - Before any analysis, verify these variables have >= 2 levels
               - When converting to factor, preserve ALL levels: factor(var, levels = unique(var[!is.na(var)]))
               - NEVER filter data by design variables unless protocol explicitly requires
               - If design variable has < 2 levels: STOP and report error
               - Report level counts in console for verification
            
            11. Protocol Deviation Register (MANDATORY for modeling stages):
               - Compare protocol-specified variables (especially DAG adjustment set) with actual data variables
               - If protocol variables are missing from data: Document in analysis_summary.json as "protocol_deviations"
               - Required fields in analysis_summary.json:
                 * protocol_deviations: list of {variable_name, reason, substitute_variable, impact_on_conclusion}
                 * Example: {{"variable_name": "Education", "reason": "not collected in data", "substitute_variable": "Self_Rated_Health", "impact_on_conclusion": "may underestimate confounding by socioeconomic status"}}
               - If no deviations: Set protocol_deviations to empty list []
               - This information will be used in report generation for Deviation Register section
            
            """
        ).strip() + "\n\n"
        
        instruction_block = textwrap.dedent(
            f"""
            Please strictly enforce the constraints in method_contract:
            - Do not replace or weaken the specified statistical methods and function calls;
            - Must load required_packages and satisfy required_patterns;
            - Must generate all files listed in deliverables;
            - If any preconditions are not met, explicitly stop(...) with explanation;
            - May only adjust variables or parameters when allowed by the allowed_adjustments list.

           {controlled_deviation_instructions}{weight_detection_rules}{mice_export_instructions}{missing_visualization_instructions}{mice_convergence_instructions}{mice_density_instructions}{mice_reading_instructions}{factor_validation_instructions}{tableone_instructions}{correlation_matrix_instructions}{pooled_extraction_instructions}{all_variables_modeling_instructions}{statistical_rules}{framework_instructions}{design_instructions}{sparse_instructions}**Strict file naming requirements:**
           - Output file names must exactly match those specified in the sub-prompt
           - Do not arbitrarily change file names or add extra suffixes
           - Graphics file names must clearly describe content (e.g., forest_plot_[outcome_name].png)
           - CSV files must use specified column names and formats

           **Standardized image generation requirements:**
           - **Heatmap generation**: Must use the `create_heatmap()` function (in the plot generation template), do not directly use ggplot2 or corrplot to draw heatmaps manually
           - **Other images**: Must use standardized functions such as `create_standard_plot()` or `create_forest_plot()`
           - Ensure all images have uniform format, clear labels, and no overlap issues
           - **CRITICAL**: Use ENGLISH for ALL plot labels, titles, legends, and annotations (NO Chinese characters)

           Output requirements:
            - Only return complete R code;
            - Wrap with ```r at the beginning and ``` at the end;
            - Include execution markers, validation statements, and artifact output in the code.
            """
        ).strip()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": contract_block},
        ]

        if context_block:
            messages.append({"role": "user", "content": context_block})

        payload = f"{analysis_plan}\n\n{instruction_block}"
        messages.append({"role": "user", "content": self._clip_payload(payload)})

        return messages

    def build_plan_messages(
        self,
        *,
        section: str,
        stage_name: str,
        method_description: str,
        variable_schema: Optional[List[Dict[str, Any]]] = None,
        global_guidance: Optional[str] = None,
        method_contract: Optional[MethodContract] = None,
    ) -> List[Dict[str, str]]:
        """(Reserved) Build message list for Checklist planning stage."""

        contract = method_contract or self.build_method_contract(section, stage_name, method_description)
        system_prompt = self._build_system_prompt(mode="plan")
        context_block = self._build_context_block(variable_schema, global_guidance, None)

        instructions = textwrap.dedent(
            """
            Please output the Checklist (JSON array) required to execute this statistical stage, each step including:
            - step: Brief action description;
            - functions: Key R functions/packages;
            - validations: Validation points that must pass;
            - deliverables: Related artifacts.

            Checklist must cover method_contract.required_patterns and deliverables.
            """
        ).strip()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"<method_contract>\n{contract.to_json()}\n</method_contract>"},
        ]

        if context_block:
            messages.append({"role": "user", "content": context_block})

        messages.append({"role": "user", "content": instructions})
        return messages

    def _build_system_prompt(self, mode: str = "code") -> str:
        if self.model_profile.startswith("claude"):
            iron_rules = """
            <iron_rules>
            <rule>Do not replace the statistical method specified in method_contract.method</rule>
            <rule>Must generate all deliverables</rule>
            <rule>Must stop if validation fails or preconditions are not met</rule>
            </iron_rules>
            """
            header = textwrap.dedent(
                f"""
                You are a statistical modeling expert and R language engineer who will strictly execute XML/JSON contracts.
                Mode: {mode}
                """
            ).strip()
            return f"{header}\n{iron_rules.strip()}"

        iron_rules = """
        Core iron rules:
        1. Do not replace the statistical methods or functions specified in method_contract(method).
        2. Must generate all artifacts listed in deliverables, and stop if write fails.
        3. Stop immediately and throw error if any precondition is not met.
        """
        header = textwrap.dedent(
            f"""
            You are a senior statistical analyst and R engineer who will strictly follow structured contracts.
            Mode: {mode}
            """
        ).strip()
        return f"{header}\n{iron_rules.strip()}"

    def _build_context_block(
        self,
        variable_schema: Optional[List[Dict[str, Any]]],
        global_guidance: Optional[str],
        path_strategy: Optional[str],
        data_snapshot: Optional[str] = None,
        sparse_analysis: Optional[Dict[str, Any]] = None,
    ) -> str:
        parts: List[str] = []

        if data_snapshot and data_snapshot.strip():
            parts.append(f"<current_data_snapshot>\n{data_snapshot.strip()}\n</current_data_snapshot>")

        if sparse_analysis and sparse_analysis.get('has_separation_risk', False):
            sparse_warning = self._build_sparse_variable_warning(sparse_analysis)
            parts.append(sparse_warning)

        if variable_schema:
            lines = ["<variable_schema>"]
            for item in variable_schema:
                name = item.get("name")
                dtype = item.get("dtype")
                role = item.get("role")
                level = item.get("level")
                alias = ",".join(item.get("aliases", [])) or "-"
                lines.append(f"- name: {name}; dtype: {dtype}; role: {role or '-'}; level: {level or '-'}; aliases: {alias}")
            lines.append("</variable_schema>")
            parts.append("\n".join(lines))

        if global_guidance and global_guidance.strip():
            parts.append(f"<global_guidance>\n{global_guidance.strip()}\n</global_guidance>")

        if path_strategy and path_strategy.strip():
            parts.append(f"<path_strategy>\n{path_strategy.strip()}\n</path_strategy>")

        content = "\n\n".join(parts).strip()
        return self._clip_payload(content)

    def _build_sparse_variable_warning(self, sparse_analysis: Dict[str, Any]) -> str:
        """
        Build sparse variable warning message (general method)
        
        Args:
            sparse_analysis: Sparse variable detection results
            
        Returns:
            Formatted warning message
        """
        warning_lines = [
            "<sparse_variable_warning>",
            "Data Quality Warning: Potential separation issue detected",
            "",
            "Sparse variable details:"
        ]
        
        for var in sparse_analysis.get('sparse_variables', []):
            risk_info = sparse_analysis['separation_risk'].get(var, {})
            warning_lines.append(f"- {var}: {risk_info.get('sparse_levels', 0)} sparse levels (risk level: {risk_info.get('risk_level', 'unknown')})")
        
        warning_lines.extend([
            "",
            "**Mandatory requirements (must execute):**",
            "- **High-risk variables**: Must be excluded from the model, or explicitly comment in code explaining the reason for using robust methods (Firth correction, Bayesian methods)",
            "- **Medium-risk variables**: Must merge sparse levels into 'Other' category, or explicitly explain in code why they are retained",
            "- In model formula, must adjust variable list according to above requirements",
            "- When generating forest plots, must filter out abnormal effect values (OR/PR > 1000 or < 0.001), which are usually caused by separation issues",
            "",
            "Severity: These variables will cause model convergence failure, abnormally large coefficients (e.g., OR > 1000), or model instability. **Action must be taken, do not ignore.**",
            "</sparse_variable_warning>"
        ])
        
        return "\n".join(warning_lines)

    def _clip_payload(self, content: str) -> str:
        if not content:
            return content
        if len(content) <= self.max_context_chars:
            return content
        trimmed = content[: self.max_context_chars]
        hint = "\n<!-- clipped due to context budget -->"
        return trimmed + hint


__all__ = ["MethodContract", "PromptBuilder"]
