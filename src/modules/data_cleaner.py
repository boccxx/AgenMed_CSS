#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data cleaner module
Function: Move sensitive data files from 03_results to _private
Execution time: Automatically executed after all analysis stages are successful
"""

import shutil
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict
import logging
import fnmatch


class DataCleaner:
    """Data cleaner - move sensitive data to secure storage area"""
    
    def __init__(self, results_dir: str, private_dir: str = None):
        """
        Initialize the cleaner
        
        Args:
            results_dir: Analysis results directory (workspace/analysis_xxx/03_results)
            private_dir: Secure storage directory (default in workspace/analysis_xxx/_private)
        """
        self.results_dir = Path(results_dir)
        if private_dir:
            self.private_dir = Path(private_dir)
        else:
            self.private_dir = self.results_dir.parent / "_private"
        
        self.logger = logging.getLogger(__name__)
        
        # Define sensitive file patterns to move
        self.sensitive_patterns = [
            "data.csv",           # Original data copy
            "processed_data.csv", # Processed data
            "main_output.csv",    # Output with all rows
            "*_imputed*.csv",     # Imputed data
            "data_complete_cases.csv",  # Complete case data
            "*.rds"               # R data object (may contain original data)
        ]
        
        # Security threshold: If the number of rows exceeds this value, it is considered to contain individual data
        self.individual_data_threshold = 100
    
    def is_sensitive_file(self, filepath: Path) -> bool:
        """Check if the file is sensitive (needs to be moved)"""
        filename = filepath.name
        
        for pattern in self.sensitive_patterns:
            if fnmatch.fnmatch(filename, pattern):
                return True
        
        if filepath.suffix == '.csv':
            try:
                file_size = filepath.stat().st_size
                if file_size > 10 * 1024 * 1024:
                    return True
                
                df = pd.read_csv(filepath, nrows=self.individual_data_threshold + 1)
                if len(df) > self.individual_data_threshold:
                    return True
            except Exception as e:
                self.logger.warning(f"    Cannot read {filename}: {e}")
                return True
        
        return False
    
    def move_file(self, source: Path, stage_name: str) -> bool:
        """
        Move a single file to the private area
        
        Args:
            source: Source file path
            stage_name: Stage name (e.g. "7.1")
            
        Returns:
            Whether successful
        """
        try:
            # Check file size and log for large files
            file_size = source.stat().st_size if source.exists() else 0
            file_size_mb = file_size / (1024 * 1024)
            if file_size_mb > 10:
                self.logger.info(f"    Moving large file ({file_size_mb:.1f} MB), this may take a moment...")
            
            target_dir = self.private_dir / stage_name
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / source.name

            # For very large files (>100MB), use copy+delete instead of move for better error handling
            if file_size_mb > 100:
                self.logger.info(f"    Copying large file ({file_size_mb:.1f} MB)...")
                shutil.copy2(str(source), str(target))
                source.unlink()
                self.logger.info(f"    Large file moved successfully")
            else:
                shutil.move(str(source), str(target))
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to move {source}: {e}")
            return False
    
    def cleanup(self, verify: bool = True, dry_run: bool = False) -> Dict:
        """
        Execute data cleanup (workspace version)
        
        Logic:
        1. Scan all 7.X directories under 03_results
        2. Identify sensitive files (data.csv, processed_data.csv, main_output.csv, etc.)
        3. Move sensitive files to _private/7.X/
        4. Keep safe files (aggregate tables, figures) in 03_results for report generation
        
        Args:
            verify: Whether to verify file security
            dry_run: Whether to only simulate running
            
        Returns:
            Cleanup result statistics
        """
        self.logger.info("=" * 60)
        self.logger.info("Starting data cleanup process...")
        self.logger.info(f"Results directory: {self.results_dir}")
        self.logger.info(f"Private directory: {self.private_dir}")
        self.logger.info("=" * 60)
        
        results = {
            'moved': [],
            'kept_safe': [],
            'skipped': [],
            'failed': [],
            'errors': []
        }
        
        if not self.results_dir.exists():
            self.logger.error(f"Results directory does not exist: {self.results_dir}")
            return results
        
        try:
            stage_dirs = []
            for item in self.results_dir.iterdir():
                try:
                    if item.is_dir() and item.name.startswith('7.'):
                        stage_dirs.append(item)
                except (OSError, PermissionError) as e:
                    self.logger.warning(f"Cannot access {item}: {e}")
                    results['errors'].append(f"Cannot access {item.name}: {str(e)}")
                    continue
            
            stage_dirs.sort(key=lambda x: x.name)
            self.logger.info(f"Found {len(stage_dirs)} stage directories to process")
        except Exception as e:
            self.logger.error(f"Failed to scan stage directories: {e}", exc_info=True)
            results['errors'].append(f"Directory scan failed: {str(e)}")
            return results
        
        if not stage_dirs:
            self.logger.warning("No 7.X stage directories found")
            return results
        
        for idx, stage_dir in enumerate(stage_dirs, 1):
            try:
                if not stage_dir.is_dir():
                    self.logger.warning(f"  {stage_dir} is not a directory, skipping")
                    continue
                
                stage_name = stage_dir.name
                self.logger.info(f"\nProcessing stage {idx}/{len(stage_dirs)}: {stage_name}")
                
                try:
                    all_files = [f for f in stage_dir.iterdir() if f.is_file()]
                except (OSError, PermissionError) as e:
                    self.logger.error(f"  Cannot access files in {stage_name}: {e}")
                    results['errors'].append(f"{stage_name}: {str(e)}")
                    continue
                
                self.logger.info(f"  Found {len(all_files)} files in {stage_name}")
                
                if not all_files:
                    self.logger.info(f"  Stage {stage_name} has no files, skipping")
                    continue
            
                for file_idx, filepath in enumerate(all_files, 1):
                    try:
                        if not filepath.is_file():
                            continue
                        
                        filename = filepath.name
                        self.logger.info(f"  Processing file {file_idx}/{len(all_files)}: {filename}")
                        
                        try:
                            is_sensitive = self.is_sensitive_file(filepath)
                        except Exception as e:
                            self.logger.warning(f"  Cannot check sensitivity of {filename}: {e}, treating as safe")
                            is_sensitive = False
                        
                        if is_sensitive:
                            self.logger.info(f"  Sensitive file: {filename}")
                            
                            if dry_run:
                                results['moved'].append(f"{stage_name}/{filename} (dry-run)")
                            else:
                                try:
                                    if self.move_file(filepath, stage_name):
                                        results['moved'].append(f"{stage_name}/{filename}")
                                        self.logger.info(f"    Moved")
                                    else:
                                        results['failed'].append(f"{stage_name}/{filename}")
                                        self.logger.error(f"    Failed to move")
                                except Exception as e:
                                    results['failed'].append(f"{stage_name}/{filename}")
                                    self.logger.error(f"    Error moving file: {e}", exc_info=True)
                        else:
                            self.logger.info(f"  Safe file: {filename} (retained)")
                            results['kept_safe'].append(f"{stage_name}/{filename}")
                    except Exception as e:
                        self.logger.error(f"  Error processing file {filepath}: {e}", exc_info=True)
                        results['errors'].append(f"{stage_name}/{filepath.name}: {str(e)}")
                
                self.logger.info(f"  Completed processing stage {stage_name}")
            except Exception as e:
                self.logger.error(f"Error processing stage {stage_dir}: {e}", exc_info=True)
                results['errors'].append(f"{stage_dir.name}: {str(e)}")
                continue

        if not dry_run:
            try:
                self.logger.info("Writing cleanup record...")
                self._write_cleanup_record(results)
                self.logger.info("Cleanup record written successfully")
            except Exception as e:
                self.logger.error(f"Failed to write cleanup record: {e}", exc_info=True)

        try:
            self.logger.info("Printing cleanup summary...")
            self._print_summary(results, dry_run)
            self.logger.info("Cleanup summary printed")
        except Exception as e:
            self.logger.error(f"Failed to print cleanup summary: {e}", exc_info=True)
        
        self.logger.info("Data cleanup process completed, returning results")
        return results
    
    def _write_cleanup_record(self, results: Dict):
        """Write cleanup record to JSON file"""
        try:
            record_file = self.private_dir / "cleanup_record.json"
            self.logger.info(f"Preparing to write cleanup record to: {record_file}")
            self.private_dir.mkdir(parents=True, exist_ok=True)
            
            import json
            record = {
                'timestamp': datetime.now().isoformat(),
                'results_dir': str(self.results_dir),
                'private_dir': str(self.private_dir),
                'moved_count': len(results['moved']),
                'kept_safe_count': len(results['kept_safe']),
                'failed_count': len(results['failed']),
                'moved_files': results['moved'],
                'kept_files': results['kept_safe'],
                'failed_files': results['failed']
            }
            
            self.logger.info(f"Writing cleanup record (moved: {len(results['moved'])}, kept: {len(results['kept_safe'])}, failed: {len(results['failed'])})...")
            with open(record_file, 'w', encoding='utf-8') as f:
                json.dump(record, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Cleanup record saved successfully: {record_file}")
        except Exception as e:
            self.logger.error(f"Failed to write cleanup record: {e}", exc_info=True)
    
    def _print_summary(self, results: Dict, dry_run: bool):
        """Print cleanup summary"""
        mode_text = "(模拟运行)" if dry_run else ""
        
        print("\n" + "=" * 60)
        print(f"Data cleanup completed {mode_text}")
        print("=" * 60)
        print(f"Moved sensitive files: {len(results['moved'])} files")
        print(f"Kept safe files: {len(results['kept_safe'])} files")
        print(f"Skipped files: {len(results['skipped'])} files")
        print(f"Failed files: {len(results['failed'])} files")
        
        if results['moved']:
            print(f"\nMoved to {self.private_dir}:")
            for item in results['moved'][:10]: 
                print(f"  - {item}")
            if len(results['moved']) > 10:
                print(f"  ... 还有 {len(results['moved']) - 10} 个")
        
        if results['failed']:
            print("\n Failed to move:")
            for item in results['failed']:
                print(f"  - {item}")
        
        print("=" * 60)
    
    def restore_file(self, stage: str, filename: str) -> bool:
        """
        Restore file from private area (for testing or re-analysis)
        
        Args:
            stage: Stage name (e.g. "7.1")
            filename: File name
            
        Returns:
            Whether successful
        """
        try:
            source = self.private_dir / stage / filename
            target_dir = self.results_dir / stage
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / filename
            
            if not source.exists():
                self.logger.error(f"Source file does not exist: {source}")
                return False
            
            shutil.copy2(str(source), str(target))
            self.logger.info(f"Restored successfully: {filename} → {target}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to restore: {e}")
            return False


def cleanup_workspace_data(workspace_dir: str, dry_run: bool = False) -> bool:
    """
    Clean sensitive data in workspace (convenience function)
    
    Args:
        workspace_dir: workspace directory path (workspace/analysis_xxx/)
        dry_run: Whether to only simulate running
        
    Returns:
        Whether successful
    """
    workspace_path = Path(workspace_dir)
    results_dir = workspace_path / "03_results"
    
    if not results_dir.exists():
        print(f"Results directory does not exist: {results_dir}")
        return False
    
    cleaner = DataCleaner(str(results_dir))
    results = cleaner.cleanup(dry_run=dry_run)

    return len(results['failed']) == 0


def main():
    """Command line entry"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Clean sensitive data in workspace")
    parser.add_argument("workspace_dir", help="workspace directory path")
    parser.add_argument("--dry-run", action="store_true", help="Only simulate running, do not actually move files")
    parser.add_argument("--verbose", action="store_true", help="Show detailed logs")
    
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    success = cleanup_workspace_data(args.workspace_dir, dry_run=args.dry_run)
    
    if success:
        print("\nData cleanup completed")
        return 0
    else:
        print("\nData cleanup failed")
        return 1


if __name__ == "__main__":
    exit(main())
