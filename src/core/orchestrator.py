#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main controller - Statistical analysis workflow orchestration"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.modules.llm_client import LLMClient
from src.modules.data_profiler import DataProfiler
from src.modules.document_processor import DocumentProcessor
from src.modules.decision_manager import DecisionManager
from src.modules.code_generator import CodeGenerator
from src.modules.code_executor import CodeExecutor
from src.modules.file_path_manager import FilePathManager
from src.modules.prompt_builder import PromptBuilder
from src.modules.error_fix_manager import ErrorFixManager
from src.modules.contract_extractor import ContractExtractor
from src.modules.estimand_classifier import EstimandClassifier
from src.modules.survey_design_validator import SurveyDesignValidator
from src.modules.data_quality_controller import DataQualityController
from src.modules.statistical_consistency_checker import StatisticalConsistencyChecker


class AnalysisOrchestrator:
    """Statistical analysis workflow orchestrator - coordinate all modules to complete the analysis task"""
    
    def __init__(self, config_path: str = "config.json", session_id: str = None):
        """
        Initialize the orchestrator
        
        Args:
            config_path: Configuration file path
            session_id: Session ID (for creating independent workspace)
        """
        self.config = self._load_config(config_path)
        self.workspace_root = os.getcwd()
        self.session_id = session_id
        
        from src.modules.file_path_manager import FilePathManager
        self.path_manager = FilePathManager(self.workspace_root, self.config, session_id=self.session_id)
        
        self.setup_logging()
        self.logger = logging.getLogger(__name__)
        
        self._initialize_modules()
        
        self.setup_directories()
        
        self.logger.info("AnalysisOrchestrator initialized")
    
    def _initialize_modules(self):
        """Initialize all modules (path_manager has already been created in __init__)"""
        self.logger.info("Initializing modules...")
        
        self.llm_client = LLMClient(self.config)
        self.data_profiler = DataProfiler()
        self.prompt_builder = PromptBuilder(
            model_profile=self._infer_model_profile(self.config.get('model', '')),
            max_context_chars=self.config.get('max_context_chars', 20000)
        )
        self.error_fix_manager = ErrorFixManager()
        
        self.contract_extractor = ContractExtractor()
        
        decisions_file = Path(self.path_manager.get_global_decisions_path())
        self.decision_manager = DecisionManager(str(decisions_file))
        
        self.document_processor = DocumentProcessor(
            temp_dir=str(self.path_manager.temp_dir),
            meta_prompt_path=self.config['meta_prompt_path']
        )
        
        self.code_generator = CodeGenerator(self.config)
        self.code_executor = CodeExecutor(self.config, self.error_fix_manager, self.data_profiler)
        
        self.code_executor.set_llm_fix_function(self._llm_fix_wrapper)
        
        self.estimand_classifier = EstimandClassifier()
        self.survey_validator = SurveyDesignValidator()
        self.quality_controller = DataQualityController()
        self.consistency_checker = StatisticalConsistencyChecker()
        
        self.method_contracts = self._load_method_contracts()
        self.data_semantics = self._load_data_semantics()
        self.research_framework = None
    
    def _llm_fix_wrapper(self, system_prompt: str, user_prompt: str) -> str:
        """LLM fix function wrapper"""
        try:
            return self.llm_client.call(
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )
        except Exception as e:
            self.logger.error(f"LLM fix call failed: {e}")
            return ""
    
    def run_analysis(self, document_path: str, data_path: str, progress_callback=None) -> Dict:
        """
        Run the complete analysis process
        
        Args:
            document_path: Research protocol document path
            data_path: Data file path
            progress_callback: Optional callback function(progress: int, current_step: str) to update progress
            
        Returns:
            Analysis result dictionary
        """
        self.logger.info("=" * 60)
        self.logger.info("Starting statistical analysis process...")
        self.logger.info("=" * 60)
        start_time = time.time()
        
        try:
            if progress_callback:
                progress_callback(10, "Parsing research protocol document")
            self.logger.info("Stage 1: Parse research protocol document, generate sub prompts")
            
            protocol_text = self._read_file_with_encoding_detection(document_path)
            self.research_framework = self.estimand_classifier.classify_research_goal(protocol_text)
            self.logger.info(f"Research framework: {self.research_framework['research_type']}")
            
            sub_prompts = self.document_processor.process(
                document_path=document_path,
                data_path=data_path,
                data_profiler=self.data_profiler,
                llm_client=self.llm_client
            )
            
            self.logger.info(f"Successfully generated {len(sub_prompts)} sub prompts")
            
            if progress_callback:
                progress_callback(20, "Starting analysis stages")
            self.logger.info("Stage 2: Process each analysis module")
            analysis_results = []
            
            current_data_path = data_path
            
            for i, sub_prompt in enumerate(sub_prompts, 1):
                section = sub_prompt['section']
                stage_name = sub_prompt['stage_name']
                
                if progress_callback:
                    base_progress = 20
                    stage_progress = base_progress + int((i - 1) * (70 - base_progress) / len(sub_prompts))
                    progress_callback(stage_progress, f"Processing stage {i}/{len(sub_prompts)}: {stage_name}")
                self.logger.info(f"\n{'='*60}")
                self.logger.info(f"Stage {i}/{len(sub_prompts)}: {section} - {stage_name}")
                self.logger.info(f"Current data path: {current_data_path}")
                self.logger.info(f"{'='*60}")
                
                try:
                    self.logger.info(f"[{section}] Extract dynamic contract...")
                    dynamic_contract = self.contract_extractor.extract_from_file(
                        sub_prompt['file_path']
                    )
                    self.logger.info(
                        f"[{section}] Dynamic contract: methods={dynamic_contract.required_methods}, "
                        f"recommended files={dynamic_contract.recommended_files}"
                    )
                    
                    self.logger.info(f"[{section}] Generate R code...")
                    r_code = self.code_generator.generate(
                        sub_prompt_path=sub_prompt['file_path'],
                        data_path=current_data_path,
                        path_manager=self.path_manager,
                        prompt_builder=self.prompt_builder,
                        decision_manager=self.decision_manager,
                        data_profiler=self.data_profiler,
                        llm_client=self.llm_client,
                        method_contracts=self.method_contracts,
                        data_semantics=self.data_semantics,
                        dynamic_contract=dynamic_contract,
                        research_framework=self.research_framework
                    )
                    
                    r_script_path = Path(self.path_manager.get_r_script_path(section, stage_name))
                    with open(r_script_path, 'w', encoding='utf-8') as f:
                        f.write(f"# R code file: {r_script_path.name}\n")
                        f.write(f"# Analysis stage: {stage_name}\n")
                        f.write(f"# SAP section: {section}\n")
                        f.write(f"# Generated time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                        f.write(r_code)
                    
                    self.logger.info(f"[{section}] R code saved: {r_script_path}")
                    
                    data_path_for_r = current_data_path
                    self.logger.info(f"[{section}] R will read data: {data_path_for_r}")
                    
                    self.logger.info(f"[{section}] Execute R code...")
                    try:
                        with open(sub_prompt['file_path'], 'r', encoding='utf-8') as spf:
                            sub_prompt_content = spf.read()
                    except Exception:
                        sub_prompt_content = None

                    success, message, output_files = self.code_executor.execute(
                        r_script_path=r_script_path,
                        stage_name=stage_name,
                        section=section,
                        path_manager=self.path_manager,
                        data_path=data_path_for_r,
                        sub_prompt_content=sub_prompt_content
                    )
                    
                    if success:
                        stage_output_dir = Path(self.path_manager.get_stage_paths(section)['stage_output_dir'])
                        
                        consistency_report = self.consistency_checker.check_analysis_results(
                            str(stage_output_dir), stage_name
                        )
                        if consistency_report['blocking_issues']:
                            self.logger.error(f"[{section}] Statistical consistency check failed")
                            for issue in consistency_report['blocking_issues']:
                                self.logger.error(f"  - {issue}")
                        
                        design_validation = self.survey_validator.validate_design_implementation(
                            current_data_path, r_code
                        )
                        self.logger.info(
                            f"[{section}] Survey design: {design_validation['inference_level']}"
                        )
                        
                        self.decision_manager.extract_and_save(
                            stage_output_dir=stage_output_dir,
                            section=section,
                            r_output=message
                        )
                        
                        next_data_path = stage_output_dir / "main_output.csv"
                        
                        if section in ["7.0", "7.1"] and next_data_path.exists():
                            self.logger.info(f"[{section}] Running data quality controller...")
                            quality_result = self.quality_controller.detect_and_fix_issues(
                                data_path=str(next_data_path),
                                output_path=str(next_data_path),
                                quality_report_path=str(stage_output_dir / "data_quality_control_report.json")
                            )
                            
                            if quality_result.get('success'):
                                n_issues = len(quality_result.get('issues_detected', []))
                                n_affected = quality_result.get('affected_samples', 0)
                                self.logger.info(
                                    f"[{section}] Quality control: {n_issues} issues, {n_affected} samples modified"
                                )
                            else:
                                self.logger.warning(f"[{section}] Quality control encountered issues")
                        
                        if next_data_path.exists():
                            current_data_path = str(next_data_path)
                            self.logger.info(f"[{section}] Update data path to: {current_data_path}")
                        else:
                            self.logger.warning(
                                f"[{section}] main_output.csv does not exist, still use: {current_data_path}"
                            )
                    
                    analysis_results.append({
                        'stage_name': stage_name,
                        'section': section,
                        'success': success,
                        'message': message[:500] if len(message) > 500 else message,
                        'output_files': output_files,
                        'error_message': message if not success else None
                    })
                    
                    if success:
                        self.logger.info(f"[{section}] Execution successful")
                    else:
                        self.logger.error(f"[{section}] Execution failed: {message[:200]}")
                
                except Exception as stage_exc:
                    exc_msg = str(stage_exc)
                    self.logger.error(f"[{section}] Processing failed: {exc_msg}")
                    
                    analysis_results.append({
                        'stage_name': stage_name,
                        'section': section,
                        'success': False,
                        'message': exc_msg,
                        'output_files': [],
                        'error_message': exc_msg
                    })
            
            successful_modules = sum(1 for r in analysis_results if r['success'])
            failed_modules = sum(1 for r in analysis_results if not r['success'])
            
            end_time = time.time()
            duration = end_time - start_time
            
            self.logger.info("=" * 60)
            self.logger.info("Analysis execution completed")
            self.logger.info(f"Total modules: {len(sub_prompts)}")
            self.logger.info(f"Successful modules: {successful_modules}")
            self.logger.info(f"Failed modules: {failed_modules}")
            self.logger.info(f"Duration: {duration:.2f} seconds")
            self.logger.info("=" * 60)
            
            return {
                'success': True,
                'status': 'analysis_completed' if successful_modules == len(sub_prompts) else 'analysis_partial',
                'duration': duration,
                'total_modules': len(sub_prompts),
                'successful_modules': successful_modules,
                'failed_modules': failed_modules,
                'detailed_results': analysis_results,
                'audit_log_path': self.log_file
            }
        
        except Exception as e:
            self.logger.error(f"Analysis process failed: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'duration': time.time() - start_time
            }
    
    def _read_file_with_encoding_detection(self, file_path: str) -> str:
        """
        Read file with automatic encoding detection
        
        Args:
            file_path: Path to file
            
        Returns:
            File content as string
        """
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read()
            
            import chardet
            detected = chardet.detect(raw_data)
            encoding = detected['encoding']
            confidence = detected['confidence']
            
            self.logger.info(f"Detected encoding: {encoding} (confidence: {confidence:.2f})")
            
            if encoding is None or confidence < 0.7:
                self.logger.warning(f"Low confidence encoding detection, trying common encodings")
                for enc in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin1']:
                    try:
                        return raw_data.decode(enc)
                    except (UnicodeDecodeError, LookupError):
                        continue
                raise ValueError("Failed to decode file with any common encoding")
            
            return raw_data.decode(encoding)
            
        except Exception as e:
            self.logger.error(f"Encoding detection failed: {e}")
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    self.logger.warning("Falling back to UTF-8 with errors='ignore'")
                    return f.read()
            except Exception as e2:
                raise RuntimeError(f"Failed to read file {file_path}: {e2}")
    
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration file"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def setup_logging(self):
        log_file = self.path_manager.session_dir / f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        
        file_handler_exists = any(
            isinstance(h, logging.FileHandler) and 
            hasattr(h, 'baseFilename') and 
            h.baseFilename == str(log_file)
            for h in root_logger.handlers
        )
        
        if not file_handler_exists:
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                str(log_file),
                maxBytes=10_000_000,
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        
        console_handler_exists = any(
            isinstance(h, logging.StreamHandler) and 
            not isinstance(h, logging.FileHandler)
            for h in root_logger.handlers
        )
        
        if not console_handler_exists:
            enable_console = os.environ.get("ORCH_CONSOLE_LOG", "0") == "1"
            if enable_console:
                console_handler = logging.StreamHandler(stream=sys.stdout)
                console_handler.setLevel(logging.WARNING)
                console_handler.setFormatter(formatter)
                root_logger.addHandler(console_handler)
        
        self.log_file = str(log_file)
    
    def setup_directories(self):
        """Create necessary directory structure (now managed by path_manager)"""
        pass
    
    def _infer_model_profile(self, model_name: str) -> str:
        """Infer model profile based on model name"""
        if not model_name:
            return 'gpt'
        lowered = model_name.lower()
        if 'claude' in lowered or 'sonnet' in lowered or 'anthropic' in lowered:
            return 'claude'
        return 'gpt'
    
    def _load_method_contracts(self) -> Dict[str, Dict[str, Any]]:
        """Load method contracts configuration (optional)"""
        contracts_path = Path(self.workspace_root) / 'contracts' / 'method_contracts.json'
        if not contracts_path.exists():
            self.logger.info("Using dynamic contract extraction mode (no static configuration file)")
            return {}
        try:
            with open(contracts_path, 'r', encoding='utf-8') as f:
                self.logger.info(f"Load static method contracts configuration: {contracts_path}")
                return json.load(f)
        except Exception as exc:
            self.logger.error(f"Load method contracts failed: {exc}")
            return {}
    
    def _load_data_semantics(self) -> Dict[str, Any]:
        """Load data semantics contracts (optional)"""
        semantics_path = Path(self.workspace_root) / 'contracts' / 'data_semantics.json'
        if not semantics_path.exists():
            self.logger.info("Using dynamic data semantics analysis (no static configuration file)")
            return {'variables': [], 'globals': {}}
        try:
            with open(semantics_path, 'r', encoding='utf-8') as f:
                self.logger.info(f"Load static data semantics configuration: {semantics_path}")
                data = json.load(f)
            data.setdefault('variables', [])
            data.setdefault('globals', {})
            return data
        except Exception as exc:
            self.logger.error(f"Load data semantics configuration failed: {exc}")
            return {'variables': [], 'globals': {}}
    
    def _run_data_cleaner_subprocess(self) -> Dict:
        workspace_dir = str(self.path_manager.session_dir)
        script_path = Path(__file__).parent.parent / "modules" / "data_cleaner.py"
        
        cmd = [sys.executable, str(script_path), workspace_dir, "--verbose"]
        self.logger.info(f"Running data_cleaner as subprocess: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            self.logger.info(f"[data_cleaner] returncode={result.returncode}")
            if result.stdout:
                for line in result.stdout.splitlines():
                    if line.strip():
                        if line.strip().startswith("2025-") or "INFO" in line or "ERROR" in line or "WARNING" in line:
                            self.logger.info(f"[data_cleaner] {line}")
                        else:
                            self.logger.info(f"[data_cleaner] {line}")
            if result.stderr:
                for line in result.stderr.splitlines():
                    if line.strip():
                        if "ERROR" in line or "Traceback" in line or "Exception" in line:
                            self.logger.error(f"[data_cleaner] {line}")
                        elif "WARNING" in line:
                            self.logger.warning(f"[data_cleaner] {line}")
                        else:
                            self.logger.info(f"[data_cleaner] {line}")
            
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0
            }
        except subprocess.TimeoutExpired:
            self.logger.error("[data_cleaner] Subprocess timeout after 600 seconds")
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": "Timeout after 600 seconds",
                "success": False
            }
        except Exception as e:
            self.logger.error(f"[data_cleaner] Subprocess failed: {e}", exc_info=True)
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False
            }
    
    def _run_report_generator_subprocess(self, protocol_file: Path) -> Dict:
        script_path = Path(__file__).parent.parent / "modules" / "report_generator.py"
        results_dir = str(self.path_manager.results_dir)
        config_path = Path(self.workspace_root) / "config.json"
        
        cmd = [
            sys.executable,
            str(script_path),
            "--protocol", str(protocol_file),
            "--output-dir", results_dir,
            "--config", str(config_path)
        ]
        self.logger.info(f"Running report_generator as subprocess: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800
            )
            
            self.logger.info(f"[report_generator] returncode={result.returncode}")
            if result.stdout:
                for line in result.stdout.splitlines():
                    self.logger.info(f"[report_generator] {line}")
            if result.stderr:
                for line in result.stderr.splitlines():
                    self.logger.warning(f"[report_generator] {line}")
            
            report_path = None
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.strip().startswith("Location:"):
                        report_path = line.split("Location:", 1)[1].strip()
                        break
            
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0,
                "report_path": report_path
            }
        except subprocess.TimeoutExpired:
            self.logger.error("[report_generator] Subprocess timeout after 1800 seconds")
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": "Timeout after 1800 seconds",
                "success": False,
                "report_path": None
            }
        except Exception as e:
            self.logger.error(f"[report_generator] Subprocess failed: {e}", exc_info=True)
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False,
                "report_path": None
            }
    
    def _generate_report_contract(self) -> Dict:
        results_dir = Path(self.path_manager.results_dir)
        contract = {
            "inference_level": "unknown",
            "weight_var_name": None,
            "weight_status": "missing",
            "strata_variable": None,
            "psu_variable": None,
            "n_total": None,
            "n_by_group": {},
            "missing_data_method": "unknown",
            "exposure_definition": None,
            "outcome_definition": None,
            "design_limitations": None
        }
        
        stage_dirs = sorted(results_dir.glob("7.*"), key=lambda x: x.name)
        design_info = None
        weight_info = None
        inference_levels = []
        weight_usage_by_stage = {}
        
        for stage_dir in stage_dirs:
            if not stage_dir.is_dir():
                continue
            summary_file = stage_dir / "analysis_summary.json"
            if not summary_file.exists():
                continue
            
            try:
                with open(summary_file, 'r', encoding='utf-8') as f:
                    summary = json.load(f)
                
                if 'design' in summary:
                    design = summary['design']
                    stage_name = stage_dir.name
                    
                    if design.get('design_verified_level'):
                        inference_levels.append(design['design_verified_level'])
                        weight_usage_by_stage[stage_name] = design['design_verified_level']
                    
                    if design.get('weight_variable') and not contract['weight_var_name']:
                        contract['weight_var_name'] = design['weight_variable']
                    if design.get('weight_is_placeholder') is not None and contract['weight_status'] == 'missing':
                        contract['weight_status'] = 'placeholder' if design['weight_is_placeholder'] else 'valid'
                    
                    if design.get('strata_variable'):
                        if isinstance(design['strata_variable'], str) and design['strata_variable']:
                            if 'strata_variable' not in contract:
                                contract['strata_variable'] = design['strata_variable']
                            elif not contract.get('strata_variable'):
                                contract['strata_variable'] = design['strata_variable']
                    
                    if design.get('psu_variable'):
                        if isinstance(design['psu_variable'], str) and design['psu_variable']:
                            if 'psu_variable' not in contract:
                                contract['psu_variable'] = design['psu_variable']
                            elif not contract.get('psu_variable'):
                                contract['psu_variable'] = design['psu_variable']
                    
                    if design.get('design_limitations'):
                        if not contract.get('design_limitations') or contract['design_limitations'] == []:
                            contract['design_limitations'] = design['design_limitations']
                        elif isinstance(contract['design_limitations'], str) and 'no strata' in contract['design_limitations'].lower():
                            if isinstance(design['design_limitations'], str) and 'strata' in design['design_limitations'].lower() and 'no' not in design['design_limitations'].lower():
                                contract['design_limitations'] = design['design_limitations']
                    
                    if not design_info:
                        design_info = design
                
                if 'weight_detection' in summary:
                    wd = summary['weight_detection']
                    if wd.get('usable_weight') and wd.get('weight_variable'):
                        contract['weight_var_name'] = wd['weight_variable']
                        contract['weight_status'] = 'valid'
                    weight_info = wd
                
                if 'missing_method' in summary:
                    contract['missing_data_method'] = summary['missing_method']
                elif 'method' in summary and 'missing' in summary['method'].lower():
                    contract['missing_data_method'] = summary['method']
                
                if 'exposure' in summary and summary['exposure'].get('derived_group'):
                    contract['exposure_definition'] = summary['exposure']['derived_group']
                
                if 'outcome' in summary:
                    outcome = summary['outcome']
                    if isinstance(outcome, dict) and outcome.get('variable'):
                        contract['outcome_definition'] = outcome['variable']
                    elif isinstance(outcome, str):
                        contract['outcome_definition'] = outcome
                
                if 'data_dimensions' in summary:
                    dims = summary['data_dimensions']
                    if isinstance(dims, dict) and 'rows' in dims:
                        contract['n_total'] = dims['rows']
                
            except Exception as e:
                self.logger.warning(f"Failed to read {summary_file}: {e}")
        
        if inference_levels:
            design_based_count = inference_levels.count('design_based')
            sample_based_count = inference_levels.count('sample_based')
            if design_based_count > sample_based_count:
                contract['inference_level'] = 'design_based'
            elif sample_based_count > 0:
                contract['inference_level'] = 'sample_based'
            else:
                contract['inference_level'] = inference_levels[0] if inference_levels else 'unknown'
        
        if contract['weight_status'] == 'missing' and contract['weight_var_name']:
            contract['weight_status'] = 'valid'
        
        if contract['inference_level'] == 'design_based' and contract['weight_status'] == 'placeholder':
            contract['inference_level'] = 'sample_based'
        
        if contract.get('strata_variable') or contract.get('psu_variable'):
            if not contract.get('design_limitations') or (isinstance(contract['design_limitations'], str) and 'no strata' in contract['design_limitations'].lower()):
                limitations = []
                if contract.get('strata_variable'):
                    limitations.append(f"Stratified design: {contract['strata_variable']}")
                if contract.get('psu_variable'):
                    limitations.append(f"PSU clustering: {contract['psu_variable']}")
                if contract.get('weight_var_name'):
                    limitations.append(f"Survey weights: {contract['weight_var_name']}")
                if limitations:
                    contract['design_limitations'] = "; ".join(limitations)
                else:
                    contract['design_limitations'] = "Complex survey design detected"
        elif not contract.get('design_limitations'):
            contract['design_limitations'] = "Weight-only design; no strata or PSU information available"
        
        contract_path = results_dir / "report_contract.json"
        with open(contract_path, 'w', encoding='utf-8') as f:
            json.dump(contract, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"Report contract generated: {contract_path}")
        return contract
    
    def postprocess(self) -> Dict:
        self.logger.info("=" * 60)
        self.logger.info("Starting post-processing: cleanup and report generation")
        self.logger.info("=" * 60)
        
        cleanup_summary = None
        dc_result = self._run_data_cleaner_subprocess()
        
        if dc_result["success"]:
            cleanup_summary = "DataCleaner subprocess finished successfully"
            self.logger.info(f"Data cleanup completed: {cleanup_summary}")
        else:
            self.logger.error("DataCleaner subprocess failed")
            self.logger.warning("Continuing with report generation despite cleanup errors...")
        
        self._generate_report_contract()
        
        report_path = None
        upload_dir = self.path_manager.session_dir / "01_uploads"
        protocol_file = None
        
        for ext in ['.docx', '.doc', '.md', '.txt']:
            candidate = upload_dir / f"protocol{ext}"
            if candidate.exists():
                protocol_file = candidate
                break
        
        if protocol_file is None:
            self.logger.error(f"Protocol file not found in {upload_dir}")
        else:
            rg_result = self._run_report_generator_subprocess(protocol_file)
            if rg_result["success"]:
                report_path = rg_result.get("report_path")
                if report_path:
                    self.logger.info(f"Analysis report generated: {report_path}")
                else:
                    self.logger.warning("Report generation completed but report path not found in output")
            else:
                self.logger.error("ReportGenerator subprocess failed")
        
        self.logger.info("=" * 60)
        self.logger.info("Post-processing completed")
        if report_path:
            self.logger.info(f"Report location: {report_path}")
        if cleanup_summary:
            self.logger.info(f"Data cleanup: {cleanup_summary}")
        self.logger.info("=" * 60)
        
        return {
            'success': dc_result["success"] and report_path is not None,
            'report_path': report_path,
            'cleanup_summary': cleanup_summary,
            'audit_log_path': self.log_file,
            'data_cleaner': dc_result,
            'report_generator': rg_result if 'rg_result' in locals() else None
        }

