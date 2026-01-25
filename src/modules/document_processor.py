#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Document processing module - complete research plan parsing and sub prompt generation functionality"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime
import chardet


class DocumentProcessor:
    """Document processor, responsible for parsing research plan and generating sub prompts"""
    
    def __init__(self, temp_dir: str, meta_prompt_path: str):
        """
        Initialize document processor
        
        Args:
            temp_dir: Sub prompt save directory
            meta_prompt_path: Meta prompt file path
        """
        self.logger = logging.getLogger(__name__)
        self.temp_dir = Path(temp_dir)
        self.meta_prompt_path = Path(meta_prompt_path)

        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def _read_document_with_encoding(self, file_path: str) -> str:
        """
        Smartly read document, automatically detect encoding and support multiple formats    
        
        Args:
            file_path: Document path
            
        Returns:
            str: Document content
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Document file not found: {file_path}")
        
        ext = file_path.suffix.lower()
        
        if ext in ['.doc', '.docx']:
            try:
                import docx
                doc = docx.Document(str(file_path))
                content = '\n'.join([para.text for para in doc.paragraphs])
                self.logger.info(f"Successfully read Word document: {file_path.name}")
                return content
            except ImportError:
                self.logger.warning("python-docx not installed, try reading as text file")
            except Exception as e:
                self.logger.error(f"Failed to read Word document: {e}")
                raise ValueError(f"Failed to read Word document {file_path.name}, please ensure file format is correct or convert to .md/.txt format")
        
        with open(file_path, 'rb') as f:
            raw_data = f.read()
        
        detected = chardet.detect(raw_data)
        encoding = detected.get('encoding', 'utf-8')
        confidence = detected.get('confidence', 0)
        
        self.logger.info(f"Detected file encoding: {encoding} (confidence: {confidence:.2f})")
        
        encodings_to_try = [encoding, 'utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']
        
        for enc in encodings_to_try:
            if not enc:
                continue
            try:
                content = raw_data.decode(enc)
                self.logger.info(f"Successfully read document with {enc} encoding: {file_path.name}")
                return content
            except (UnicodeDecodeError, LookupError):
                continue
        
        try:
            content = raw_data.decode('utf-8', errors='ignore')
            self.logger.warning(f"Ignored some undecodable characters when reading with UTF-8: {file_path.name}")
            return content
        except Exception as e:
            raise ValueError(f"Failed to read document {file_path.name}, please check file encoding or format")
    
    def process(
        self,
        document_path: str,
        data_path: str,
        data_profiler,
        llm_client
    ) -> List[Dict]:
        """
        Parse research plan document, generate sub prompts
        
        Args:
            document_path: Research plan document path
            data_path: Data file path
            data_profiler: Data profiler instance
            llm_client: LLM client instance
            
        Returns:
            Sub prompts list, each element contains section, stage_name, title, file_path information
        """
        self.logger.info("Starting to parse research plan document...")
        
        with open(self.meta_prompt_path, 'r', encoding='utf-8') as f:
            meta_prompt = f.read()
        
        research_document = self._read_document_with_encoding(document_path)
        
        data_info = ""
        weight_detection_info = ""
        
        if data_path and Path(data_path).exists():
            data_profile = data_profiler.get_profile(data_path)
            data_info = data_profile.get('info_text', '')
            
            weight_detection = data_profiler.detect_weight_variable(data_path)
            if weight_detection['usable_weight']:
                weight_detection_info = f"""
Weight Variable Detection (Pre-validated):
- Detected variable: {weight_detection['weight_variable']}
- Status: USABLE (n_unique={weight_detection['weight_summary']['n_unique']}, range=[{weight_detection['weight_summary']['min']:.2f}, {weight_detection['weight_summary']['max']:.2f}])
- All subsequent stages MUST use this weight variable
- DO NOT create placeholder weight=1
"""
            else:
                weight_detection_info = f"""
Weight Variable Detection (Pre-validated):
- Detected variable: {weight_detection['weight_variable'] or 'None'}
- Status: NOT USABLE ({weight_detection['detection_reason']})
- Subsequent stages MAY create placeholder weight=1 with weight_is_placeholder=true
- Analysis must be downgraded to sample_based inference
"""
        
        data_filename = Path(data_path).name if data_path else "data.csv"
        
        enhanced_prompt = f"""
