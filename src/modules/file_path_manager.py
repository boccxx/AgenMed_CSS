#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File Path Manager Agent
Unified management of all file path issues in the statistical analysis workflow
Solving path confusion problems in multi-stage analysis
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging
import shutil
from datetime import datetime
import pandas as pd
import csv

from .r_code_templates import RCodeTemplates


class FilePathManager:
    """File Path Manager Agent"""
    
    def __init__(self, workspace_root: str, config: Dict, session_id: Optional[str] = None):
        """
        Initialize path manager
        
        Args:
            workspace_root: Absolute path of workspace root directory
            config: Configuration dictionary
            session_id: Session ID (used to create independent workspace)
        """
        self.workspace_root = Path(workspace_root).resolve()
        self.config = config
        self.logger = logging.getLogger(__name__)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if session_id:
            session_suffix = session_id[:8]
        else:
            import uuid
            session_suffix = str(uuid.uuid4())[:8]
        self.session_dir = self.workspace_root / "workspace" / f"analysis_{timestamp}_{session_suffix}"

        self.upload_dir = self.session_dir / "01_uploads"
        self.r_scripts_dir = self.session_dir / "02_r_scripts"
        self.output_root = self.session_dir / "03_results"
        self.results_dir = self.output_root  # Alias for compatibility
        self.report_dir = self.session_dir / "04_reports"
        self.temp_dir = self.session_dir / "_temp"

        self.global_decisions_dir = self.output_root / '_decisions'

        for dir_path in [self.upload_dir, self.r_scripts_dir, self.output_root, 
                         self.report_dir, self.temp_dir, self.global_decisions_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Workspace created: {self.session_dir}")
    
    def preprocess_csv_for_r(self, input_file: str, output_file: str) -> bool:
        """
        Preprocess CSV file to ensure R can read it correctly
        
        Solve CSV parsing issues:
        1. Handle string values containing commas
        2. Ensure column number consistency
        3. Fix encoding issues
        
        Args:
            input_file: Input CSV file path
            output_file: Output CSV file path
            
        Returns:
            bool: Whether preprocessing succeeded
        """
        try:
            self.logger.info(f"Starting to preprocess CSV file: {input_file}")

            df = pd.read_csv(input_file, encoding='utf-8', dtype=str)

            for col in df.columns:
                if df[col].dtype == 'object': 
                    mask = df[col].str.contains(',', na=False) & ~df[col].str.startswith('"')
                    if mask.any():
                        self.logger.warning(f"Found {mask.sum()} values containing commas in column '{col}', fixing...")
                        df.loc[mask, col] = df.loc[mask, col].apply(lambda x: f'"{x}"' if pd.notna(x) else x)
            
            expected_cols = len(df.columns)
            inconsistent_rows = []
            
            for i, row in df.iterrows():
                if row.isna().sum() > expected_cols * 0.5:  
                    inconsistent_rows.append(i)
            
            if inconsistent_rows:
                self.logger.warning(f"Found {len(inconsistent_rows)} rows with potential issues, skipping these rows")
                df = df.drop(inconsistent_rows)
            
            df.to_csv(output_file, index=False, encoding='utf-8', quoting=csv.QUOTE_MINIMAL)
            
            self.logger.info(f"CSV preprocessing completed: {output_file}")
            self.logger.info(f"Processed {len(df)} rows and {len(df.columns)} columns")
            
            return True
            
        except Exception as e:
            self.logger.error(f"CSV preprocessing failed: {e}")
            try:
                shutil.copy2(input_file, output_file)
                self.logger.info(f"Copied original file to: {output_file}")
                return True
            except Exception as copy_error:
                self.logger.error(f"Failed to copy original file: {copy_error}")
                return False
    
    def get_stage_paths(self, section: str) -> Dict[str, str]:
        """
        Get all standard paths for the specified stage
        
        Args:
            section: Stage number, such as "7.1", "7.2"
            
        Returns:
            Dictionary containing all paths for this stage
        """
        import re
        num_match = re.search(r'(\d+\.\d+)', section)
        if num_match:
            clean_section = num_match.group(1)
        else:
            clean_section = section
        
        stage_dir = self.output_root / clean_section
        stage_dir.mkdir(parents=True, exist_ok=True)
        
        return {
            'stage_output_dir': str(stage_dir),
            'main_output_csv': 'main_output.csv',
            'analysis_summary_json': 'analysis_summary.json',
            'input_data_csv': 'data.csv',
            'main_output_csv_abs': str(stage_dir / 'main_output.csv'),
            'analysis_summary_json_abs': str(stage_dir / 'analysis_summary.json'),
            'input_data_csv_abs': str(stage_dir / 'data.csv'),
            'r_script_dir': str(self.r_scripts_dir),
        }
    
    def get_data_reading_strategy(self, current_section: str) -> Dict[str, str]:
        """
        Get data reading strategy for the current stage
        
        Args:
            current_section: Current stage number, such as "7.2"
            
        Returns:
            Data reading strategy dictionary
        """
        try:
            import re
            num_match = re.search(r'(\d+\.\d+)', current_section)
            if num_match:
                current_num = float(num_match.group(1))
            else:
                current_num = float(current_section)
            
            prev_num = current_num - 0.1
            prev_section = f"{prev_num:.1f}"
        except:
            return {
                'strategy': 'use_original',
                'primary_source': self.workspace_root / 'data.csv',
                'primary_source_relative': 'data.csv',
                'has_previous_stage': False,
                'reading_code': 'data <- read.csv("data.csv", stringsAsFactors = FALSE)'
            }
        
        prev_paths = self.get_stage_paths(prev_section)
        prev_main_output = Path(prev_paths['main_output_csv_abs'])
        prev_summary = Path(prev_paths['analysis_summary_json_abs'])
        
        has_prev_data = prev_main_output.exists()
        has_prev_summary = prev_summary.exists()
        
        if has_prev_data:
            current_stage_dir = Path(self.get_stage_paths(current_section)['stage_output_dir'])
            relative_path = os.path.relpath(prev_main_output, current_stage_dir)
            
            strategy_info = {
                'strategy': 'use_previous_stage',
                'primary_source': str(prev_main_output),
                'primary_source_relative': relative_path,
                'fallback_source': 'data.csv',
                'has_previous_stage': True,
                'has_previous_summary': has_prev_summary,
                'previous_summary_path': str(prev_summary) if has_prev_summary else None,
                'previous_section': prev_section,
                'reading_code': self._generate_data_reading_code(relative_path, has_prev_summary, prev_summary, current_stage_dir)
            }
        else:
            strategy_info = {
                'strategy': 'fallback_to_original',
                'primary_source': self.workspace_root / 'data.csv',
                'primary_source_relative': 'data.csv',
                'has_previous_stage': True,
                'has_previous_summary': False,
                'previous_section': prev_section,
                'reading_code': 'data <- read.csv("data.csv", stringsAsFactors = FALSE)'
            }
        
        return strategy_info
    
    def _generate_data_reading_code(self, data_path: str, has_summary: bool, 
                                  summary_path: Path, current_dir: Path) -> str:
        """Generate simplified data reading R code (using template)"""
        font_setup = RCodeTemplates.font_setup_template()
        
        summary_relative = None
        if has_summary:
            summary_relative = os.path.relpath(summary_path, current_dir)
 
        data_reading = RCodeTemplates.data_reading_template(
            data_path=data_path,
            has_summary=has_summary,
            summary_path=summary_relative
        )

        return font_setup + "\n" + data_reading
    
    def generate_output_code(self, section: str) -> str:
        """Generate standardized output saving R code (using template)"""
        return RCodeTemplates.output_template(section)
    
    def get_r_script_path(self, section: str, stage_name: str) -> str:
        """Get the save path for R script"""
        filename = f"{section}_{stage_name}.R"
        return str(self.r_scripts_dir / filename)
    
    def prepare_stage_environment(self, section: str) -> Dict[str, str]:
        """
        Prepare execution environment for the specified stage
        
        Args:
            section: Stage number
            
        Returns:
            Environment preparation information
        """
        stage_paths = self.get_stage_paths(section)
        stage_dir = Path(stage_paths['stage_output_dir'])

        original_data = self.upload_dir / 'data.csv' 
        if not original_data.exists():
            original_data = self.workspace_root / 'data.csv'

        return {
            'stage_dir': str(stage_dir),
            'data_strategy': self.get_data_reading_strategy(section),
            'stage_paths': stage_paths
        }
    
    def get_upload_path(self, filename: str) -> Path:
        """Get the save path for uploaded file"""
        return self.upload_dir / filename
    
    def get_report_path(self, filename: str) -> Path:
        """Get the save path for report"""
        return self.report_dir / filename
    
    def get_session_summary(self) -> Dict:
        """Get workspace summary information"""
        return {
            'session_dir': str(self.session_dir),
            'upload_dir': str(self.upload_dir),
            'code_dir': str(self.r_scripts_dir),
            'results_dir': str(self.output_root),
            'report_dir': str(self.report_dir)
        }
    
    def get_global_decisions_path(self) -> str:
        """Get global decision file path"""
        return str(self.global_decisions_dir / 'statistical_decisions.json')

    def generate_enhanced_prompt_info(self, section: str) -> str:
        """Generate simplified prompt information (optimized version: using template references instead of full code)"""
        data_strategy = self.get_data_reading_strategy(section)
        stage_paths = self.get_stage_paths(section)

        prompt_info = f"""
**Working Directory Management (Important):**
- Python has set the working directory to: `{stage_paths['stage_output_dir']}`
- **You are currently in this directory**, no need to create subdirectories or change directory
- Correct approach: Write files directly, e.g. `write.csv(data, "main_output.csv")`
- Prohibited operations: `setwd("output/...")` or `dir.create("output")`

**Data Reading:**
- Data reading strategy: {data_strategy['strategy']}
- Primary data source: {data_strategy['primary_source_relative']}

{RCodeTemplates.get_all_templates_reference()}
"""
        return prompt_info
    
    def get_data_path(self, section: str) -> str:
        """Get data file path for the specified stage"""
        try:
            import re
            num_match = re.search(r'(\d+\.\d+)', section)
            if num_match:
                current_num = float(num_match.group(1))
            else:
                current_num = float(section)
            
            if current_num <= 7.1:
                return "data.csv"
            else:
                prev_num = current_num - 0.1
                prev_section = f"{prev_num:.1f}"
                return f"../{prev_section}/main_output.csv"
        except:
            return "data.csv"
    

