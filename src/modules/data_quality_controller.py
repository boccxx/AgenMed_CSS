#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Quality Controller - Closed-loop data cleaning: detect → fix → verify"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd


class DataQualityController:
    """Enforce closed-loop data quality control"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def detect_and_fix_issues(
        self,
        data_path: str,
        output_path: str,
        quality_report_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Detect data quality issues and apply automatic fixes
        
        Args:
            data_path: Input data path
            output_path: Output cleaned data path
            quality_report_path: Path to save quality report
            
        Returns:
            Quality control result with before/after statistics
        """
        result = {
            'success': False,
            'issues_detected': [],
            'fixes_applied': [],
            'before_stats': {},
            'after_stats': {},
            'affected_samples': 0,
            'cleaning_rules': []
        }
        
        try:
            df = pd.read_csv(data_path)
            df_original = df.copy()
            result['before_stats'] = self._compute_statistics(df)
            
            # Detect issues
            issues = self._detect_quality_issues(df)
            result['issues_detected'] = [issue['description'] for issue in issues]
            
            if not issues:
                self.logger.info("No data quality issues detected")
                df.to_csv(output_path, index=False)
                result['success'] = True
                return result
            
            # Apply fixes
            for issue in issues:
                fix_result = self._apply_fix(df, issue)
                result['fixes_applied'].append(fix_result)
                result['affected_samples'] += fix_result['n_affected']
                result['cleaning_rules'].append(fix_result['rule'])
            
            # Compute after stats
            result['after_stats'] = self._compute_statistics(df)
            
            # Save cleaned data
            df.to_csv(output_path, index=False)
            
            # Generate comparison report
            comparison = self._generate_comparison(
                result['before_stats'],
                result['after_stats'],
                result['fixes_applied']
            )
            
            if quality_report_path:
                self._save_quality_report(
                    quality_report_path,
                    result,
                    comparison
                )
            
            result['success'] = True
            result['comparison'] = comparison
            
            self.logger.info(
                f"Data cleaning completed: {len(issues)} issues detected, "
                f"{result['affected_samples']} samples affected"
            )
            
        except Exception as e:
            self.logger.error(f"Data quality control failed: {e}")
            result['error'] = str(e)
        
        return result
    
    def _detect_quality_issues(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Detect various data quality issues"""
        issues = []
        
        for col in df.columns:
            if col.endswith('_flag') or col.endswith('_outlier_flag'):
                continue
                
            if pd.api.types.is_numeric_dtype(df[col]):
                # BMI checks
                if 'bmi' in col.lower():
                    outliers = df[(df[col] < 10) | (df[col] > 70)]
                    if len(outliers) > 0:
                        issues.append({
                            'type': 'range_violation',
                            'variable': col,
                            'description': f'{col}: {len(outliers)} extreme values outside [10, 70]',
                            'strategy': 'set_missing',
                            'condition': lambda x: (x < 10) | (x > 70),
                            'n_affected': len(outliers)
                        })
                
                # Age checks
                elif 'age' in col.lower():
                    outliers = df[(df[col] < 0) | (df[col] > 120)]
                    if len(outliers) > 0:
                        issues.append({
                            'type': 'range_violation',
                            'variable': col,
                            'description': f'{col}: {len(outliers)} values outside [0, 120]',
                            'strategy': 'set_missing',
                            'condition': lambda x: (x < 0) | (x > 120),
                            'n_affected': len(outliers)
                        })
                
                # Biomarker checks
                biomarker_keywords = ['hemoglobin', 'hb', 'glucose', 'cholesterol', 'triglyceride',
                                     'creatinine', 'bilirubin', 'urea', 'albumin', 'protein']
                if any(kw in col.lower() for kw in biomarker_keywords):
                    median_val = df[col].median()
                    if pd.notna(median_val) and median_val > 1:
                        suspiciously_low = df[(df[col] > 0) & (df[col] < median_val * 0.1)]
                        if len(suspiciously_low) > 0:
                            issues.append({
                                'type': 'range_violation',
                                'variable': col,
                                'description': f'{col}: {len(suspiciously_low)} suspiciously low values (<10% of median)',
                                'strategy': 'set_missing',
                                'condition': lambda x: (x > 0) & (x < median_val * 0.1),
                                'n_affected': len(suspiciously_low)
                        })
                
                # General extreme values (IQR method)
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                if IQR > 0:
                    lower_bound = Q1 - 5 * IQR
                    upper_bound = Q3 + 5 * IQR
                    extreme = df[(df[col] < lower_bound) | (df[col] > upper_bound)]
                    if len(extreme) > df.shape[0] * 0.01:  # >1% extreme values
                        issues.append({
                            'type': 'extreme_outlier',
                            'variable': col,
                            'description': f'{col}: {len(extreme)} extreme outliers (>5*IQR)',
                            'strategy': 'winsorize',
                            'lower_bound': lower_bound,
                            'upper_bound': upper_bound,
                            'n_affected': len(extreme)
                        })
            
            # Logical inconsistencies
            # Example: negative values in non-negative variables
            if any(keyword in col.lower() for keyword in ['count', 'number', 'duration']):
                if pd.api.types.is_numeric_dtype(df[col]):
                    negative = df[df[col] < 0]
                    if len(negative) > 0:
                        issues.append({
                            'type': 'logical_error',
                            'variable': col,
                            'description': f'{col}: {len(negative)} negative values in non-negative variable',
                            'strategy': 'set_missing',
                            'condition': lambda x: x < 0,
                            'n_affected': len(negative)
                        })
        
        return issues
    
    def _apply_fix(self, df: pd.DataFrame, issue: Dict[str, Any]) -> Dict[str, Any]:
        """Apply fix for detected issue"""
        fix_result = {
            'issue_type': issue['type'],
            'variable': issue['variable'],
            'strategy': issue['strategy'],
            'n_affected': issue['n_affected'],
            'rule': ''
        }
        
        col = issue['variable']
        
        if issue['strategy'] == 'set_missing':
            condition = issue['condition']
            mask = condition(df[col])
            df.loc[mask, col] = pd.NA
            fix_result['rule'] = f"Set to missing: {issue['description']}"
            
        elif issue['strategy'] == 'winsorize':
            lower = issue['lower_bound']
            upper = issue['upper_bound']
            df.loc[df[col] < lower, col] = lower
            df.loc[df[col] > upper, col] = upper
            fix_result['rule'] = f"Winsorize to [{lower:.2f}, {upper:.2f}]"
            
        elif issue['strategy'] == 'exclude':
            condition = issue['condition']
            mask = condition(df[col])
            df = df[~mask].copy()
            fix_result['rule'] = f"Exclude samples: {issue['description']}"
        
        return fix_result
    
    def _compute_statistics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Compute summary statistics for numeric variables"""
        stats = {}
        
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                stats[col] = {
                    'n': df[col].notna().sum(),
                    'mean': df[col].mean(),
                    'sd': df[col].std(),
                    'min': df[col].min(),
                    'max': df[col].max(),
                    'q25': df[col].quantile(0.25),
                    'q50': df[col].quantile(0.50),
                    'q75': df[col].quantile(0.75),
                }
        
        return stats
    
    def _generate_comparison(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        fixes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate before-after comparison"""
        comparison = {
            'variables_affected': [],
            'statistics_change': {}
        }
        
        for var in before.keys():
            if var in after:
                b = before[var]
                a = after[var]
                
                change = {
                    'variable': var,
                    'n_change': a['n'] - b['n'],
                    'mean_change': a['mean'] - b['mean'] if pd.notna(a['mean']) and pd.notna(b['mean']) else None,
                    'sd_change': a['sd'] - b['sd'] if pd.notna(a['sd']) and pd.notna(b['sd']) else None,
                    'range_before': [b['min'], b['max']],
                    'range_after': [a['min'], a['max']]
                }
                
                comparison['statistics_change'][var] = change
                comparison['variables_affected'].append(var)
        
        return comparison
    
    def _save_quality_report(
        self,
        report_path: str,
        result: Dict[str, Any],
        comparison: Dict[str, Any]
    ):
        """Save quality control report"""
        report = {
            'summary': {
                'issues_detected': len(result['issues_detected']),
                'fixes_applied': len(result['fixes_applied']),
                'affected_samples': result['affected_samples']
            },
            'issues': result['issues_detected'],
            'cleaning_rules': result['cleaning_rules'],
            'comparison': comparison
        }
        
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.logger.info(f"Quality report saved: {report_path}")
    
    def generate_quality_gate_decision(
        self,
        quality_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate quality gate decision: proceed or block
        
        Returns:
            Decision with allow_proceed flag
        """
        decision = {
            'allow_proceed': True,
            'gate_status': 'pass',
            'blocking_issues': [],
            'warnings': []
        }
        
        # Check if critical issues remain unresolved
        if quality_result.get('success', False):
            if quality_result.get('affected_samples', 0) > 0:
                decision['warnings'].append(
                    f"{quality_result['affected_samples']} samples were modified or excluded"
                )
        else:
            decision['allow_proceed'] = False
            decision['gate_status'] = 'fail'
            decision['blocking_issues'].append(
                'Data quality control failed - cannot proceed to imputation/modeling'
            )
        
        return decision