Research plan document:
{research_document}

Actual data variable information (must strictly use these variables):
{data_info}

{weight_detection_info}

Data file name: {data_filename}

Important restrictions:
- Only use variables that exist in the actual data file
- Do not reference variables that do not exist in the data file
- If the variable names in the research plan do not match the actual variable names, use the variable names in the actual data

⚠️ CRITICAL Requirements:
1. Generate ALL subsections in Chapter 7 (7.1-7.8, do not skip sensitivity analysis)
2. Keep sub-prompts CONCISE (150-300 lines): bullet points for methods/variables/outputs, minimal code (≤5 lines when needed)
3. Use data summary statistics (n_unique, range, etc.) to validate protocol assumptions

Please generate sub prompts based on the statistical methods in Chapter 7 of the research plan.
"""
  
        self.logger.info("Calling LLM to parse research plan...")
        response = llm_client.call(
            system_prompt=meta_prompt,
            user_prompt=enhanced_prompt
        )
        
        debug_file = self.temp_dir / f"llm_response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(response)
        self.logger.info(f"LLM response saved to: {debug_file}")
        self.logger.info(f"LLM response length: {len(response)} characters")
        self.logger.info(f"LLM response first 500 characters: {response[:500]}")
        
        sub_prompts = self._extract_sub_prompts(response)
        self.logger.info(f"Extracted {len(sub_prompts)} sub prompts")
        
        for i, sub_prompt in enumerate(sub_prompts):
            section_num = sub_prompt['section']
            stage_name = sub_prompt['stage_name']
            
            if section_num == "unknown":
                section_num = f"7.{i+1}"
            
            filename = f"prompt_{section_num}_{stage_name}.md"
            filepath = self.temp_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(sub_prompt['content'])
            
            sub_prompt['file_path'] = str(filepath)
            sub_prompt['section'] = section_num
            
            self.logger.info(f"Saved sub prompt: {filename} (section: {section_num})")
        
        filtered_prompts = []
        non_analysis_keywords = [
            'reporting', 'report', 'guideline', 'checklist', 
            'strobe', 'consort', 'prisma', 'spirit',
            'reporting', 'report', 'guideline', 'checklist',
            'ethical', 'ethics', 'ethics', 
            'dissemination', 'dissemination', 'publication'
        ]
        
        for prompt in sub_prompts:
            stage_name = prompt.get('stage_name', '').lower()
            is_non_analysis = any(keyword in stage_name for keyword in non_analysis_keywords)
            
            if is_non_analysis:
                self.logger.info(f"Skipping non-analysis section: {prompt.get('section')} - {prompt.get('stage_name')}")
            else:
                filtered_prompts.append(prompt)
        
        if len(filtered_prompts) < len(sub_prompts):
            self.logger.info(f"After filtering, {len(filtered_prompts)}/{len(sub_prompts)} analysis sections remain")
        
        self.logger.info(f"Successfully generated {len(filtered_prompts)} sub prompt files")
        return filtered_prompts
    
    def _extract_sub_prompts(self, llm_response: str) -> List[Dict]:
        """
        Extract sub prompt information from LLM response
        
        Args:
            llm_response: Response text returned by LLM
            
        Returns:
            Sub prompt list
        """
        sub_prompts = []
        lines = llm_response.split('\n')
        current_prompt = None
        in_code_block = False
        
        prompt_header_pattern = re.compile(
            r'#+\s*prompt_(\d+\.\d+)_([A-Za-z0-9_\-]+)(?:\.[A-Za-z0-9]+)?',
            re.IGNORECASE
        )
        
        for line in lines:
            stripped = line.strip()
            
            if stripped.startswith('```'):
                in_code_block = not in_code_block
                if current_prompt:
                    current_prompt['content'] += line + '\n'
                continue
            
            header_match = prompt_header_pattern.match(stripped)
            stripped_lower = stripped.lower()
            if (stripped_lower.startswith('# statistical analysis task:') or
                stripped_lower.startswith('# prompt for:') or
                (stripped.startswith('##') and 'Prompt for:' in stripped) or
                header_match):
                
                if current_prompt:
                    sub_prompts.append(current_prompt)
                
                if header_match:
                    section = header_match.group(1)
                    stage_token = header_match.group(2)
                    stage_name = stage_token.lower()
                    title = f"SAP {section} - {stage_name}"
                    
                    current_prompt = {
                        'section': section,
                        'stage_name': stage_name,
                        'title': title,
                        'content': line + '\n'
                    }
                else:
                    # Extract title (case-insensitive matching)
                    if stripped_lower.startswith('# statistical analysis task:'):
                        title = stripped[len('# Statistical Analysis Task:'):].strip()
                    elif stripped_lower.startswith('# prompt for:'):
                        title = stripped[len('# Prompt for:'):].strip()
                    elif stripped.startswith('##') and 'Prompt for:' in stripped:
                        title = stripped.replace('## Prompt for:', '').strip()
                    else:
                        title = stripped.lstrip('#').strip()
                    
                    section_info = self._parse_section_title(title)
                    
                    current_prompt = {
                        'section': section_info['section'],
                        'stage_name': section_info['stage_name'],
                        'title': title,
                        'content': line + '\n'
                    }
            
            elif current_prompt:
                current_prompt['content'] += line + '\n'
        
        if current_prompt:
            sub_prompts.append(current_prompt)
        
        if not sub_prompts:
            self.logger.warning("Main extraction method did not find any sub prompts, trying fallback method...")
            sub_prompts = self._fallback_extract_prompts(llm_response)
            self.logger.info(f"Fallback method extracted {len(sub_prompts)} sub prompts")
        
        filtered_prompts = []
        for prompt in sub_prompts:
            lines = [ln for ln in prompt.get('content', '').splitlines() if ln.strip()]
            if len(lines) > 2:
                filtered_prompts.append(prompt)
        
        if not filtered_prompts:
            return sub_prompts
        
        dedup: Dict[Tuple[str, str], Dict] = {}
        for prompt in filtered_prompts:
            key = (
                prompt.get('section', 'unknown'),
                prompt.get('stage_name', 'unknown_stage')
            )
            current = dedup.get(key)
            if not current or len(prompt.get('content', '')) > len(current.get('content', '')):
                dedup[key] = prompt
        
        return list(dedup.values())
    
    def _parse_section_title(self, title: str) -> Dict:
        """
        Parse section title, extract section number and stage name
        
        Args:
            title: Section title
            
        Returns:
            Dictionary containing section and stage name
        """
        section_match = re.search(r'SAP\s+(\d+\.\d+)', title)
        if not section_match:
            section_match = re.search(r'(\d+\.\d+)', title)
        
        section = section_match.group(1) if section_match else "unknown"
        
        if ' - ' in title:
            stage_name = title.split(' - ')[1].strip()
        else:
            stage_name = title.strip()
        
        stage_name = re.sub(r'[#：]', '', stage_name).strip()
        
        return {
            'section': section,
            'stage_name': stage_name
        }
    
    def _fallback_extract_prompts(self, llm_response: str) -> List[Dict]:
        """
        Fallback method for sub prompt extraction (more intelligent parsing)
        
        Args:
            llm_response: LLM response text
            
        Returns:
            Sub prompt list
        """
        self.logger.info("Using fallback extraction method...")
        sections = []
        
        if '===' in llm_response:
            parts = llm_response.split('===')
        elif '---' in llm_response and llm_response.count('---') > 2:
            parts = llm_response.split('---')
        else:
            parts = re.split(r'\n#+\s+', llm_response)
        
        for i, part in enumerate(parts):
            part = part.strip()
            if len(part) < 50:
                continue
            
            section_match = re.search(r'(?:SAP\s+)?(\d+\.\d+)', part[:200])
            if section_match:
                section = section_match.group(1)
            else:
                section = f"7.{i+1}"
            
            stage_match = re.search(r'[：:]\s*([^\n]+)', part[:200])
            if stage_match:
                stage_name = stage_match.group(1).strip()[:50]
            else:
                stage_name = f"stage_{i+1}"
            
            sections.append({
                'section': section,
                'stage_name': stage_name,
                'title': f"SAP {section} - {stage_name}",
                'content': part
            })
        
        self.logger.info(f"Fallback method found {len(sections)} sections")
        
        if not sections and len(llm_response) > 100:
            self.logger.warning("All extraction methods failed, will use the entire response as a single prompt")
            sections = [{
                'section': '7.1',
                'stage_name': 'full_analysis',
                'title': 'SAP 7.1 - Full analysis',
                'content': llm_response
            }]
        
        return sections



