#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional


class SurveyDesignValidator:
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def validate_design_implementation(
        self,
        data_path: str,
        r_code: str,
        analysis_summary_path: Optional[str] = None
    ) -> Dict[str, Any]:
        
        result = {
            'design_verified': False,
            'weight_implemented': False,
            'strata_implemented': False,
            'psu_implemented': False,
            'design_object_used': False,
            'inference_level': 'exploratory',
            'issues': [],
            'recommendations': []
        }
        
        design_vars = self._check_data_for_design_vars(data_path)
        result.update(design_vars)
        
        code_analysis = self._analyze_r_code(r_code)
        result.update(code_analysis)
        
        if (result['weight_implemented'] and 
            result['strata_implemented'] and 
            result['psu_implemented'] and
            result['design_object_used']):
            result['design_verified'] = True
            result['inference_level'] = 'design_based'
        else:
            result['design_verified'] = False
            result['inference_level'] = 'exploratory'
            
            if not result['weight_implemented']:
                result['issues'].append('Weight variable not found or set to placeholder=1')
            if not result['strata_implemented']:
                result['issues'].append('Strata variable not implemented')
            if not result['psu_implemented']:
                result['issues'].append('PSU variable not implemented')
            if not result['design_object_used']:
                result['issues'].append('survey::svydesign object not consistently used')
            
            result['recommendations'].append(
                'Downgrade all inferential statements to "exploratory analysis without sampling design adjustment"'
            )
            result['recommendations'].append(
                'Remove phrases like "generalizable to population", "design-consistent", "weighted estimates"'
            )
        
        return result
    
    def _check_data_for_design_vars(self, data_path: str) -> Dict[str, Any]:
        
        result = {
            'has_weight_var': False,
            'has_strata_var': False,
            'has_psu_var': False,
            'design_var_names': []
        }
        
        if not data_path or not Path(data_path).exists():
            return result
        
        try:
            import pandas as pd
            df = pd.read_csv(data_path, nrows=100)
            
            weight_patterns = ['weight', 'wt', 'sampling_weight', 'survey_weight']
            for col in df.columns:
                col_lower = col.lower()
                if any(p in col_lower for p in weight_patterns):
                    if df[col].nunique() > 1 or df[col].mean() != 1.0:
                        result['has_weight_var'] = True
                        result['design_var_names'].append(col)
            
            strata_patterns = ['strata', 'stratum', 'sampling_strata']
            for col in df.columns:
                col_lower = col.lower()
                if any(p in col_lower for p in strata_patterns):
                    result['has_strata_var'] = True
                    result['design_var_names'].append(col)
            
            psu_patterns = ['psu', 'cluster', 'primary_sampling_unit']
            for col in df.columns:
                col_lower = col.lower()
                if any(p in col_lower for p in psu_patterns):
                    result['has_psu_var'] = True
                    result['design_var_names'].append(col)
                    
        except Exception as e:
            self.logger.warning(f"Failed to check design variables: {e}")
        
        return result
    
    def _analyze_r_code(self, r_code: str) -> Dict[str, Any]:
        
        result = {
            'weight_implemented': False,
            'strata_implemented': False,
            'psu_implemented': False,
            'design_object_used': False,
            'design_object_name': None,
            'all_analyses_use_design': True
        }
        
        svydesign_match = re.search(
            r'(\w+)\s*<-\s*svydesign\s*\(',
            r_code
        )
        if svydesign_match:
            result['design_object_name'] = svydesign_match.group(1)
            result['design_object_used'] = True
            
            design_call = self._extract_function_call(r_code, 'svydesign')
            if design_call:
                if 'weights' in design_call and '~1' not in design_call:
                    result['weight_implemented'] = True
                if 'strata' in design_call:
                    result['strata_implemented'] = True
                if 'ids' in design_call and '~1' not in design_call:
                    result['psu_implemented'] = True
        
        if result['design_object_name']:
            non_survey_patterns = [
                r'lm\s*\([^)]*data\s*=\s*(?!' + result['design_object_name'] + ')',
                r'glm\s*\([^)]*data\s*=\s*(?!' + result['design_object_name'] + ')',
                r'table\s*\([^)]*\$',
                r'prop\.table\s*\('
            ]
            
            for pattern in non_survey_patterns:
                if re.search(pattern, r_code):
                    result['all_analyses_use_design'] = False
                    break
        
        return result
    
    def _extract_function_call(self, code: str, func_name: str) -> Optional[str]:
        
        pattern = rf'{func_name}\s*\([^)]*\)'
        match = re.search(pattern, code, re.DOTALL)
        return match.group(0) if match else None
    
    def adjust_wording_for_inference_level(
        self,
        text: str,
        inference_level: str
    ) -> str:
        
        if inference_level == 'exploratory':
            replacements = {
                r'generalizable to (\w+ )?population': r'observed in this sample',
                r'population-level (estimate|inference)': r'sample-level \1',
                r'design-consistent': r'descriptive',
                r'weighted (estimate|analysis)': r'unweighted \1',
                r'representative of': r'observed in',
                r'complex survey design': r'simple random sampling assumption',
                r'sampling weight': r'equal weight (placeholder)',
            }
            
            for pattern, replacement in replacements.items():
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
            
            if 'exploratory analysis' not in text.lower():
                text = (
                    "Note: This is an exploratory analysis without sampling design adjustment. "
                    + text
                )
        
        return text

