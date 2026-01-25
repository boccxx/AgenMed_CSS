#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM-driven Statistical Analysis Report Generator
Function: Read research protocol and all analysis results, automatically generate Word format statistical analysis report
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime

import pandas as pd
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

try:
    from .llm_client import LLMClient
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from modules.llm_client import LLMClient


class ReportGenerator:
    """LLM-driven Report Generator (General Version)"""
    
    def __init__(self, protocol_path: str, results_dir: str, config: Dict = None):
        """
        Initialize report generator
        
        Args:
            protocol_path: Research protocol path
            results_dir: Analysis results directory (workspace/analysis_xxx/03_results)
            config: System configuration
        """
        self.protocol_path = Path(protocol_path)
        self.results_dir = Path(results_dir)
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
        # Sensitive file patterns (should not be accessed during report generation)
        self.sensitive_patterns = [
            "data.csv", "processed_data.csv", "main_output.csv",
            "*_imputed*.csv", "data_complete_cases.csv", "*.rds"
        ]
        
        self.llm_client = LLMClient(self.config)
        
        self.protocol_summary = self._load_protocol_summary()
        
        self.report_sections = self._discover_analysis_stages()
        
        self.report_contract = self._load_report_contract()
        
    def _load_protocol_summary(self) -> str:
        """Read research protocol summary (first 3000 characters)"""
        try:
            if self.protocol_path.suffix.lower() == '.docx':
                from docx import Document
                doc = Document(str(self.protocol_path))
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                content = '\n'.join(paragraphs)
                summary = content[:3000]
                return summary
            else:
                with open(self.protocol_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.split('\n')
                    title_lines = [line for line in lines[:20] if line.strip()]
                    summary = '\n'.join(title_lines[:5]) + '\n\n' + content[:3000]
                    return summary
        except Exception as e:
            self.logger.warning(f"Unable to read research protocol: {e}")
            return "Research protocol summary not provided"
    
    def _load_report_contract(self) -> Dict:
        """Load report contract (single source of truth)"""
        contract_path = self.results_dir / "report_contract.json"
        if contract_path.exists():
            try:
                with open(contract_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"Failed to load report contract: {e}")
        
        return {
            "inference_level": "unknown",
            "weight_var_name": None,
            "weight_status": "missing",
            "n_total": None,
            "missing_data_method": "unknown",
            "exposure_definition": None,
            "outcome_definition": None
        }
    
    def _discover_analysis_stages(self) -> List[Dict]:
        """
        Automatically discover all analysis stages
        
        Returns:
            Section list, extracted from analysis_summary.json
        """
        self.logger.info("Automatically discovering analysis stages...")
        
        sections = []
        
        stage_dirs = sorted(self.results_dir.glob("7.*"), key=lambda x: x.name)
        
        for stage_dir in stage_dirs:
            if not stage_dir.is_dir():
                continue
            
            stage = stage_dir.name
            summary_file = stage_dir / "analysis_summary.json"
            
            section_name = None
            method_name = None
            
            if summary_file.exists():
                try:
                    with open(summary_file, 'r', encoding='utf-8') as f:
                        summary_data = json.load(f)
                    
                    method_name = summary_data.get('method', '')
                    
                    section_name = self._infer_section_name(method_name, stage)
                    
                except Exception as e:
                    self.logger.warning(f"Unable to read {summary_file}: {e}")
            
            if not section_name:
                section_name = f"Stage {stage}"
            
            sections.append({
                "id": stage.replace(".", "_"),
                "name": section_name,
                "stage": stage,
                "method": method_name
            })
        
        self.logger.info(f"Discovered {len(sections)} analysis stages")
        
        return sections
    
    def _infer_section_name(self, method_name: str, stage: str) -> str:
        """
        Infer section name from method name (general mapping)
        
        Args:
            method_name: Analysis method name (e.g., "descriptive_analysis")
            stage: Stage number (e.g., "7.4")
            
        Returns:
            Section name
        """
        method_mapping = {
            "overview": "Data Overview",
            "data_overview": "Data Overview",
            "unknown_stage": "Unknown Stage Processing",
            "missing": "Missing Data Analysis",
            "missing_data": "Missing Data Analysis",
            "descriptive": "Descriptive Statistics",
            "descriptive_analysis": "Descriptive Statistics",
            "association": "Association Analysis",
            "association_analysis": "Association Analysis",
            "advanced": "Advanced Analysis",
            "advanced_analysis": "Advanced Analysis",
            "results": "Results Presentation",
            "results_presentation": "Results Presentation and Summary",
        }
        
        for key, name in method_mapping.items():
            if key in method_name.lower():
                return name
        
        return f"Analysis Stage {stage}"
    
    def scan_available_files(self) -> Dict[str, List[Dict]]:
        """
        Scan all available result files (general method)
        
        Returns:
            Dictionary containing tables, images, and summaries
        """
        self.logger.info("Scanning available result files...")
        
        available_files = {
            "tables": [],
            "images": [],
            "summaries": []
        }
        
        for stage_dir in self.results_dir.glob("7.*"):
            if not stage_dir.is_dir():
                continue
            
            stage = stage_dir.name
            
            for csv_file in stage_dir.glob("*.csv"):
                if csv_file.name in [
                    "main_output.csv",      
                    "processed_data.csv",   
                    "data.csv",             
                    "data_complete_cases.csv",  
                    "imputed_data.csv"      
                ]:
                    continue
                
                description = self._infer_file_description(csv_file.name)
                
                available_files["tables"].append({
                    "path": str(csv_file),
                    "name": csv_file.name,
                    "stage": stage,
                    "description": description
                })
            
            for png_file in stage_dir.glob("*.png"):
                description = self._infer_file_description(png_file.name)
                
                available_files["images"].append({
                    "path": str(png_file),
                    "name": png_file.name,
                    "stage": stage,
                    "description": description
                })
            
            summary_file = stage_dir / "analysis_summary.json"
            if summary_file.exists():
                try:
                    with open(summary_file, 'r', encoding='utf-8') as f:
                        summary_data = json.load(f)
                    
                    available_files["summaries"].append({
                        "path": str(summary_file),
                        "stage": stage,
                        "data": summary_data
                    })
                except Exception as e:
                    self.logger.warning(f"Unable to read {summary_file}: {e}")
        
        self.logger.info(f"Found {len(available_files['tables'])} tables, "
                        f"{len(available_files['images'])} images, "
                        f"{len(available_files['summaries'])} summaries")
        
        return available_files
    
    def _infer_file_description(self, filename: str) -> str:
        """
        Automatically infer description from filename (general method)
        
        Args:
            filename: File name
            
        Returns:
            File description
        """
        name = Path(filename).stem.lower()
        
        keyword_mapping = {
            "table1": "Baseline Characteristics Table",
            "table_1": "Baseline Characteristics Table",
            "baseline": "Baseline Characteristics",
            "overall": "Overall",
            "by_": "Stratified",
            "stratified": "Stratified",
            "corr": "Correlation",
            "correlation": "Correlation",
            "heatmap": "Heatmap",
            "missing": "Missing Data",
            "pattern": "Pattern",
            "forest": "Forest Plot",
            "flow": "Flow Chart",
            "strobe": "STROBE",
            "final": "Final",
            "main": "Main",
            "results": "Results",
            "summary": "Summary",
            "descriptive": "Descriptive Statistics",
        }
        
        description_parts = []
        
        for keyword, meaning in keyword_mapping.items():
            if keyword in name:
                description_parts.append(meaning)
        
        if description_parts:
            return " ".join(description_parts)
        else:
            return filename.replace("_", " ").replace("-", " ").title()
    
    def extract_evidence(self, csv_path: str, table_description: str) -> Dict:
        try:
            df = pd.read_csv(csv_path)
            evidence = {
                "table_name": Path(csv_path).name,
                "description": table_description,
                "n_rows": len(df),
                "columns": list(df.columns),
                "key_numbers": {}
            }
            
            numeric_cols = df.select_dtypes(include=[float, int]).columns
            for col in numeric_cols:
                if any(kw in col.lower() for kw in ['n', 'count', 'sample', 'size']):
                    evidence["key_numbers"][f"{col}_values"] = df[col].dropna().tolist()[:20]
                elif any(kw in col.lower() for kw in ['pr', 'or', 'rr', 'hr', 'estimate', 'coefficient', 'beta']):
                    evidence["key_numbers"][f"{col}_values"] = df[col].dropna().tolist()[:20]
                elif any(kw in col.lower() for kw in ['ci', 'lower', 'upper', '95']):
                    evidence["key_numbers"][f"{col}_values"] = df[col].dropna().tolist()[:20]
                elif any(kw in col.lower() for kw in ['p', 'p_value', 'pvalue']):
                    evidence["key_numbers"][f"{col}_values"] = df[col].dropna().tolist()[:20]
                elif any(kw in col.lower() for kw in ['rate', 'prevalence', 'proportion', 'percent', '%']):
                    evidence["key_numbers"][f"{col}_values"] = df[col].dropna().tolist()[:20]
            
            if len(df) <= 20:
                evidence["full_data"] = df.to_dict('records')
            else:
                evidence["sample_data"] = df.head(10).to_dict('records')
            
            return evidence
        except Exception as e:
            self.logger.error(f"Evidence extraction failed {csv_path}: {e}")
            return {
                "table_name": Path(csv_path).name,
                "description": table_description,
                "error": str(e)
            }
    
    def interpret_image(self, image_path: str, image_description: str) -> str:
        """
        Use LLM to interpret image (based on filename inference, general method)
        
        Args:
            image_path: Image file path
            image_description: Image description
            
        Returns:
            Image interpretation text
        """
        self.logger.info(f"[PROGRESS] Building prompt for image: {Path(image_path).name}")
        
        prompt = f"""
You are a statistical expert, please infer what this image might display based on the image filename.

Image filename: {Path(image_path).name}
Image description: {image_description}

Please explain in 1-2 sentences:
1. What type of statistical results this image typically displays
2. How readers should interpret this image

Note: Only output the explanation text, no additional content.
"""
        
        self.logger.info(f"[PROGRESS] Prompt built for image, length: {len(prompt)} characters")
        import sys
        sys.stdout.flush()
        
        try:
            self.logger.info(f"[PROGRESS] Calling LLM for image: {Path(image_path).name}")
            response = self.llm_client.call(
                messages=[{"role": "user", "content": prompt}]
            )
            
            self.logger.info(f"[PROGRESS] LLM response received for image {Path(image_path).name}, type: {type(response)}")
            
            if response is None:
                self.logger.error(f"LLM returned None for image {image_path}")
                return f"This image displays the visualization results of {image_description}."
            
            interpretation = str(response).strip()
            self.logger.info(f"Image interpretation completed: {image_path}, length: {len(interpretation)}")
            
            import sys
            sys.stdout.flush()
            
            return interpretation
        except Exception as e:
            self.logger.error(f"Image interpretation failed {image_path}: {e}", exc_info=True)
            return f"This image displays the visualization results of {image_description}."
    
    def build_section_prompt(self, section_name: str, section_stage: str, 
                            available_files: Dict, previous_context: str = "") -> str:
        """
        Build prompt for generating section (general method)
        
        Args:
            section_name: Section name
            section_stage: Corresponding analysis stage
            available_files: Available file list
            previous_context: Last part of previous section (for continuity)
            
        Returns:
            Built prompt
        """
        self.logger.info(f"[PROGRESS] Building prompt for {section_name} (stage {section_stage})...")
        
        stage_tables = [f for f in available_files['tables'] if f['stage'] == section_stage]
        stage_images = [f for f in available_files['images'] if f['stage'] == section_stage]
        stage_summary = next((s for s in available_files['summaries'] if s['stage'] == section_stage), None)
        
        previous_stage_summaries = []
        stage_num = float(section_stage) if section_stage.replace('.', '').isdigit() else 0
        for summary in available_files['summaries']:
            try:
                prev_stage_num = float(summary['stage']) if summary['stage'].replace('.', '').isdigit() else 0
                if prev_stage_num < stage_num and prev_stage_num > 0:
                    previous_stage_summaries.append({
                        'stage': summary['stage'],
                        'design': summary['data'].get('design', {}),
                        'weight_detection': summary['data'].get('weight_detection', {}),
                        'critical_decisions': summary['data'].get('critical_decisions', {})
                    })
            except:
                pass
        
        previous_stage_summaries.sort(key=lambda x: float(x['stage']) if x['stage'].replace('.', '').isdigit() else 0)
        
        self.logger.info(f"[PROGRESS] Found {len(stage_tables)} tables, {len(stage_images)} images for stage {section_stage}")
        
        priority_keywords = ['model', 'regression', 'main', 'final', 'weights', 'summary', 'results']
        priority_tables = [t for t in stage_tables if any(kw in t['name'].lower() for kw in priority_keywords)]
        other_tables = [t for t in stage_tables if t not in priority_tables]
        stage_tables_sorted = priority_tables + other_tables[:10]
        
        tables_list = "\n".join([f"- {t['description']} ({t['name']}): path={t['path']}" for t in stage_tables_sorted])
        images_list = "\n".join([f"- {i['description']} ({i['name']}): path={i['path']}" for i in stage_images])
        
        evidence_pack = []
        for table in stage_tables_sorted:
            try:
                evidence = self.extract_evidence(table['path'], table['description'])
                evidence_pack.append(evidence)
            except Exception as e:
                self.logger.error(f"Evidence extraction failed for {table['name']}: {e}")
        
        image_interpretations = []
        for idx, image in enumerate(stage_images, 1):
            try:
                interpretation = self.interpret_image(image['path'], image['description'])
                image_interpretations.append(f"**{image['description']}** ({image['name']})\n{interpretation}")
            except Exception as e:
                self.logger.error(f"Image interpretation failed for {image['name']}: {e}")
                image_interpretations.append(f"**{image['description']}** ({image['name']})\nThis image displays the visualization results of {image['description']}.")
        
        contract_text = json.dumps(self.report_contract, ensure_ascii=False, indent=2)
        inference_level = self.report_contract.get('inference_level', 'unknown')
        weight_status = self.report_contract.get('weight_status', 'missing')
        
        stage_design_info = None
        if stage_summary and 'data' in stage_summary:
            stage_design_info = stage_summary['data'].get('design', {})
        
        stage_inference_level = stage_design_info.get('design_verified_level', inference_level) if stage_design_info else inference_level
        stage_weights_used = stage_design_info.get('weights_actually_used', None) if stage_design_info else None
        
        structure_bullets = []
        if previous_context:
            lines = previous_context.split('\n')
            headings = [l for l in lines if l.startswith('##')]
            if headings:
                structure_bullets = headings[-3:]
        
        self.logger.info(f"[PROGRESS] Prompt building: contract loaded, {len(evidence_pack)} evidence items")
        
        weight_description_rule = ""
        if stage_weights_used is not None:
            if stage_weights_used and stage_inference_level == "design_based":
                weight_description_rule = f"""
**WEIGHT USAGE FOR THIS STAGE (MANDATORY):**
- This stage's analysis_summary.json shows: weights_actually_used=true, design_verified_level="design_based"
- You MUST write: "weighted analysis" or "applied sampling weights" or "design-based analysis"
- You MUST NOT write "unweighted" or "sample-based" for this stage
"""
            elif not stage_weights_used or stage_inference_level == "sample_based":
                weight_description_rule = f"""
**WEIGHT USAGE FOR THIS STAGE (MANDATORY):**
- This stage's analysis_summary.json shows: weights_actually_used=false OR design_verified_level="sample_based"
- You MUST write: "unweighted analysis" or "sample-based inference"
- You MUST NOT write "weighted" or "applied sampling weights" for this stage
"""
        else:
            if inference_level == "design_based" and weight_status == "valid":
                weight_description_rule = f"""
**WEIGHT USAGE FOR THIS STAGE (MANDATORY):**
- Report contract shows: inference_level="design_based", weight_status="valid"
- You MUST write: "weighted analysis" or "applied sampling weights" or "design-based analysis"
- You MUST NOT write "unweighted" or "sample-based" for this stage
"""
            else:
                weight_description_rule = f"""
**WEIGHT USAGE FOR THIS STAGE (MANDATORY):**
- Report contract shows: inference_level="sample_based" OR weight_status="placeholder"
- You MUST write: "unweighted analysis" or "sample-based inference"
- You MUST NOT write "weighted" or "applied sampling weights" for this stage
"""
        
        prompt = f"""
You are a senior statistician writing a professional statistical analysis report.

**CRITICAL: REPORT COMPLIANCE RULES (MANDATORY)**

**REPORT CONTRACT (SINGLE SOURCE OF TRUTH - MUST NOT CONTRADICT):**
{contract_text}

**INFERENCE LEVEL CONSTRAINT:**
- If inference_level = "design_based" AND weight_status = "valid": You may use "design-based / weighted estimation / population-level inference"
- If inference_level = "sample_based" OR weight_status = "placeholder" OR weight_status = "missing": 
  * MUST write "exploratory, unweighted, sample-based inference"
  * MUST NOT use "representative", "generalizable", "population-level"
  * If mentioning region/institution controls: phrase as "to partially mitigate selection-related differences"

{weight_description_rule}

**EVIDENCE-BASED WRITING:**
- You MUST cite specific numbers from evidence_pack below, with source file name in parentheses
- Example: "The prevalence was 45.2% (table1_baseline_characteristics.csv)"
- Do NOT fabricate numbers not in evidence_pack

# Research Background
{self.protocol_summary[:1000]}

# Structure Continuity
{chr(10).join(structure_bullets) if structure_bullets else "(This is the first section)"}

---

# Current Task
Please write the **"{section_name}"** section of the report (corresponding to analysis stage {section_stage}).

# Available result files for this section

## Table Files
{tables_list if tables_list else "(No table files in this stage)"}

## Evidence Pack (Structured Key Numbers - MUST cite with source)
{json.dumps(evidence_pack, ensure_ascii=False, indent=2) if evidence_pack else "(No evidence extracted)"}

## Image Files
{images_list if images_list else "(No image files in this stage)"}

### Image Content Description
{chr(10).join(image_interpretations) if image_interpretations else "(No images to describe)"}

## Analysis Summary (from system - Current Stage)
{json.dumps(stage_summary['data'], ensure_ascii=False, indent=2) if stage_summary else "(No analysis summary for this stage)"}

## Previous Stage Summaries (for context - especially design information)
{json.dumps(previous_stage_summaries, ensure_ascii=False, indent=2) if previous_stage_summaries else "(No previous stage summaries)"}

**IMPORTANT**: If previous stages contain design information (strata_variable, psu_variable, weight_variable), you MUST use that information and NOT contradict it. The earliest stage (usually 7.1) contains the authoritative design information.

**DEVIATION REGISTER REQUIREMENT (MANDATORY for multivariable modeling sections):**
- If the current stage's analysis_summary.json contains "protocol_deviations" field with non-empty list:
  - You MUST include a "### Deviation Register" subsection in your report
  - For each deviation, clearly state:
    * Which protocol-specified variable was missing/unavailable
    * Reason for unavailability (e.g., "not collected in data", "implementation deviation")
    * What substitute variable/proxy was used (if any)
    * Impact on main conclusion direction and interpretation
  - Example format: "The protocol specified adjustment for Education, but this variable was not collected in the dataset. We used Self_Rated_Health as a proxy indicator of socioeconomic status. This may underestimate confounding by education level, potentially biasing effect estimates toward the null."
- If protocol_deviations is empty or absent: No deviation register subsection needed

---

# Writing Requirements

1. **Content Requirements**:
   - Describe the analysis process and findings in academic but understandable language
   - Cite specific numbers from evidence_pack with source file name: "value (filename.csv)"
   - If the analysis summary contains statistical method descriptions, explain the reason for method selection
   - Summarize 2-3 key findings

2. **Figure and Table Insertion**:
   - Reference images: `[Image: image_path]`
   - Reference tables: `[Table: table_path]`
   - Must have text explanation before and after references

3. **Format Requirements**:
   - Use level-2 headings `## Subsection Name`
   - Use level-3 headings `### Smaller Subsection`
   - Word count: 600-1000 words
   - All numbers must be from evidence_pack with source citation

4. **Things to Avoid**:
   - Do not fabricate numbers not in evidence_pack
   - Do not reference files not in the above list
   - Do not contradict report_contract

# Output Format
Directly output section content, do not include any extra explanation. Start with `## {section_name}`.

Please begin:
"""
        
        self.logger.info(f"[PROGRESS] Final prompt built, length: {len(prompt)} characters")
        import sys
        sys.stdout.flush()
        
        return prompt
    
    def generate_section(self, section_name: str, section_stage: str, 
                        available_files: Dict, previous_context: str = "") -> str:
        """
        Generate single section content
        
        Args:
            section_name: Section name
            section_stage: Corresponding analysis stage
            available_files: Available file list
            previous_context: Previous section content
            
        Returns:
            Generated section content (Markdown format)
        """
        self.logger.info(f"Generating section: {section_name} (stage {section_stage})")
        
        try:
            self.logger.info(f"[PROGRESS] Building prompt for section {section_name}...")
            prompt = self.build_section_prompt(
                section_name, section_stage, available_files, previous_context
            )
            
            prompt_length = len(prompt)
            self.logger.info(f"[PROGRESS] Prompt built, length: {prompt_length} characters")
            
            if prompt_length > 50000:
                self.logger.warning(f"[WARNING] Prompt is very long ({prompt_length} chars), may cause timeout or token limit issues")
            
            self.logger.info(f"[PROGRESS] Calling LLM for section {section_name}...")
            
            response = self.llm_client.call(
                messages=[{"role": "user", "content": prompt}],
                max_retries=5
            )
            
            self.logger.info(f"[DEBUG] LLM response received for {section_name}, type: {type(response)}")
            
            # Ensure response is string
            if response is None:
                raise ValueError("LLM returned None response")
            
            section_content = str(response).strip()
            
            self.logger.info(f"Section generation successful: {section_name}, length: {len(section_content)}")
            
            return section_content
            
        except Exception as e:
            self.logger.error(f"Section generation failed {section_name}: {e}", exc_info=True)
            return f"""## {section_name}

This section analyzed the results of stage {section_stage}. Due to problems in the generation process, please refer to the original analysis result files.

Analysis stage: {section_stage}
"""
    
    def generate_cover(self) -> str:
        contract_text = json.dumps(self.report_contract, ensure_ascii=False, indent=2)
        inference_level = self.report_contract.get('inference_level', 'unknown')
        weight_status = self.report_contract.get('weight_status', 'missing')
        
        prompt = f"""
You are a professional statistician, please write the report cover and executive summary for the following study.

**CRITICAL: REPORT COMPLIANCE RULES (MANDATORY)**

**REPORT CONTRACT (SINGLE SOURCE OF TRUTH - MUST NOT CONTRADICT):**
{contract_text}

**INFERENCE LEVEL CONSTRAINT:**
- If inference_level = "design_based" AND weight_status = "valid": You may use "design-based / weighted estimation / population-level inference"
- If inference_level = "sample_based" OR weight_status = "placeholder" OR weight_status = "missing": 
  * MUST write "exploratory, unweighted, sample-based inference"
  * MUST NOT use "representative", "generalizable", "population-level"

# Research Protocol Summary
{self.protocol_summary[:2000]}

# Task
Generate the cover page and executive summary of the report, including:
1. Study title (extracted from protocol)
2. Study type (e.g., cross-sectional study, cohort study, etc., inferred from protocol content)
3. Executive summary (200-300 words), including:
   - Study purpose
   - Main methods (MUST be consistent with report_contract inference_level and weight_status)
   - Expected analysis content

# Output Format
Directly output content using Markdown format:
- Use `# ` for level-1 heading (study title)
- Use `## ` for level-2 headings
- Do not include any extra explanation

Please begin:
"""
        
        try:
            self.logger.info("[PROGRESS] Starting cover generation...")
            response = self.llm_client.call(
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Check if response is None or empty
            if response is None:
                self.logger.error("Cover generation failed: LLM returned None response")
                raise ValueError("LLM returned None response")
            
            if not isinstance(response, str):
                self.logger.warning(f"Cover generation: response type is {type(response)}, converting to string")
                response = str(response)
            
            self.logger.info(f"[PROGRESS] Cover generation completed, length: {len(response)}")
            return response.strip()
        except Exception as e:
            self.logger.error(f"Cover generation failed: {e}", exc_info=True)
            return f"""# Statistical Analysis Report

## Executive Summary
This report is generated based on an automated statistical analysis system and covers complete analysis results from multiple stages.

**Generation Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    def generate_discussion(self, report_parts: List[str]) -> str:
        """
        Generate discussion and conclusion section
        
        Args:
            report_parts: All previously generated sections
            
        Returns:
            Discussion section content
        """

        key_findings = []
        for part in report_parts[1:]: 
            lines = part.split('\n')
            title = next((line for line in lines if line.startswith('##')), '')
            last_lines = '\n'.join(lines[-5:])
            key_findings.append(f"{title}\n{last_lines}")
        
        prompt = f"""
You are a senior statistician, please write the "Discussion" and "Conclusion" sections for the statistical analysis report.

# Key Findings from Previous Text
{chr(10).join(key_findings[:3000])}  # Limit length

# Task
Based on the analysis results from previous text, write:

1. **Discussion** (400-600 words):
   - Integrate main findings from each section
   - Explain the practical significance of results
   - Point out strengths and limitations of this study

2. **Conclusion** (200-300 words):
   - Briefly summarize research findings
   - Propose suggestions for practice

# Output Format
Use Markdown format, starting with `## Discussion` and `## Conclusion`.

Please begin:
"""
        
        try:
            self.logger.info("[PROGRESS] Starting discussion and conclusion generation...")
            response = self.llm_client.call(
                messages=[{"role": "user", "content": prompt}]
            )
            
            self.logger.info(f"[PROGRESS] Discussion generation completed, length: {len(response)}")
            return response.strip()
        except Exception as e:
            self.logger.error(f"Discussion generation failed: {e}", exc_info=True)
            return """## Discussion

This study obtained important findings on research questions through systematic statistical analysis. Detailed analysis results have been presented in previous sections.

## Conclusion

This study provides valuable statistical evidence that can provide reference for subsequent research and practice.
"""
    
    def markdown_to_word(self, markdown_content: str, output_path: str) -> str:
        """
        Convert Markdown content to Word document
        
        Args:
            markdown_content: Markdown format content
            output_path: Output file path
            
        Returns:
            Generated file path
        """
        self.logger.info("Starting to generate Word document...")
        
        doc = Document()
        
        self._set_document_styles(doc)
        
        lines = markdown_content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line or line == '---':
                i += 1
                continue
            
            if line.startswith('# '):
                title = line[2:]
                p = doc.add_heading(title, level=0)
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            elif line.startswith('## '):
                title = line[3:]
                doc.add_heading(title, level=1)
            
            elif line.startswith('### '):
                title = line[4:]
                doc.add_heading(title, level=2)
            
            elif line.startswith('[Image:') or line.startswith('[图片:') or line.startswith('[图片：'):
                image_path = re.search(r'\[(Image|图片)[:：]\s*([^\]]+)\]', line)
                if image_path:
                    img_path = image_path.group(2).strip()
                    self._add_image_to_doc(doc, img_path)
            
            elif line.startswith('[Table:') or line.startswith('[表格:') or line.startswith('[表格：'):
                table_path = re.search(r'\[(Table|表格)[:：]\s*([^\]]+)\]', line)
                if table_path:
                    tbl_path = table_path.group(2).strip()
                    self._add_table_to_doc(doc, tbl_path)
            
            elif line.startswith('- ') or line.startswith('* '):
                content = line[2:]
                doc.add_paragraph(content, style='List Bullet')
            
            elif line.startswith('1. ') or line.startswith('2. '):
                content = line[3:]
                doc.add_paragraph(content, style='List Number')
            
            else:
                if '**' in line:
                    self._add_formatted_paragraph(doc, line)
                else:
                    doc.add_paragraph(line)
            
            i += 1
        
        section = doc.sections[0]
        footer = section.footer
        footer_para = footer.paragraphs[0]
        footer_para.text = f"Report Generation Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        doc.save(output_path)
        self.logger.info(f"Word document saved: {output_path}")
        
        return output_path
    
    def _set_document_styles(self, doc: Document):
        """Set document styles"""
        style = doc.styles['Normal']
        font = style.font
        font.name = 'Times New Roman'
        font.size = Pt(12)
    
    def _add_image_to_doc(self, doc: Document, image_path: str):
        """Add image to document"""
        try:
            img_path = Path(image_path)
            if img_path.exists():
                doc.add_picture(str(img_path), width=Inches(5.5))
                last_paragraph = doc.paragraphs[-1]
                last_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                
                caption = doc.add_paragraph()
                run = caption.add_run(f"Figure: {img_path.name}")
                run.italic = True
                run.font.name = 'Times New Roman'
                run.font.size = Pt(12)
                caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                doc.add_paragraph(f"Image does not exist: {image_path}")
        except Exception as e:
            self.logger.error(f"Image insertion failed {image_path}: {e}")
            doc.add_paragraph(f"Image insertion failed: {image_path}")
    
    def _add_table_to_doc(self, doc: Document, table_path: str):
        """Add table to document"""
        try:
            tbl_path = Path(table_path)
            if tbl_path.exists():
                df = pd.read_csv(tbl_path)

                if len(df) > 20:
                    df = df.head(20)
                    doc.add_paragraph("(Table is too long, only first 20 rows shown)")

                table = doc.add_table(rows=len(df)+1, cols=len(df.columns))
                table.style = 'Light Grid Accent 1'

                for i, col in enumerate(df.columns):
                    cell = table.rows[0].cells[i]
                    cell.text = str(col)
                    run = cell.paragraphs[0].runs[0]
                    run.font.bold = True
                    run.font.name = 'Times New Roman'
                    run.font.size = Pt(12)

                for i, row in df.iterrows():
                    for j, value in enumerate(row):
                        cell = table.rows[i+1].cells[j]
                        cell.text = str(value)

                        if cell.paragraphs[0].runs:
                            cell.paragraphs[0].runs[0].font.name = 'Times New Roman'
                            cell.paragraphs[0].runs[0].font.size = Pt(12)

                caption = doc.add_paragraph()
                run = caption.add_run(f"Table: {tbl_path.name}")
                run.italic = True
                run.font.name = 'Times New Roman'
                run.font.size = Pt(12)
                caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                doc.add_paragraph(f"Table does not exist: {table_path}")
        except Exception as e:
            self.logger.error(f"Table insertion failed {table_path}: {e}")
            doc.add_paragraph(f"Table insertion failed: {table_path}")
    
    def _add_formatted_paragraph(self, doc: Document, text: str):
        """Add formatted paragraph (handle bold text)"""
        para = doc.add_paragraph()
        
        parts = text.split('**')
        for i, part in enumerate(parts):
            if i % 2 == 0:
                para.add_run(part)
            else:
                para.add_run(part).bold = True
    
    def _audit_report(self, markdown_content: str) -> Dict:
        issues = []
        blocking = False
        
        inference_level = self.report_contract.get('inference_level', 'unknown')
        weight_status = self.report_contract.get('weight_status', 'missing')
        
        forbidden_words_design = ['representative', 'generalizable', 'population-level', 'probability sampling inference']
        forbidden_words_sample = ['design-based', 'weighted estimation', 'design-based variance']
        
        if inference_level != 'design_based' or weight_status in ['placeholder', 'missing']:
            for word in forbidden_words_design:
                if word.lower() in markdown_content.lower():
                    issues.append(f"Forbidden word '{word}' used when inference_level={inference_level}, weight_status={weight_status}")
                    blocking = True
        else:
            for word in forbidden_words_sample:
                if word.lower() in markdown_content.lower() and 'sample-based' in markdown_content.lower():
                    issues.append(f"Contradictory language: '{word}' with sample-based inference")
        
        number_pattern = r'\b\d+\.?\d*\b'
        numbers = re.findall(number_pattern, markdown_content)
        
        available_files = self.scan_available_files()
        all_evidence = []
        for table in available_files['tables']:
            try:
                evidence = self.extract_evidence(table['path'], table['description'])
                all_evidence.append(evidence)
            except:
                pass
        
        return {
            'passed': len(issues) == 0,
            'issues': issues,
            'blocking': blocking
        }
    
    def generate_report(self, output_filename: str = "statistical_analysis_report.docx") -> str:
        """
        Main function to generate complete report
        
        Args:
            output_filename: Output filename
            
        Returns:
            Generated report path
        """
        self.logger.info("="*60)
        self.logger.info("Starting to generate statistical analysis report (general mode)")
        self.logger.info("="*60)
        
        try:
            available_files = self.scan_available_files()
            
            print("\nGenerating cover and summary...")
            self.logger.info("[PROGRESS] Calling generate_cover()...")
            cover = self.generate_cover()
            self.logger.info(f"[PROGRESS] generate_cover() returned, type: {type(cover)}, length: {len(cover) if cover else 0}")
            
            report_parts = [cover]
            self.logger.info(f"[PROGRESS] report_parts initialized with cover, total sections to generate: {len(self.report_sections)}")
            
            for idx, section in enumerate(self.report_sections):
                print(f"\nGenerating section {idx+1}/{len(self.report_sections)}: {section['name']} (stage {section['stage']})...")
                self.logger.info(f"[PROGRESS] Generating section {idx+1}/{len(self.report_sections)}: {section['name']}")
                
                try:
                    section_content = self.generate_section(
                        section_name=section['name'],
                        section_stage=section['stage'],
                        available_files=available_files,
                        previous_context=report_parts[-1] if report_parts else ""
                    )
                    
                    self.logger.info(f"[PROGRESS] Section {idx+1}/{len(self.report_sections)} completed, content length: {len(section_content)}")
                    report_parts.append(section_content)
                    
                except Exception as e:
                    self.logger.error(f"[ERROR] Section {idx+1} generation failed: {e}", exc_info=True)
                    # Add fallback content
                    fallback_content = f"""## {section['name']}

Analysis of stage {section['stage']} encountered an error during report generation. Please refer to the original analysis result files.

Error: {str(e)}
"""
                    report_parts.append(fallback_content)
                    print(f"Warning: Section {idx+1} generation failed, using fallback content")
            
            print("\nGenerating discussion and conclusion...")
            self.logger.info("[PROGRESS] Generating discussion and conclusion...")
            discussion = self.generate_discussion(report_parts)
            report_parts.append(discussion)
            self.logger.info(f"[PROGRESS] Discussion completed, total parts: {len(report_parts)}")
            
            self.logger.info("[PROGRESS] Merging all sections...")
            full_markdown = "\n\n".join(report_parts)
            self.logger.info(f"[PROGRESS] Full markdown length: {len(full_markdown)} characters")
            
            report_dir = self.results_dir.parent / "04_reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            output_path = report_dir / output_filename
            print(f"\nGenerating Word document...")
            self.logger.info(f"[PROGRESS] Converting to Word: {output_path}")
            
            final_path = self.markdown_to_word(full_markdown, str(output_path))
            self.logger.info(f"[PROGRESS] Word document saved successfully: {final_path}")
            
            audit_result = self._audit_report(full_markdown)
            if not audit_result['passed']:
                self.logger.warning(f"Report audit found issues: {audit_result['issues']}")
                if audit_result['blocking']:
                    self.logger.error("Blocking issues found, report may need regeneration")
            
            print("\n" + "="*60)
            print(f"Report generation completed!")
            print(f"File location: {final_path}")
            print(f"Number of report sections: {len(self.report_sections)}")
            if audit_result['issues']:
                print(f"Audit warnings: {len(audit_result['issues'])}")
            print("="*60)
            
            return final_path
            
        except KeyboardInterrupt:
            self.logger.warning("Report generation interrupted by user (Ctrl+C)")
            print("\n⚠️  Report generation interrupted by user")
            raise
            
        except Exception as e:
            self.logger.error(f"Critical error in report generation: {e}", exc_info=True)
            print(f"\n❌ Critical error in report generation: {e}")
            raise


def generate_analysis_report(protocol_path: str, results_dir: str, config: Dict) -> str:
    """
    Convenience function: Generate analysis report
    
    Args:
        protocol_path: Research protocol path
        results_dir: Analysis results directory (workspace/analysis_xxx/03_results)
        config: System configuration
        
    Returns:
        Generated report path
    """
    generator = ReportGenerator(
        protocol_path=protocol_path,
        results_dir=results_dir,
        config=config
    )
    
    return generator.generate_report()


def main():
    import argparse
    import sys
    from pathlib import Path
    
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    
    parser = argparse.ArgumentParser(description='Generate statistical analysis report')
    parser.add_argument('--protocol', type=str, required=True,
                       help='Research protocol file path')
    parser.add_argument('--config', type=str, default='config.json',
                       help='Configuration file path')
    parser.add_argument('--output-dir', type=str, required=True,
                       help='Analysis results directory')
    
    args = parser.parse_args()
    
    protocol_path = Path(args.protocol)
    if not protocol_path.exists():
        print(f"Research protocol file does not exist: {args.protocol}")
        sys.exit(1)
    
    config = {}
    config_path = Path(args.config)
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    
    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        print(f"Output directory does not exist: {args.output_dir}")
        sys.exit(1)
    
    try:
        print("\n" + "="*60)
        print("Statistical Analysis Report Generator")
        print("="*60)
        print(f"Research protocol: {args.protocol}")
        print(f"Output directory: {args.output_dir}")
        print(f"Configuration file: {args.config}")
        print("="*60)
        
        report_path = generate_analysis_report(
            protocol_path=str(protocol_path),
            results_dir=str(output_dir),
            config=config
        )
        
        print("\nReport generation successful!")
        print(f"Location: {report_path}")
        
    except Exception as e:
        print(f"\nReport generation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
