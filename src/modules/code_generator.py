#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Code generation module - complete R code generation and validation functionality"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Three-level validation result"""
    
    level: str = "normal"
    
    passed: bool = True
    
    failures: List[Dict[str, str]] = field(default_factory=list)
    
    def add_failure(self, level: str, message: str):
        """Add failure item"""
        self.failures.append({'level': level, 'message': message})
        if level == 'critical':
            self.passed = False
    
    def get_critical_failures(self) -> List[str]:
        """Get critical failure items"""
        return [f['message'] for f in self.failures if f['level'] == 'critical']
    
    def get_important_failures(self) -> List[str]:
        """Get important failure items"""
        return [f['message'] for f in self.failures if f['level'] == 'important']
    
    def get_normal_failures(self) -> List[str]:
        """Get normal failure items"""
        return [f['message'] for f in self.failures if f['level'] == 'normal']
    
    def get_all_failures(self) -> List[str]:
        """Get all failure items"""
        return [f['message'] for f in self.failures]


class CodeGenerator:
    """R code generator, responsible for generating R code conforming to the contract"""
    
    def __init__(self, config: Dict):
        """
        Initialize code generator
        
        Args:
            config: Configuration dictionary
        """
        self.logger = logging.getLogger(__name__)
        self.config = config
        self._current_dynamic_contract = None
        self._current_data_path = None
    
    def generate(
        self,
        sub_prompt_path: str,
        data_path: str,
        path_manager,
        prompt_builder,
        decision_manager,
        data_profiler,
        llm_client,
        method_contracts: Dict,
        data_semantics: Dict,
        dynamic_contract=None,
        research_framework: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Main entry point for generating R code
        
        Args:
            sub_prompt_path: Sub prompt file path
            data_path: Data file path
            path_manager: Path manager instance
            prompt_builder: Prompt builder instance
            decision_manager: Decision manager instance
            data_profiler: Data profiler instance
            llm_client: LLM client instance
            method_contracts: Method contract configuration
            data_semantics: Data semantics configuration
            dynamic_contract: Dynamic extracted contract (optional)
            
        Returns:
            Generated R code
        """
        self.logger.info(f"Generating R code for {sub_prompt_path}...")
        
        self._current_dynamic_contract = dynamic_contract
        self._current_data_path = data_path
        
        with open(sub_prompt_path, 'r', encoding='utf-8') as f:
            sub_prompt = f.read()
        
        filename = Path(sub_prompt_path).stem
        parts = filename.split('_')
        current_section = parts[1] if len(parts) > 1 else "unknown"
        stage_name_token = "_".join(parts[2:]) if len(parts) > 2 else "analysis_stage"
        
        data_profile = data_profiler.get_profile(data_path)
        
        data_snapshot = data_profiler.get_quick_snapshot(data_path)
        self.logger.info(f"Current stage data snapshot:\n{data_snapshot}")
        
        path_info = path_manager.generate_enhanced_prompt_info(current_section)
        
        global_decisions_context = decision_manager.get_for_stage(current_section)
        
        method_summary = self._extract_method_summary(sub_prompt)
        
        method_contract = self._resolve_method_contract(
            current_section,
            stage_name_token,
            method_summary,
            method_contracts,
            prompt_builder
        )
        
        preflight_ok, preflight_issues = self._run_preflight_checks(
            current_section,
            method_contract,
            data_profile,
            method_summary,
            data_semantics
        )
        
        self.logger.info(
            f"Preflight check: {'passed' if preflight_ok else 'failed'}, "
            f"issues={preflight_issues}"
        )
        
        if not preflight_ok:
            raise RuntimeError(f"Preflight check failed: {preflight_issues}")
        
        sparse_analysis = data_profiler.detect_sparse_variables(data_path)
        if sparse_analysis.get('has_separation_risk', False):
            self.logger.warning(f"[{current_section}] Detected sparse variables: {sparse_analysis.get('sparse_variables', [])}")
        
        survey_design_guidance = None
        if '7.2' in current_section or '7.5' in current_section:
            survey_design_guidance = (
                "This stage may involve multiple imputation or modeling. "
                "Ensure survey design (weight/strata/PSU) is consistently applied throughout."
            )
        
        messages = prompt_builder.build_code_messages(
            section=current_section,
            stage_name=stage_name_token,
            method_description=method_summary,
            sub_prompt=sub_prompt,
            variable_schema=data_profile.get('schema'),
            global_guidance=global_decisions_context,
            path_strategy=path_info,
            method_contract=method_contract,
            data_snapshot=data_snapshot,
            sparse_analysis=sparse_analysis,
            research_framework=research_framework,
            survey_design_guidance=survey_design_guidance
        )
        
        max_attempts = max(1, int(self.config.get('code_generation_retry', 3)))
        r_code = self._generate_with_retry(
            messages,
            sub_prompt,
            llm_client,
            max_attempts
        )
        
        return r_code
    
    def _generate_with_retry(
        self,
        messages: List[Dict],
        sub_prompt: str,
        llm_client,
        max_attempts: int
    ) -> str:
        """
        Code generation with validation (empty retry mechanism to avoid getting worse)
        
        Args:
            messages: Initial message list
            sub_prompt: Sub prompt content
            llm_client: LLM client
            max_attempts: Maximum number of attempts
            
        Returns:
            Generated R code
            
        Raises:
            RuntimeError: If all attempts fail
        """
        initial_messages = list(messages)
        last_result = None
        accumulated_constraints = []
        
        for attempt in range(max_attempts):
            if attempt == 0:
                conversation = list(initial_messages)
            else:
                conversation = list(initial_messages)
                
                constraint_list = "\n".join(f"✓ Must be satisfied: {c}" for c in accumulated_constraints)
                
                retry_instruction = (
                    f"Please regenerate the complete R code (attempt {attempt + 1}).\n\n"
                    f"The previous code did not satisfy the following constraints:\n{constraint_list}\n\n"
                    "Important instructions:\n"
                    "- Please provide the complete, compliant R code\n"
                    "- Do not omit any part\n"
                    "- Ensure all required variables and output files are included\n"
                    "- The code must be a complete, executable script"
                )
                conversation.append({"role": "user", "content": retry_instruction})
            
            response = llm_client.call(messages=conversation)
            
            r_code = self._extract_r_code(response)
            
            validation_result = self._validate_generated_code(r_code, sub_prompt)
            
            if validation_result.passed:
                if validation_result.failures:
                    normal_failures = validation_result.get_normal_failures()
                    if normal_failures:
                        self.logger.info(
                            f"Code generation successful (attempt {attempt + 1}/{max_attempts}), "
                            f"but there are {len(normal_failures)} suggestions for improvement"
                        )
                else:
                    self.logger.info(f"Code generation successful (attempt {attempt + 1}/{max_attempts})")
                return r_code
            
            last_result = validation_result
            critical_failures = validation_result.get_critical_failures()
            important_failures = validation_result.get_important_failures()

            accumulated_constraints = critical_failures
              
            failure_msgs = []
            if critical_failures:
                failure_msgs.extend([f"[Critical] {msg}" for msg in critical_failures])
            if important_failures:
                failure_msgs.extend([f"[Important-only advice] {msg}" for msg in important_failures])
            
            failure_text = "\n".join(f"- {msg}" for msg in failure_msgs)
            
            self.logger.warning(
                f"Generated code did not pass the constraint validation (attempt {attempt + 1}/{max_attempts}):\n{failure_text}"
            )
        
        if last_result and last_result.get_critical_failures():
            aggregate_failure = "; ".join(last_result.get_critical_failures())
        else:
            aggregate_failure = "Generated code did not satisfy the critical constraints"
        
        raise RuntimeError(f"Generated R code did not satisfy the critical constraints: {aggregate_failure}")
    
    def _resolve_method_contract(
        self,
        section: str,
        stage_name: str,
        method_summary: str,
        method_contracts: Dict,
        prompt_builder
    ):
        """
        Resolve method contract based on the stage
        
        Args:
            section: Stage number
            stage_name: Stage name
            method_summary: Method summary
            method_contracts: Method contract configuration
            prompt_builder: Prompt builder
            
        Returns:
            MethodContract object
        """
        hints = (
            method_contracts.get(section)
            or method_contracts.get(stage_name)
            or method_contracts.get('default')
            or {}
        )
        return prompt_builder.build_method_contract(
            section=section,
            stage_name=stage_name,
            method_description=method_summary,
            hints=hints
        )
    
    def _run_preflight_checks(
        self,
        section: str,
        contract,
        data_profile: Dict[str, Any],
        method_summary: str,
        data_semantics: Dict
    ) -> Tuple[bool, List[str]]:
        """
        Execute semantic preflight checks, ensure critical variables and preconditions are met
        
        Args:
            section: Stage number
            contract: Method contract
            data_profile: Data profile
            method_summary: Method summary
            data_semantics: Data semantics configuration
            
        Returns:
            (Whether passed, problem list)
        """
        issues: List[str] = []
        schema_map = {col['name']: col for col in data_profile.get('schema', [])}
        
        method_tags = {
            (contract.method or '').lower(),
            section.lower(),
            method_summary.lower()
        }
        
        if not contract.deliverables:
            issues.append('contract_missing_deliverables')
        
        for variable in data_semantics.get('variables', []):
            var_name = variable.get('name')
            required_methods = [m.lower() for m in (variable.get('required_by_methods') or [])]
            
            if required_methods and method_tags.isdisjoint(set(required_methods)):
                continue
            
            if var_name not in schema_map:
                issues.append(f"missing_variable::{var_name}")
                continue
            
            level = variable.get('level')
            dtype = schema_map[var_name].get('dtype', '')
            if level == 'binary':
                if not any(keyword in dtype for keyword in ['int', 'float', 'bool', 'object']):
                    issues.append(f"binary_variable_type_mismatch::{var_name}::{dtype}")
        
        success = not any(item.startswith('missing_variable') for item in issues)
        return success, issues
    
    def _extract_method_summary(self, sub_prompt: str) -> str:
        """
        Extract the main statistical method description from the sub prompt
        
        Args:
            sub_prompt: Sub prompt content
            
        Returns:
            Method summary
        """
        for line in sub_prompt.splitlines():
            cleaned = line.strip('# ').strip()
            if cleaned:
                return cleaned
        return sub_prompt.strip()[:120]
    
    def _validate_generated_code(self, r_code: str, sub_prompt: str) -> ValidationResult:
        """
        Validate the generated R code against the constraints (three-level validation strategy)
        
        Args:
            r_code: R code
            sub_prompt: Sub prompt content
            
        Returns:
            ValidationResult object
        """
        result = ValidationResult()
        
        # ==== Level 1 validation: critical items (must be satisfied, otherwise blocked) ====
        if re.search(r'setwd\s*\(\s*["\']output/', r_code):
            result.add_failure('critical', 
                "Detected code that manually sets the working directory setwd(\"output/...\"), this will cause path errors."
                "Python has already set the working directory to output/7.X/, please write files directly.")
        
        if re.search(r'dir\.create\s*\(\s*["\']output["\']', r_code):
            result.add_failure('critical',
                "Detected code that creates the output subdirectory dir.create(\"output\"), this will cause path混乱。"
                "Python has already set the working directory to output/7.X/, please write files directly.")

        has_main_output = bool(re.search(
            r'(write\.csv|write_csv|fwrite|readr::write_csv|data\.table::fwrite)\s*\([^)]*["\']main_output\.csv["\']',
            r_code
        ))
        if not has_main_output:
            result.add_failure('critical', "Missing main_output.csv write logic")
        
        # ==== Level 2 validation: important items (recommended but not mandatory) ====
        has_summary_json = bool(re.search(
            r'(write|writeLines|cat|toJSON|write_json|jsonlite::write_json)\s*\([^)]*["\']analysis_summary\.json["\']',
            r_code
        ))
        if not has_summary_json:
            result.add_failure('important', "It is recommended to add analysis_summary.json write logic to record the analysis summary")

        if hasattr(self, '_current_dynamic_contract') and self._current_dynamic_contract:
            contract = self._current_dynamic_contract

            for group in contract.alternative_method_groups:
                for group_name, methods in group.items():
                    found_methods = []
                    for method_name, pattern in methods:
                        if re.search(pattern, r_code):
                            found_methods.append(method_name)
                    
                    if not found_methods:
                        method_names = [m[0] for m in methods]
                        result.add_failure(
                            'important',
                            f"{group_name} needs to implement at least one of the following methods: {method_names}"
                        )
                    else:
                        self.logger.debug(f"{group_name} validation passed: found {found_methods}")
            
            for method_name, pattern in contract.recommended_methods.items():
                if not re.search(pattern, r_code):
                    result.add_failure(
                        'normal',
                        f"It is recommended to use the '{method_name}' method"
                    )
            
            for filename in contract.recommended_files:
                if filename not in r_code:
                    result.add_failure(
                        'normal',
                        f"It is recommended to generate the '{filename}' file"
                    )
            
            if contract.has_validation_template:
                for pattern in contract.validation_patterns:
                    if pattern not in r_code:
                        result.add_failure(
                            'normal',
                            f"It is recommended to use the validation pattern '{pattern}'"
                        )
        else:
            self.logger.debug("No dynamic contract provided, skipping method validation")
        
        # ==== Level 3 validation: recommended items (only recorded, does not affect passing) ====
        if 'stop(' not in r_code:
            result.add_failure('normal', "It is recommended to add error handling mechanism (e.g. stop())")
        
        if 'cat(' not in r_code and 'print(' not in r_code:
            result.add_failure('normal', "It is recommended to add execution log output (e.g. cat() or print())")
        
        return result
    
    def _extract_r_code(self, response: str) -> str:
        """
        Extract pure R code from the LLM response
        
        Args:
            response: Response from the LLM
            
        Returns:
            Extracted R code
        """
        if '```r' in response:
            parts = response.split('```r')
            if len(parts) > 1:
                code_part = parts[1].split('```')[0]
                return code_part.strip()
        
        elif '```' in response:
            parts = response.split('```')
            if len(parts) >= 3:
                return parts[1].strip()
        
        lines = response.split('\n')
        r_code_lines = []
        
        for line in lines:
            if (line.strip().startswith('#') and 
                ('Step 1' in line or 'Step 2' in line or '##' in line)):
                continue
            if line.strip().startswith('I will') or line.strip().startswith('Here is'):
                continue
            r_code_lines.append(line)
        
        return '\n'.join(r_code_lines).strip()


