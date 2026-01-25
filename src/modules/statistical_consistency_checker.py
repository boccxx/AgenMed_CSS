#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import re
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np


class StatisticalConsistencyChecker:
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def check_analysis_results(
        self,
        results_dir: str,
        stage_name: str
    ) -> Dict[str, Any]:
        
        report = {
            'stage': stage_name,
            'checks_performed': [],
            'passed': True,
            'violations': [],
            'warnings': [],
            'blocking_issues': []
        }
        
        results_path = Path(results_dir)
        
        for csv_file in results_path.glob('*.csv'):
            try:
                df = pd.read_csv(csv_file)
                file_report = self._check_csv_consistency(df, csv_file.name)
                report['checks_performed'].append(csv_file.name)
                
                if file_report['violations']:
                    report['violations'].extend(file_report['violations'])
                    report['passed'] = False
                
                if file_report['warnings']:
                    report['warnings'].extend(file_report['warnings'])
                    
                if file_report['blocking_issues']:
                    report['blocking_issues'].extend(file_report['blocking_issues'])
                    
            except Exception as e:
                self.logger.warning(f"Failed to check {csv_file}: {e}")
        
        return report
    
    def _check_csv_consistency(
        self,
        df: pd.DataFrame,
        filename: str
    ) -> Dict[str, Any]:
        
        report = {
            'file': filename,
            'violations': [],
            'warnings': [],
            'blocking_issues': []
        }
        
        has_estimates = any(col.lower() in ['estimate', 'coef', 'coefficient', 'or', 'pr', 'hr', 'beta']
                           for col in df.columns)
        has_se = any('se' in col.lower() or 'std' in col.lower() for col in df.columns)
        has_t = any(col.lower() in ['t', 't_value', 'z', 'z_value'] for col in df.columns)
        has_p = any('p' in col.lower() and 'value' in col.lower() for col in df.columns)
        has_ci = any('ci' in col.lower() or 'lower' in col.lower() or 'upper' in col.lower()
                    for col in df.columns)
        
        if has_estimates and has_p:
            consistency_report = self._check_estimate_p_consistency(df)
            report['violations'].extend(consistency_report['violations'])
            report['warnings'].extend(consistency_report['warnings'])
        
        if has_t and has_p:
            alignment_report = self._check_t_p_alignment(df)
            report['violations'].extend(alignment_report['violations'])
        
        if has_ci and has_estimates:
            ci_report = self._check_ci_contains_estimate(df)
            report['violations'].extend(ci_report['violations'])
            report['blocking_issues'].extend(ci_report['blocking_issues'])
        
        extreme_report = self._check_extreme_values(df)
        report['warnings'].extend(extreme_report['warnings'])
        report['blocking_issues'].extend(extreme_report['blocking_issues'])
        
        return report
    
    def _check_estimate_p_consistency(self, df: pd.DataFrame) -> Dict[str, Any]:
        
        report = {
            'violations': [],
            'warnings': []
        }
        
        est_cols = [col for col in df.columns 
                   if any(term in col.lower() for term in ['estimate', 'coef', 'or', 'pr', 'hr'])]
        p_cols = [col for col in df.columns 
                 if 'p' in col.lower() and 'value' in col.lower()]
        
        if not est_cols or not p_cols:
            return report
        
        est_col = est_cols[0]
        p_col = p_cols[0]
        
        for idx, row in df.iterrows():
            try:
                est = float(row[est_col])
                p = float(row[p_col])
                
                if 'or' in est_col.lower() or 'pr' in est_col.lower() or 'hr' in est_col.lower():
                    if abs(est - 1.0) < 0.05 and p < 0.01:
                        report['violations'].append(
                            f"Row {idx+1}: {est_col}={est:.3f} (approx 1) but p={p:.4f} (<0.01) - inconsistent"
                        )
                else:
                    if abs(est) < 0.01 and p < 0.01:
                        report['violations'].append(
                            f"Row {idx+1}: {est_col}={est:.3f} (approx 0) but p={p:.4f} (<0.01) - inconsistent"
                        )
                
                if 'or' in est_col.lower() or 'pr' in est_col.lower():
                    if (est > 2.0 or est < 0.5) and p > 0.5:
                        report['warnings'].append(
                            f"Row {idx+1}: Large effect size {est_col}={est:.3f} but p={p:.3f} (not significant)"
                        )
                        
            except (ValueError, TypeError):
                continue
        
        return report
    
    def _check_t_p_alignment(self, df: pd.DataFrame) -> Dict[str, Any]:
        
        report = {'violations': []}
        
        t_cols = [col for col in df.columns if col.lower() in ['t', 't_value', 'z', 'z_value']]
        p_cols = [col for col in df.columns if 'p' in col.lower() and 'value' in col.lower()]
        
        if not t_cols or not p_cols:
            return report
        
        t_col = t_cols[0]
        p_col = p_cols[0]
        
        for idx, row in df.iterrows():
            try:
                t_val = float(row[t_col])
                p_val = float(row[p_col])
                
                if abs(t_val) > 2.5 and p_val > 0.05:
                    report['violations'].append(
                        f"Row {idx+1}: |{t_col}|={abs(t_val):.2f} (>2.5) but p={p_val:.3f} (>0.05) - misalignment"
                    )
                elif abs(t_val) < 1.0 and p_val < 0.01:
                    report['violations'].append(
                        f"Row {idx+1}: |{t_col}|={abs(t_val):.2f} (<1) but p={p_val:.4f} (<0.01) - misalignment"
                    )
                    
            except (ValueError, TypeError):
                continue
        
        return report
    
    def _check_ci_contains_estimate(self, df: pd.DataFrame) -> Dict[str, Any]:
        
        report = {
            'violations': [],
            'blocking_issues': []
        }
        
        est_cols = [col for col in df.columns 
                   if any(term in col.lower() for term in ['estimate', 'coef', 'or', 'pr', 'hr'])]
        lower_cols = [col for col in df.columns if 'lower' in col.lower()]
        upper_cols = [col for col in df.columns if 'upper' in col.lower()]
        
        if not est_cols or not lower_cols or not upper_cols:
            return report
        
        est_col = est_cols[0]
        lower_col = lower_cols[0]
        upper_col = upper_cols[0]
        
        for idx, row in df.iterrows():
            try:
                est = float(row[est_col])
                lower = float(row[lower_col])
                upper = float(row[upper_col])
                
                if not (lower <= est <= upper):
                    report['violations'].append(
                        f"Row {idx+1}: Estimate {est:.3f} not in CI [{lower:.3f}, {upper:.3f}]"
                    )
                    report['blocking_issues'].append(
                        f"CRITICAL: Point estimate outside CI at row {idx+1}"
                    )
                    
            except (ValueError, TypeError):
                continue
        
        return report
    
    def _check_extreme_values(self, df: pd.DataFrame) -> Dict[str, Any]:
        
        report = {
            'warnings': [],
            'blocking_issues': []
        }
        
        ratio_cols = [col for col in df.columns 
                     if any(term in col.lower() for term in ['or', 'pr', 'hr']) 
                     and 'p' not in col.lower()]
        
        for col in ratio_cols:
            try:
                extreme_high = df[df[col] > 1000]
                extreme_low = df[df[col] < 0.001]
                
                if len(extreme_high) > 0:
                    report['blocking_issues'].append(
                        f"SEPARATION: {len(extreme_high)} rows with {col} > 1000 (likely separation issue)"
                    )
                    report['blocking_issues'].append(
                        f"ACTION REQUIRED: Filter out or apply Firth correction"
                    )
                
                if len(extreme_low) > 0:
                    report['warnings'].append(
                        f"{len(extreme_low)} rows with {col} < 0.001 (check for separation)"
                    )
                    
            except (ValueError, TypeError):
                continue
        
        p_cols = [col for col in df.columns if 'p' in col.lower() and 'value' in col.lower()]
        
        for col in p_cols:
            try:
                invalid_p = df[(df[col] < 0) | (df[col] > 1)]
                if len(invalid_p) > 0:
                    report['blocking_issues'].append(
                        f"INVALID: {len(invalid_p)} rows with invalid p-values in {col}"
                    )
            except (ValueError, TypeError):
                continue
        
        return report
    
    def generate_validation_gate(
        self,
        consistency_report: Dict[str, Any]
    ) -> Dict[str, Any]:
        
        gate = {
            'allow_proceed': True,
            'allow_interpretation': True,
            'gate_status': 'pass',
            'required_actions': []
        }
        
        if consistency_report['blocking_issues']:
            gate['allow_proceed'] = False
            gate['allow_interpretation'] = False
            gate['gate_status'] = 'fail'
            gate['required_actions'].extend(consistency_report['blocking_issues'])
            gate['required_actions'].append(
                'MANDATORY: Fix statistical inconsistencies before generating final report'
            )
        
        elif consistency_report['violations']:
            gate['allow_interpretation'] = False
            gate['gate_status'] = 'warning'
            gate['required_actions'].append(
                'Review and resolve statistical inconsistencies before interpretation'
            )
        
        return gate
