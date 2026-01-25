#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Decision management module - complete global decision extraction, storage and transmission functionality"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class DecisionManager:
    """Global decision manager, responsible for extracting, storing and passing decisions across stages"""
    
    def __init__(self, decisions_file_path: str):
        """
        Initialize decision manager
        
        Args:
            decisions_file_path: Full path to the global decision file
        """
        self.logger = logging.getLogger(__name__)
        self.decisions_file = Path(decisions_file_path)

        self.decisions_file.parent.mkdir(parents=True, exist_ok=True)

        if not self.decisions_file.exists():
            self._save_decisions({})
    
    def extract_and_save(
        self, 
        stage_output_dir: Path, 
        section: str, 
        r_output: str
    ) -> None:
        """
        Extract decisions from stage output and save to global decision file
        
        Args:
            stage_output_dir: Stage output directory
            section: Stage number (e.g. "7.1")
            r_output: Standard output of R code execution
        """
        try:
            global_decisions = self._load_decisions()
            
            summary_file = stage_output_dir / 'analysis_summary.json'
            stage_summary = {}
            if summary_file.exists():
                with open(summary_file, 'r', encoding='utf-8') as f:
                    stage_summary = json.load(f)
            
            stage_key = f"stage_{section}"
            global_decisions[stage_key] = {
                'timestamp': datetime.now().isoformat(),
                'methods_executed': [],
                'key_parameters': {},
                'critical_findings': [],
                'next_stage_guidance': {}
            }

            if 'critical_decisions' in stage_summary:
                for decision in stage_summary['critical_decisions']:
                    decision_type = self._classify_decision(decision)
                    
                    if decision_type == 'normality':
                        if 'normality_tests' not in global_decisions:
                            global_decisions['normality_tests'] = {}
                        global_decisions['normality_tests'][section] = decision
                    
                    elif decision_type == 'model':
                        if 'model_specifications' not in global_decisions:
                            global_decisions['model_specifications'] = {}
                        global_decisions['model_specifications'][section] = decision
                    
                    elif decision_type == 'variable':
                        if 'variable_decisions' not in global_decisions:
                            global_decisions['variable_decisions'] = {}
                        global_decisions['variable_decisions'][section] = decision
                    
                    global_decisions[stage_key]['critical_findings'].append(decision)
            
            if 'statistical_methods_summary' in stage_summary:
                global_decisions[stage_key]['methods_executed'] = [
                    stage_summary['statistical_methods_summary']
                ]
            
            if 'next_stage_requirements' in stage_summary:
                global_decisions[stage_key]['next_stage_guidance'] = \
                    stage_summary['next_stage_requirements']
            
            self._extract_from_r_output(r_output, global_decisions[stage_key])
            
            self._save_decisions(global_decisions)
            
            self.logger.info(f"Global decisions updated: {section}")
            
        except Exception as e:
            self.logger.warning(f"Failed to extract global decisions: {e}")
    
    def get_for_stage(self, current_section: str) -> str:
        """
        Get previous decisions affecting the current stage (formatted as guidance text)
        
        Args:
            current_section: Current stage number (e.g. "7.2")
            
        Returns:
            Formatted text of previous decisions
        """
        try:
            num_match = re.search(r'(\d+\.\d+)', current_section)
            if not num_match:
                return "Cannot parse current stage number, will execute standard method."
            
            current_num = float(num_match.group(1))
            
            global_decisions = self._load_decisions()
            
            if not global_decisions:
                return "This is the first analysis stage, no previous findings to apply."
            
            guidance_info = "Previous stage key findings (please apply when generating R code):\n"
            has_findings = False
            
            for stage_key, stage_info in global_decisions.items():
                if stage_key.startswith('stage_'):
                    stage_num_str = stage_key.replace('stage_', '')
                    try:
                        stage_num = float(stage_num_str)
                        
                        if stage_num < current_num:
                            guidance_info += f"\nStage {stage_num} findings:"
                            
                            if 'critical_findings' in stage_info and stage_info['critical_findings']:
                                for finding in stage_info['critical_findings']:
                                    guidance_info += f"\n  • {finding}"
                                has_findings = True
                            
                            if 'methods_executed' in stage_info and stage_info['methods_executed']:
                                methods = stage_info['methods_executed']
                                if methods:
                                    guidance_info += f"\n  • 使用方法: {', '.join(str(m) for m in methods)}"
                    
                    except ValueError:
                        continue
            
            if not has_findings:
                return "No previous findings to apply."
            
            return guidance_info
            
        except Exception as e:
            self.logger.warning(f"Failed to read global decisions for code generation: {e}")
            return "Failed to read previous stage key findings, will execute standard method."
    
    def _classify_decision(self, decision_text: str) -> str:
        """
        Classify decision type
        
        Args:
            decision_text: Decision text
            
        Returns:
            Decision type: 'normality'/'model'/'variable'/'other'
        """
        decision_lower = decision_text.lower()
        
        if any(keyword in decision_lower for keyword in ['normality', 'distribution']):
            return 'normality'
        
        if any(keyword in decision_lower for keyword in ['model', 'regression']):
            return 'model'
        
        if any(keyword in decision_lower for keyword in ['variable', 'factor', 'reference']):
            return 'variable'
        
        return 'other'
    
    def _extract_from_r_output(self, r_output: str, stage_decisions: Dict) -> None:
        """
        Extract key information from R output
        
        Args:
            r_output: Standard output of R code execution
            stage_decisions: Current stage decision dictionary (will be modified)
        """
        r_lines = r_output.split('\n')
        
        for line in r_lines:
            if '✔' in line and 'successfully executed' in line:
                method_name = line.split('✔')[1].split('successfully executed')[0].strip()
                stage_decisions['methods_executed'].append(method_name)
            
            elif 'glmer(' in line or 'lmer(' in line:
                stage_decisions['key_parameters']['mixed_effects_used'] = True
            
            elif 'binomial(link = "log")' in line:
                stage_decisions['key_parameters']['link_function'] = 'log-binomial'
    
    def _load_decisions(self) -> Dict[str, Any]:
        """Load global decision file"""
        try:
            if self.decisions_file.exists():
                with open(self.decisions_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            self.logger.error(f"Failed to load global decisions: {e}")
            return {}
    
    def _save_decisions(self, decisions: Dict[str, Any]) -> None:
        """Save global decisions to file"""
        try:
            temp_file = self.decisions_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(decisions, f, ensure_ascii=False, indent=2)
            temp_file.replace(self.decisions_file)
        except Exception as e:
            self.logger.error(f"Failed to save global decisions: {e}")



