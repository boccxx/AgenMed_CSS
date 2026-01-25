#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data analysis module - generic data profile analysis"""

import logging
from pathlib import Path
from typing import Any, Dict, List


class DataProfiler:
    """Generic data profiler, analyze data file structure and generate profile"""
    
    def __init__(self):
        """Initialize data profiler"""
        self.logger = logging.getLogger(__name__)
        self._cache: Dict[str, Dict[str, Any]] = {} 
    
    def get_profile(self, data_path: str) -> Dict[str, Any]:
        """
        Get data profile (with cache based on file modification time)
        
        Args:
            data_path: Data file path
            
        Returns:
            Data profile dictionary, containing:
            - info_text: Human-readable data information text
            - schema: Variable list and type information
        """
        if not data_path:
            return {'info_text': '', 'schema': []}
   
        abs_path = str(Path(data_path).resolve())
        data_file = Path(abs_path)
        
        if not data_file.exists():
            return {'info_text': '', 'schema': []}
        
        file_mtime = data_file.stat().st_mtime
        
        cache_key = f"{abs_path}:{file_mtime}"
        
        if cache_key in self._cache:
            self.logger.info(f"Using cached data profile: {data_path}")
            return self._cache[cache_key]

        profile = self._analyze_data_structure(abs_path)
        self._cache[cache_key] = profile
        
        old_keys = [k for k in self._cache.keys() if k.startswith(f"{abs_path}:") and k != cache_key]
        for old_key in old_keys:
            del self._cache[old_key]
        
        return profile
    
    def get_quick_snapshot(self, data_path: str) -> str:
        """
        Get quick snapshot of data (without cache, always read latest data)
        Designed for data transfer between stages, for validation and error fixing
        
        Args:
            data_path: Data file path
            
        Returns:
            Simple data snapshot text, containing variable list, key types, sample size, etc.
        """
        if not data_path or not Path(data_path).exists():
            return "Data file does not exist or path is empty"
        
        try:
            import pandas as pd
            from pandas.api import types as pdt

            df_sample = pd.read_csv(data_path, nrows=50, encoding='utf-8')
            df_full = pd.read_csv(data_path, encoding='utf-8')

            total_rows = len(df_full)
            
            snapshot_lines = [
                f"Current stage data snapshot ({data_path})",
                f"- Sample size: {total_rows} rows",
                f"- Number of variables: {len(df_sample.columns)} columns",
                "",
                "Available variables (only use these):",
            ]
            
            for col in df_sample.columns:
                dtype = df_sample[col].dtype
                nunique_sample = df_sample[col].nunique()
                nunique_full = df_full[col].nunique()
                
                if nunique_full <= 20:
                    unique_vals = sorted(df_full[col].dropna().unique().tolist())
                    snapshot_lines.append(
                        f"  - {col}: {dtype}, {nunique_full} levels → {unique_vals}"
                    )
                elif nunique_sample <= 10 or dtype == 'object':
                    unique_vals = df_sample[col].dropna().unique()
                    snapshot_lines.append(
                        f"  - {col}: {dtype}, {nunique_full} levels → {list(unique_vals[:5])}"
                    )
                else:
                    snapshot_lines.append(f"  - {col}: {dtype}, continuous variable")
            
            snapshot_lines.extend([
                "",
                "Validation tips:",
                "- The number of levels of factor variables may be different from expectations",
                "- Do not assume that variables are always binary or have specific number of levels",
                "- Use friendly data processing rather than strict stop() validation",
            ])
            
            return "\n".join(snapshot_lines)
            
        except Exception as e:
            self.logger.error(f"Failed to generate data snapshot: {e}")
            return f"Failed to generate data snapshot: {e}"
    
    def _analyze_data_structure(self, data_path: str) -> Dict[str, Any]:
        """
        Analyze data file structure
        
        Args:
            data_path: Data file path
            
        Returns:
            Data profile dictionary
        """
        profile: Dict[str, Any] = {
            'info_text': '',
            'schema': []
        }
        
        try:
            import pandas as pd
            from pandas.api import types as pdt

            if not data_path.endswith('.csv'):
                self.logger.warning(f"Unsupported data file format: {data_path}")
                return profile

            self.logger.info(f"Reading data file for analysis: {data_path}")
            df_sample = pd.read_csv(data_path, nrows=100, encoding='utf-8')
            
            df_full = pd.read_csv(data_path, encoding='utf-8')
            n_total = len(df_full)

            schema: List[Dict[str, Any]] = []
            for col in df_sample.columns:
                dtype = df_sample[col].dtype
                schema.append({
                    'name': col,
                    'dtype': str(dtype),
                    'role': None, 
                    'level': 'continuous' if pdt.is_numeric_dtype(dtype) else 'categorical',
                    'aliases': []
                })

            info_lines = [
                f"Data file: {data_path}",
                f"Total observations: {n_total}",
                f"Total variables: {df_sample.shape[1]}",
                "",
                "Variable summary (statistics from full data, sample values from first 100 rows):",
            ]

            weight_vars = [
                col for col in df_full.columns 
                if 'weight' in col.lower()
            ]
            has_weight = len(weight_vars) > 0

            for col in df_full.columns:
                dtype_str = str(df_full[col].dtype)
                weight_note = " [WEIGHT]" if col in weight_vars else ""
                
                n_unique_full = df_full[col].nunique()
                n_missing_full = df_full[col].isna().sum()
                pct_missing = (n_missing_full / n_total * 100) if n_total > 0 else 0
                
                if n_unique_full <= 20:
                    sample_values = sorted(df_full[col].dropna().unique().tolist())
                else:
                    sample_values = df_sample[col].dropna().head(5).tolist()
                
                if pdt.is_numeric_dtype(df_full[col].dtype) and n_unique_full > 10:
                    min_val = df_full[col].min()
                    max_val = df_full[col].max()
                    median_val = df_full[col].median()
                    info_lines.append(
                        f"- {col}{weight_note}: {dtype_str}, n_unique={n_unique_full}, "
                        f"range=[{min_val:.2f}, {max_val:.2f}], median={median_val:.2f}, "
                        f"missing={pct_missing:.1f}%, sample={sample_values[:5]}"
                    )
                else:
                    info_lines.append(
                        f"- {col}{weight_note}: {dtype_str}, n_unique={n_unique_full}, "
                        f"missing={pct_missing:.1f}%, levels={sample_values}"
                    )
            
            info_lines.extend([
                "",
                "Notes:",
                "- n_unique, range, median computed from FULL dataset (all rows)",
                "- levels: all unique values if n_unique <= 20; sample: first 5 values from data if n_unique > 20",
                "- Use detect_weight_variable() for accurate weight validation",
                "",
                "Variable usage constraints:",
                "- ONLY use variables listed above",
                "- For categorical variables: use ONLY the levels shown, do NOT use protocol text as substitute",
            ])
            
            profile['info_text'] = "\n".join(info_lines)
            profile['schema'] = schema
            
            self.logger.info(f"Data analysis completed: {len(schema)} variables")
            
        except Exception as e:
            self.logger.error(f"Failed to analyze data structure: {e}")
        
        return profile

    def detect_weight_variable(self, data_path: str) -> Dict[str, Any]:
        if not data_path or not Path(data_path).exists():
            return {
                'weight_variable': None,
                'usable_weight': False,
                'weight_summary': {},
                'detection_reason': 'data file not found'
            }
        
        try:
            import pandas as pd
            
            df = pd.read_csv(data_path, encoding='utf-8')
            
            candidate_names = ['Sampling_Weight', 'survey_weight', 'weight', 'weights', 'wgt']
            weight_col = None
            
            for name in candidate_names:
                if name in df.columns:
                    weight_col = name
                    break
            
            if weight_col is None:
                fuzzy_matches = [col for col in df.columns if 'weight' in col.lower()]
                if fuzzy_matches:
                    weight_col = fuzzy_matches[0]
            
            if weight_col is None:
                return {
                    'weight_variable': None,
                    'usable_weight': False,
                    'weight_summary': {},
                    'detection_reason': 'no weight variable found'
                }
            
            weight_series = df[weight_col].dropna()
            n_unique = weight_series.nunique()
            pct_missing = df[weight_col].isna().mean() * 100
            has_nonpositive = (weight_series <= 0).any()
            all_equal_one = ((weight_series - 1).abs() < 1e-6).all()
            
            weight_summary = {
                'min': float(weight_series.min()),
                'median': float(weight_series.median()),
                'max': float(weight_series.max()),
                'n_unique': int(n_unique),
                'pct_missing': float(pct_missing)
            }
            
            usable = n_unique > 1 and not has_nonpositive and pct_missing < 5
            
            if not usable:
                if all_equal_one:
                    reason = 'all values equal to 1'
                elif n_unique == 1:
                    reason = f'all values constant ({weight_series.iloc[0]:.2f})'
                elif has_nonpositive:
                    reason = 'contains non-positive values'
                elif pct_missing >= 5:
                    reason = f'high missing rate ({pct_missing:.1f}%)'
                else:
                    reason = 'failed validation criteria'
            else:
                reason = 'weight variable is usable'
            
            return {
                'weight_variable': weight_col,
                'usable_weight': usable,
                'weight_summary': weight_summary,
                'detection_reason': reason
            }
            
        except Exception as e:
            self.logger.error(f"Weight detection failed: {e}")
            return {
                'weight_variable': None,
                'usable_weight': False,
                'weight_summary': {},
                'detection_reason': f'detection error: {str(e)}'
            }

    def detect_sparse_variables(self, data_path: str, min_count: int = 10) -> Dict[str, Any]:
        """
        Detect sparse variables, find separation problems early (generic method)
        
        Args:
            data_path: Data file path
            min_count: Minimum sample size threshold
            
        Returns:
            Sparse variable detection result dictionary
        """
        if not data_path or not Path(data_path).exists():
            return {
                'sparse_variables': [],
                'separation_risk': {},
                'recommendations': [],
                'has_separation_risk': False
            }
        
        try:
            import pandas as pd

            df = pd.read_csv(data_path, encoding='utf-8')
            
            sparse_variables = []
            separation_risk = {}
            recommendations = []

            for col in df.columns:
                if df[col].dtype == 'object' or df[col].nunique() <= 20: 
                    value_counts = df[col].value_counts()
                    sparse_levels = value_counts[value_counts < min_count]
                    
                    if len(sparse_levels) > 0:
                        sparse_variables.append(col)
                        separation_risk[col] = {
                            'total_levels': len(value_counts),
                            'sparse_levels': len(sparse_levels),
                            'sparse_details': sparse_levels.to_dict(),
                            'risk_level': 'high' if len(sparse_levels) > len(value_counts) * 0.5 else 'medium'
                        }

                        if len(sparse_levels) > len(value_counts) * 0.5:
                            recommendations.append(f"Variable '{col}' has more than 50% of levels with sample size < {min_count}, suggest excluding or merging")
                        else:
                            recommendations.append(f"Variable '{col}' has {len(sparse_levels)} sparse levels, suggest merging to 'other' category")
            
            return {
                'sparse_variables': sparse_variables,
                'separation_risk': separation_risk,
                'recommendations': recommendations,
                'has_separation_risk': len(sparse_variables) > 0,
                'min_count_threshold': min_count
            }
            
        except Exception as e:
            self.logger.error(f"Failed to detect sparse variables: {e}")
            return {
                'sparse_variables': [],
                'separation_risk': {},
                'recommendations': [f"Failed to detect sparse variables: {e}"],
                'has_separation_risk': False
            }
