#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cross-Sectional Study Design and Analysis Agent (AgenMed_CCS) API server"""

import json
import logging
import os
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from logging.handlers import RotatingFileHandler

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.orchestrator import AnalysisOrchestrator


BASE_DIR = Path(__file__).resolve().parent.parent.parent

logger = logging.getLogger("api_server")
logger.setLevel(logging.INFO)

if not logger.handlers:
    workspace_dir = BASE_DIR / 'workspace'
    workspace_dir.mkdir(parents=True, exist_ok=True)
    log_file = workspace_dir / f"api_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = RotatingFileHandler(str(log_file), maxBytes=2_000_000, backupCount=3, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)


app = Flask(__name__)
CORS(app)

analysis_status = {}

current_workspace = None


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'active_tasks': len([s for s in analysis_status.values() if s['status'] in ['started', 'running']])
    })


@app.route('/api/debug/tasks', methods=['GET'])
def debug_tasks():
    """Debug: View all task status"""
    return jsonify({
        'total_tasks': len(analysis_status),
        'tasks': {
            k: {
                'status': v['status'],
                'current_step': v.get('current_step', 'unknown')
            }
            for k, v in analysis_status.items()
        }
    })


@app.route('/api/upload', methods=['POST'])
def upload_files():
    """Upload files to the unified workspace"""
    try:
        if 'research' not in request.files or 'data' not in request.files:
            return jsonify({'error': 'Missing required files'}), 400
        
        research_file = request.files['research']
        data_file = request.files['data']
        
        if research_file.filename == '' or data_file.filename == '':
            return jsonify({'error': 'File name is empty'}), 400
        
        session_id = uuid.uuid4().hex[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        workspace_dir = BASE_DIR / "workspace" / f"analysis_{timestamp}_{session_id}"
        upload_dir = workspace_dir / "01_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        research_ext = Path(research_file.filename).suffix.lower()
        research_filename = f"protocol{research_ext}"
        data_filename = f"data.csv"
        
        research_path = upload_dir / research_filename
        data_path = upload_dir / data_filename
        
        research_file.save(str(research_path))
        data_file.save(str(data_path))
        
        logger.info(f"File uploaded successfully to the workspace: {workspace_dir.name}")
        logger.info(f"  - Research protocol: {research_path.name}")
        logger.info(f"  - Data file: {data_path.name}")
        
        global current_workspace
        current_workspace = {
            'workspace_dir': str(workspace_dir),
            'session_id': session_id,
            'research_path': str(research_path),
            'data_path': str(data_path),
            'timestamp': timestamp
        }
        
        return jsonify({
            'message': 'File uploaded successfully',
            'workspace_dir': str(workspace_dir),
            'session_id': session_id,
            'research_path': str(research_path),
            'data_path': str(data_path)
        })
    
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        return jsonify({'error': f'File upload failed: {str(e)}'}), 500


def find_analysis_files():
    """Smartly find analysis file paths (support new workspace)"""
    if current_workspace:
        research_path = Path(current_workspace['research_path'])
        data_path = Path(current_workspace['data_path'])
        if research_path.exists() and data_path.exists():
            return str(research_path), str(data_path)
    
    uploads_dir = BASE_DIR / 'uploads'
    data_path = uploads_dir / 'data.csv'
    
    research_path = None
    for ext in ['.md', '.docx', '.doc', '.txt']:
        candidate = uploads_dir / f'protocol{ext}'
        if candidate.exists():
            research_path = candidate
            break
    
    if research_path and data_path.exists():
        return str(research_path), str(data_path)
    
    default_research = BASE_DIR / 'protocol.md'
    default_data = BASE_DIR / 'data.csv'
    
    return str(default_research), str(default_data)


@app.route('/api/analyze', methods=['POST'])
def start_analysis():
    """Start analysis"""
    try:
        data = request.json if request.json else {}
        document_path = data.get('document_path')
        data_path = data.get('data_path')
        
        if not document_path or not data_path:
            document_path, data_path = find_analysis_files()
        
        config_path = data.get('config_path', 'config.json')

        if not Path(document_path).exists():
            return jsonify({'error': f'Research protocol document does not exist: {document_path}'}), 400
        
        if not Path(data_path).exists():
            return jsonify({'error': f'Data file does not exist: {data_path}'}), 400
        
        if not Path(config_path).exists():
            return jsonify({'error': f'Configuration file does not exist: {config_path}'}), 400
        
        task_id = str(uuid.uuid4())
        
        log_file = None
        
        analysis_status[task_id] = {
            'status': 'started',
            'message': 'Task created',
            'current_step': 'Initialization',
            'progress': 0,
            'start_time': datetime.now().isoformat(),
            'log_file': str(log_file),
            'result': None
        }
        
        thread = threading.Thread(
            target=_run_analysis_task,
            args=(task_id, document_path, data_path, config_path)
        )
        thread.daemon = True
        thread.start()
        
        logger.info(f"Analysis task started: {task_id}")
        
        return jsonify({
            'task_id': task_id,
            'message': 'Analysis task started'
        })
    
    except Exception as e:
        logger.error(f"Analysis task failed: {e}")
        return jsonify({'error': f'Analysis task failed: {str(e)}'}), 500


def _run_analysis_task(task_id: str, document_path: str, data_path: str, config_path: str):
    """Run analysis task in the background thread"""
    try:
        analysis_status[task_id]['status'] = 'running'
        analysis_status[task_id]['current_step'] = 'Initialization'
        
        session_id = current_workspace.get('session_id') if current_workspace else None
        
        orchestrator = AnalysisOrchestrator(config_path=config_path, session_id=session_id)
        
        if hasattr(orchestrator, 'log_file'):
            analysis_status[task_id]['log_file'] = orchestrator.log_file
            logger.info(f"Task {task_id} log file: {orchestrator.log_file}")
        else:
            logger.warning(f"Task {task_id} cannot get log file path")
        
        analysis_status[task_id]['current_step'] = 'Parsing document'
        analysis_status[task_id]['progress'] = 10
        
        def update_progress(progress, current_step):
            analysis_status[task_id]['progress'] = progress
            analysis_status[task_id]['current_step'] = current_step
        
        result = orchestrator.run_analysis(
            document_path=document_path,
            data_path=data_path,
            progress_callback=update_progress
        )
        
        if result.get('status') in ['analysis_completed', 'analysis_partial']:
            analysis_status[task_id]['status'] = result.get('status')
            analysis_status[task_id]['message'] = 'Analysis execution completed'
            analysis_status[task_id]['progress'] = 90
            analysis_status[task_id]['current_step'] = 'Post-processing: cleanup and report generation'
            analysis_status[task_id]['result'] = result
            
            try:
                logger.info(f"Task {task_id} starting post-processing in main thread...")
                post_result = orchestrator.postprocess()
                logger.info(f"Task {task_id} postprocess() returned successfully")
                analysis_status[task_id]['status'] = 'completed'
                analysis_status[task_id]['message'] = 'All tasks completed'
                analysis_status[task_id]['progress'] = 100
                analysis_status[task_id]['current_step'] = 'Completed'
                if 'result' in analysis_status[task_id]:
                    analysis_status[task_id]['result'].update(post_result)
                analysis_status[task_id]['end_time'] = datetime.now().isoformat()
                logger.info(f"Task {task_id} post-processing completed")
            except Exception as e:
                logger.error(f"Task {task_id} post-processing failed: {e}", exc_info=True)
                import traceback
                logger.error(f"Task {task_id} post-processing traceback: {traceback.format_exc()}")
                analysis_status[task_id]['status'] = 'postprocess_failed'
                analysis_status[task_id]['message'] = f'Post-processing failed: {str(e)}'
                analysis_status[task_id]['end_time'] = datetime.now().isoformat()
        elif result['success']:
            analysis_status[task_id]['status'] = 'completed'
            analysis_status[task_id]['message'] = 'Analysis completed'
            analysis_status[task_id]['progress'] = 100
            analysis_status[task_id]['result'] = result
            analysis_status[task_id]['end_time'] = datetime.now().isoformat()
        else:
            analysis_status[task_id]['status'] = 'failed'
            analysis_status[task_id]['message'] = f"Analysis failed: {result.get('error', 'Unknown error')}"
            analysis_status[task_id]['progress'] = -1
            analysis_status[task_id]['result'] = result
            analysis_status[task_id]['end_time'] = datetime.now().isoformat()
        
        logger.info(f"Task {task_id} analysis execution completed, status: {analysis_status[task_id]['status']}")
    
    except Exception as e:
        logger.error(f"Task {task_id} execution exception: {e}")
        analysis_status[task_id]['status'] = 'failed'
        analysis_status[task_id]['message'] = f'Task execution exception: {str(e)}'
        analysis_status[task_id]['progress'] = -1
        analysis_status[task_id]['end_time'] = datetime.now().isoformat()


@app.route('/api/status/<task_id>', methods=['GET'])
def get_status(task_id):
    """Get task status"""
    if task_id not in analysis_status:
        return jsonify({'error': 'Task does not exist'}), 404
    
    return jsonify(analysis_status[task_id])


@app.route('/api/logs/<task_id>', methods=['GET'])
def get_logs(task_id):
    """Get task logs"""
    if task_id not in analysis_status:
        return jsonify({'error': 'Task does not exist'}), 404
    
    log_file = analysis_status[task_id].get('log_file')
    if not log_file or not Path(log_file).exists():
        workspace_dir = BASE_DIR / 'workspace'
        if workspace_dir.exists():
            log_files = sorted(workspace_dir.rglob('analysis_*.log'), key=lambda p: p.stat().st_mtime, reverse=True)
            if log_files:
                log_file = str(log_files[0])
        else:
            return jsonify({'logs': [], 'message': 'Log file does not exist'})
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = f.readlines()
        
        parsed_logs = []
        for line in logs:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split(' - ', 2)
            if len(parts) >= 3:
                timestamp = parts[0]
                level = parts[1]
                message = parts[2]
                parsed_logs.append({
                    'timestamp': timestamp,
                    'level': level,
                    'message': message,
                    'raw': line
                })
            else:
                parsed_logs.append({
                    'timestamp': '',
                    'level': 'INFO',
                    'message': line,
                    'raw': line
                })
        
        return jsonify({
            'logs': parsed_logs,
            'log_file': log_file,
            'total_lines': len(parsed_logs)
        })
    
    except Exception as e:
        logger.error(f"Read logs failed: {e}")
        return jsonify({'error': f'Read logs failed: {str(e)}'}), 500


@app.route('/api/logs/latest', methods=['GET'])
def get_latest_logs():
    """Get latest logs"""
    try:
        workspace_dir = BASE_DIR / 'workspace'
        log_files = []
        if workspace_dir.exists():
            log_files = sorted(workspace_dir.rglob('analysis_*.log'), key=lambda p: p.stat().st_mtime, reverse=True)
        if not log_files:
            return jsonify({'logs': [], 'message': 'No log files'})
        
        latest_log = log_files[0]
        with open(latest_log, 'r', encoding='utf-8') as f:
            logs = f.readlines()
        
        parsed_logs = []
        for line in logs:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split(' - ', 2)
            if len(parts) >= 3:
                parsed_logs.append({
                    'timestamp': parts[0],
                    'level': parts[1],
                    'message': parts[2],
                    'raw': line
                })
            else:
                parsed_logs.append({
                    'timestamp': '',
                    'level': 'INFO',
                    'message': line,
                    'raw': line
                })
        
        return jsonify({
            'logs': parsed_logs,
            'log_file': str(latest_log),
            'total_lines': len(parsed_logs)
        })
    
    except Exception as e:
        logger.error(f"Read latest logs failed: {e}")
        return jsonify({'error': f'Read latest logs failed: {str(e)}'}), 500


def _build_file_tree(directory: Path, base_dir: Path) -> dict:
    """Recursive build file tree structure"""
    tree = {'files': [], 'folders': {}}
    
    if not directory.exists():
        return tree
    
    try:
        items = sorted(directory.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        
        for item in items:
            if item.name.startswith('.'):
                continue
            
            if item.is_file():
                try:
                    tree['files'].append({
                        'name': item.name,
                        'size': item.stat().st_size,
                        'modified': datetime.fromtimestamp(item.stat().st_mtime).isoformat()
                    })
                except (OSError, PermissionError):
                    continue
            elif item.is_dir():
                sub_tree = _build_file_tree(item, base_dir)
                if sub_tree['files'] or sub_tree['folders']:
                    tree['folders'][item.name] = sub_tree
    except (OSError, PermissionError) as e:
        logger.warning(f"Cannot read directory {directory}: {e}")
    
    return tree


@app.route('/api/files', methods=['GET'])
def list_files():
    """List output files (return tree structure)"""
    try:
        file_tree = {}
        
        workspace_dir = BASE_DIR / 'workspace'
        if workspace_dir.exists():
            file_tree['workspace'] = _build_file_tree(workspace_dir, BASE_DIR)
        
        output_dir = BASE_DIR / 'output'
        if output_dir.exists():
            file_tree['output'] = _build_file_tree(output_dir, BASE_DIR)
        
        r_scripts_dir = BASE_DIR / 'r_scripts'
        if r_scripts_dir.exists():
            file_tree['r_scripts'] = _build_file_tree(r_scripts_dir, BASE_DIR)
        
        return jsonify(file_tree)
    
    except Exception as e:
        logger.error(f"List files failed: {e}")
        return jsonify({'error': f'List files failed: {str(e)}'}), 500


@app.route('/api/file/<path:filepath>', methods=['GET'])
def get_file(filepath):
    """Get file content (for frontend display, support workspace/、output/、r_scripts/ directories)"""
    try:
        logger.info(f"Requested file path: {filepath}")
        path_parts = filepath.split('/', 1)
        
        if len(path_parts) >= 1:
            root_dir_name = path_parts[0]
            if root_dir_name in ['workspace', 'output', 'r_scripts', 'scripts', '完整']:
                full_path = BASE_DIR / filepath
            else:
                workspace_path = BASE_DIR / 'workspace' / filepath
                if workspace_path.exists():
                    full_path = workspace_path
                else:
                    full_path = BASE_DIR / 'output' / filepath
        else:
            full_path = BASE_DIR / 'workspace' / filepath
        
        full_path = full_path.resolve()
        base_dir_resolved = BASE_DIR.resolve()
        
        logger.info(f"Resolved full path: {full_path}")
        logger.info(f"BASE_DIR resolved: {base_dir_resolved}")
        logger.info(f"Path exists: {full_path.exists()}")
        logger.info(f"Path is file: {full_path.is_file() if full_path.exists() else 'N/A'}")
        
        if not str(full_path).startswith(str(base_dir_resolved)):
            logger.warning(f"Path security check failed: {full_path} not under {base_dir_resolved}")
            return jsonify({'error': 'Invalid path'}), 403
        
        if not full_path.exists() or not full_path.is_file():
            logger.warning(f"File not found: {full_path}")
            return jsonify({'error': 'File does not exist'}), 404
        
        extension = full_path.suffix.lower().lstrip('.')
        
        image_extensions = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'svg']
        pdf_extensions = ['pdf']
        
        if extension in image_extensions:
            import base64
            with open(full_path, 'rb') as f:
                content_base64 = base64.b64encode(f.read()).decode('utf-8')
            return jsonify({
                'content': content_base64,
                'type': 'image',
                'extension': extension,
                'name': full_path.name,
                'size': full_path.stat().st_size
            })
        elif extension in pdf_extensions:
            return jsonify({
                'content': None,
                'type': 'pdf',
                'extension': extension,
                'name': full_path.name,
                'size': full_path.stat().st_size,
                'message': 'PDF file cannot be previewed in the browser'
            })
        else:
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return jsonify({
                    'content': content,
                    'type': 'text',
                    'extension': extension,
                    'name': full_path.name,
                    'size': len(content)
                })
            except UnicodeDecodeError:
                return jsonify({
                    'content': None,
                    'type': 'binary',
                    'extension': extension,
                    'name': full_path.name,
                    'size': full_path.stat().st_size,
                    'message': 'This is a binary file, cannot be previewed in the browser'
                })
    
    except Exception as e:
        logger.error(f"Read file failed: {e}")
        return jsonify({'error': f'Read file failed: {str(e)}'}), 500


@app.route('/api/download/report', methods=['GET'])
def download_report():
    """Download the latest generated statistical analysis report (Word document)"""
    try:
        task_id = request.args.get('task_id')
        if task_id and task_id in analysis_status:
            result = analysis_status[task_id].get('result')
            if result and result.get('report_path'):
                report_path = Path(result['report_path'])
                if report_path.exists():
                    logger.info(f"Download report from task {task_id}: {report_path}")
                    return send_file(str(report_path), as_attachment=True, download_name=report_path.name)
        
        workspace_dir = BASE_DIR / 'workspace'
        report_files = list(workspace_dir.rglob('statistical_analysis_report.docx'))
        
        if not report_files:
            output_dir = BASE_DIR / 'output'
            report_files = list(output_dir.glob('*/statistical_analysis_report.docx'))
        
        if not report_files:
            return jsonify({'error': 'Statistical analysis report not found, please run the complete analysis process first'}), 404
        
        latest_report = max(report_files, key=lambda p: p.stat().st_mtime)
        
        logger.info(f"Download report: {latest_report}")
        return send_file(str(latest_report), as_attachment=True, download_name='statistical_analysis_report.docx')
    
    except Exception as e:
        logger.error(f"Download report failed: {e}")
        return jsonify({'error': f'Download report failed: {str(e)}'}), 500


@app.route('/api/download/<path:filepath>', methods=['GET'])
def download_file(filepath):
    """Download file (support output/、r_scripts/、scripts/ directories)"""
    try:
        path_parts = filepath.split('/', 1)
        
        if len(path_parts) == 2:
            root_dir_name, relative_path = path_parts
            if root_dir_name in ['output', 'r_scripts', 'scripts']:
                full_path = BASE_DIR / root_dir_name / relative_path
            else:
                full_path = BASE_DIR / 'output' / filepath
        else:
            full_path = BASE_DIR / 'output' / filepath
        
        full_path = full_path.resolve()
        if not str(full_path).startswith(str(BASE_DIR.resolve())):
            return jsonify({'error': 'Invalid path'}), 403
        
        if not full_path.exists() or not full_path.is_file():
            return jsonify({'error': 'File does not exist'}), 404
        
        return send_file(str(full_path), as_attachment=True)
    
    except Exception as e:
        logger.error(f"Download file failed: {e}")
        return jsonify({'error': f'Download file failed: {str(e)}'}), 500


def run_server(host='0.0.0.0', port=8001):
    """Start API server"""
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    logger.info(f"API server started: http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    run_server()



