#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Code execution module - complete R code execution and error handling functionality"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class CodeExecutor:
    """R code executor, responsible for executing R code and handling errors"""
    
    def __init__(self, config: Dict, error_fix_manager, data_profiler=None):
        """
        Initialize code executor
        
        Args:
            config: Configuration dictionary
            error_fix_manager: Error fix manager instance
            data_profiler: Data profiler instance (optional)
        """
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.error_fix_manager = error_fix_manager
        self.data_profiler = data_profiler
        self._llm_fix_function = None
    
    def set_llm_fix_function(self, llm_fix_function):
        """
        Inject LLM fix function
        
        Args:
            llm_fix_function: LLM fix function, takes (system_prompt, user_prompt) and returns the fixed code
        """
        self._llm_fix_function = llm_fix_function
        self.logger.info("LLM fix function injected")
    
    def execute(
        self,
        r_script_path: Path,
        stage_name: str,
        section: str,
        path_manager,
        data_path: Optional[str] = None,
        sub_prompt_content: Optional[str] = None
    ) -> Tuple[bool, str, List[str]]:
        """
        Main entry point for executing R code
        
        Args:
            r_script_path: R script file path
            stage_name: Stage name
            section: Section number
            path_manager: Path manager instance
            data_path: Current stage data path (for data snapshot when error fixing)
            
        Returns:
            (success flag, message, output file list)
        """
        self.logger.info(f"Executing R code for {stage_name} (section {section})...")
        
        self._current_data_path = data_path
        self._current_sub_prompt_content = sub_prompt_content
        
        max_retries = self.config.get('max_retries', 10)
        
        env_info = path_manager.prepare_stage_environment(section)
        stage_output_dir = Path(env_info['stage_dir'])
        
        self.logger.info(f"Stage execution environment prepared: {stage_output_dir}")
        
        fix_history = []

        for attempt in range(max_retries):
            try:
                relative_r_script_path = os.path.relpath(r_script_path, stage_output_dir)

                result = subprocess.run(
                    ['Rscript', relative_r_script_path],
                    cwd=str(stage_output_dir),
                    capture_output=True,
                    text=True,
                    timeout=self.config.get('timeout', 600)
                )
                
                if result.returncode == 0:
                    output_files = list(stage_output_dir.glob('*'))
                    output_files = [str(f) for f in output_files if f.is_file()]

                    outputs_ok, missing_outputs = self._verify_stage_outputs(stage_output_dir)
                    
                    if not outputs_ok:
                        self.logger.warning(
                            f"{stage_name} (section {section}) execution missing required outputs: {missing_outputs}"
                        )
                        
                        if attempt < max_retries - 1:
                            self._fix_missing_outputs(
                                r_script_path,
                                result,
                                missing_outputs,
                                stage_output_dir,
                                section
                            )
                            continue

                        failure_message = (
                            f"Required outputs missing: {missing_outputs}. R stdout:\n{result.stdout}"
                        )
                        return False, failure_message, output_files
                    
                    self.logger.info(
                        f"{stage_name} (section {section}) execution successful, generated {len(output_files)} files"
                    )
                    return True, result.stdout, output_files
                
                else:
                    error_msg = result.stderr
                    self.logger.warning(
                        f"{stage_name} execution failed (attempt {attempt + 1}/{max_retries}): {error_msg}"
                    )
                    
                    if attempt < max_retries - 1:
                        fix_result = self._fix_execution_error(
                            r_script_path,
                            error_msg,
                            stage_output_dir,
                            section,
                            attempt_number=attempt + 1,
                            fix_history=fix_history
                        )

                        fix_history.append({
                            'attempt': attempt + 1,
                            'error': error_msg[:200],
                            'fixed': fix_result,
                            'method': 'unknown'
                        })
                        
                        if not fix_result:
                            self.logger.info(f"Attempt {attempt + 1} did not produce code changes, will continue to try other strategies")
                    
            except subprocess.TimeoutExpired:
                self.logger.error(f"{stage_name} execution timed out")
                break
            except Exception as e:
                self.logger.error(f"{stage_name} execution exception: {e}")
                break
        
        error_message = result.stderr if 'result' in locals() else "Execution failed"
        return False, error_message, []
    
    def _verify_stage_outputs(self, stage_output_dir: Path) -> Tuple[bool, List[str]]:
        """
        Verify if the stage execution has generated the required output files
        
        Args:
            stage_output_dir: Stage output directory
            
        Returns:
            (success flag, missing files list)
        """
        required_files = {
            'main_output.csv': stage_output_dir / 'main_output.csv',
            'analysis_summary.json': stage_output_dir / 'analysis_summary.json'
        }
        
        missing_items: List[str] = []
        
        for name, path in required_files.items():
            if not path.exists() or path.stat().st_size == 0:
                missing_items.append(name)
                continue
            
            if name.endswith('.json'):
                try:
                    import json
                    with open(path, 'r', encoding='utf-8') as f:
                        json.load(f)
                except Exception:
                    missing_items.append(name + '(content not parsable)')
        
        return len(missing_items) == 0, missing_items
    
    def _fix_missing_outputs(
        self,
        r_script_path: Path,
        result,
        missing_outputs: List[str],
        stage_output_dir: Path,
        section: str
    ) -> None:
        """
        Fix missing outputs problem
        
        Args:
            r_script_path: R script file path
            result: subprocess result
            missing_outputs: Missing output list
            stage_output_dir: Stage output directory
            section: Section number
        """
        with open(r_script_path, 'r', encoding='utf-8') as f:
            current_r_code = f.read()
        
        synthetic_error = (
            "REQUIRED_OUTPUT_MISSING: "
            + ", ".join(missing_outputs)
            + "\nR stdout:\n"
            + result.stdout[-1500:]
            + "\nR stderr:\n"
            + result.stderr[-1500:]
        )
        
        corrected_code = self._fix_code_error(
            current_r_code,
            synthetic_error,
            r_script_path,
            stage_output_dir,
            section
        )
        
        if corrected_code != current_r_code:
            with open(r_script_path, 'w', encoding='utf-8') as f:
                f.write(corrected_code)
            self.logger.info("Script adjusted for missing outputs, will retry")
    
    def _fix_execution_error(
        self,
        r_script_path: Path,
        error_msg: str,
        stage_output_dir: Path,
        section: str,
        attempt_number: int = 1,
        fix_history: List = None
    ) -> bool:
        """
        Fix execution error (progressive repair strategy)
        
        Args:
            r_script_path: R script file path
            error_msg: Error message
            stage_output_dir: Stage output directory
            section: Section number
            attempt_number: Current attempt number (for selecting repair strategy)
            fix_history: Fix history record
            
        Returns:
            Whether the fix is successful (code has changed)
        """
        with open(r_script_path, 'r', encoding='utf-8') as f:
            current_r_code = f.read()
        
        corrected_code = self._fix_code_error(
            current_r_code,
            error_msg,
            r_script_path,
            stage_output_dir,
            section,
            attempt_number=attempt_number,
            fix_history=fix_history
        )
        
        if corrected_code != current_r_code:
            with open(r_script_path, 'w', encoding='utf-8') as f:
                f.write(corrected_code)
            self.logger.info("R code corrected and file updated")
            return True
        
        return False
    
    def _fix_code_error(
        self,
        original_code: str,
        error_message: str,
        r_script_path: Optional[Path] = None,
        stage_output_dir: Optional[Path] = None,
        section: Optional[str] = None,
        attempt_number: int = 1,
        fix_history: List = None
    ) -> str:
        """
        Fix R code error (progressive repair strategy)
        
        Args:
            original_code: Original code
            error_message: Error message
            r_script_path: R script file path (optional)
            stage_output_dir: Stage output directory (optional)
            section: Section number (optional)
            attempt_number: Current attempt number (for selecting repair strategy)
            fix_history: Fix history record
            
        Returns:
            Fixed code
        """
        self.logger.info(f"Attempting to fix R code error... (attempt {attempt_number})")
        
        data_summary = ""
        if section and stage_output_dir:
            data_summary = self._collect_diagnostic_info(section, stage_output_dir)
        
        data_snapshot = ""
        if self.data_profiler and hasattr(self, '_current_data_path') and self._current_data_path:
            data_snapshot = self.data_profiler.get_quick_snapshot(self._current_data_path)
            self.logger.info("Current data snapshot obtained for error repair")
        
        llm_fix_function = self._llm_fix_function
        
        if llm_fix_function is None:
            self.logger.warning("LLM fix function not injected, will skip LLM repair")
        
        force_llm = False
        include_history = False
        
        if attempt_number >= 3:
            force_llm = True
            self.logger.info("Enabling enhanced LLM repair strategy (including data snapshot)")
        
        if attempt_number >= 6:
            include_history = True
            self.logger.info("Enabling advanced LLM repair strategy (including repair history)")
        
        self.logger.info(f"Calling attempt_fix (force_llm={force_llm}, has_llm_function={llm_fix_function is not None})")
        try:
            fixed_code, success, method = self.error_fix_manager.attempt_fix(
                original_code,
                error_message,
                data_summary,
                llm_fix_function,
                data_snapshot=data_snapshot,
                force_llm=force_llm,
                fix_history=fix_history if include_history else None,
                sub_prompt_content=getattr(self, '_current_sub_prompt_content', None)
            )
            self.logger.info(f"attempt_fix returned: success={success}, method={method}")
        except Exception as e:
            self.logger.error(f"attempt_fix raised exception: {e}", exc_info=True)
            return original_code
        
        self.error_fix_manager.log_fix_result(error_message, success, method)
        
        if success:
            self.logger.info(f"Error repair successful, method: {method}")
            return fixed_code
        else:
            self.logger.error("Error repair failed")
            return original_code
    
    def _collect_diagnostic_info(
        self,
        section: Optional[str] = None,
        stage_output_dir: Optional[Path] = None
    ) -> str:
        """
        Collect diagnostic information, help LLM locate problems
        
        Args:
            section: Section number
            stage_output_dir: Stage output directory
            
        Returns:
            Diagnostic information text
        """
        info_parts: List[str] = []
        
        try:
            if section:
                info_parts.append(f"Current stage: {section}")
                
            if stage_output_dir:
                files_snapshot = sorted([
                    p.name for p in Path(stage_output_dir).glob('*') if p.is_file()
                ])
                info_parts.append(f"Stage directory file list: {files_snapshot}")
        
        except Exception as exc:
            info_parts.append(f"Diagnostic information collection failed: {exc}")
        
        return "\n".join(info_parts) if info_parts else "No diagnostic information"
    
    def set_llm_fix_function(self, llm_fix_func):
        """
        Set LLM repair function (injected by orchestrator)
        
        Args:
            llm_fix_func: LLM repair function
        """
        self._llm_fix_function = llm_fix_func
    
    def _fix_code_error_with_llm(
        self,
        original_code: str,
        error_message: str,
        data_summary: str
    ) -> str:
        """
        Use LLM to fix code errors
        
        Args:
            original_code: Original code
            error_message: Error message
            data_summary: Data summary
            
        Returns:
            Fixed code
        """
        if hasattr(self, '_llm_fix_function'):
            def llm_fix_function(system_prompt: str, user_prompt: str) -> str:
                return self._llm_fix_function(system_prompt, user_prompt)
            
            fixed_code, success, method = self.error_fix_manager.attempt_fix(
                original_code,
                error_message,
                data_summary,
                llm_fix_function
            )
            
            if success:
                return fixed_code
        
        return original_code


