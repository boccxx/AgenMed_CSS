"""
Double-click this file to start the system
"""

import os
import sys
import time
import subprocess
import webbrowser
from pathlib import Path

def main():
    script_dir = Path(__file__).parent.absolute()
    os.chdir(script_dir)
    
    print("=" * 50)
    print("Cross-Sectional Study Design and Analysis Agent (AgenMed_CSS)")
    print("  Starting...")
    print("=" * 50)
    print()

    if sys.version_info < (3, 8):
        print("Error: Python 3.8 or higher is required")
        print(f"Current version: Python {sys.version_info.major}.{sys.version_info.minor}")
        input("Press Enter to exit...")
        sys.exit(1)
    
    print("Checking dependencies...")
    missing_deps = []
    required_packages = ['flask', 'flask_cors', 'openai', 'pandas', 'chardet']
    
    for pkg in required_packages:
        try:
            __import__(pkg.replace('-', '_'))
        except ImportError:
            missing_deps.append(pkg)
    
    if missing_deps:
        print(f"Missing dependencies: {', '.join(missing_deps)}")
        print("Installing dependencies...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print("Dependency installation failed:")
            print(result.stderr)
            input("Press Enter to exit...")
            sys.exit(1)
        print("Dependencies installed successfully")
    else:
        print("Dependency check passed")

    if not os.path.exists("config.json"):
        if os.path.exists("config.json.example"):
            import shutil
            shutil.copy("config.json.example", "config.json")
            print("Created configuration file config.json")
            print("Please edit config.json and fill in your API key")
            print()
    
    print("Starting API server...")
    print()
    
    server_process = subprocess.Popen(
        [sys.executable, "-m", "src.api.api_server"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    print("Waiting for server to be ready...")
    print("Server output:")
    print("-" * 50)
    
    max_wait = 30
    server_ready = False
    
    for i in range(max_wait):
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:8001/api/health", timeout=1)
            print("-" * 50)
            print("API server is ready")
            server_ready = True
            break
        except:
            pass
        
        if server_process.poll() is not None:
            stdout, _ = server_process.communicate()
            print(stdout)
            print("-" * 50)
            print("Server process exited unexpectedly")
            print()
            print("Possible causes:")
            print("   1. Dependencies not installed: pip install -r requirements.txt")
            print("   2. Configuration file error: check config.json")
            print("   3. Port already in use: check port 8001")
            print()
            input("Press Enter to exit...")
            sys.exit(1)
        
        time.sleep(1)
    
    if not server_ready:
        print("-" * 50)
        print("Server startup timeout")
        print()
        try:
            server_process.kill()
            stdout, _ = server_process.communicate(timeout=2)
            if stdout:
                print("Server output:")
                print(stdout)
        except:
            pass
        print()
        print("Please try:")
        print("   1. Run manually: python -m src.api.api_server")
        print("   2. Check detailed error messages")
        print()
        input("Press Enter to exit...")
        sys.exit(1)
    
    print("Opening frontend interface...")
    html_path = script_dir / "frontend" / "Cross-Sectional Study Design and Analysis Agent (AgenMed_CSS).html"
    webbrowser.open(f"file://{html_path}")
    
    print()
    print("=" * 50)
    print("Startup complete!")
    print()
    print("Service information:")
    print("   - API server: http://localhost:8001")
    print("   - Frontend interface: opened in browser")
    print()
    print("Usage instructions:")
    print("   1. Upload research protocol document and data file")
    print("   2. Click the 'Start Statistical Analysis' button")
    print("   3. Wait for analysis to complete and view results")
    print()
    print("Please keep this window open")
    print("   Closing the window will stop the server")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 50)
    
    try:
        # Keep running
        server_process.wait()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        print("Server stopped")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nStartup failed: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)

