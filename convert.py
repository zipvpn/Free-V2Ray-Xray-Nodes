import os
import time
import requests
import tarfile
import subprocess
import threading
import socket
import concurrent.futures
from http.server import SimpleHTTPRequestHandler, HTTPServer

# ================= Configuration Area =================
# Define the path to the source subscription file
SOURCE_FILE = 'free_v2ray_xray_nodes.txt'

# Define output files and their corresponding Subconverter target parameters
OUTPUT_CONFIGS = {
    'free_clash_nodes.yaml': 'clash',
    'free_quantumultx_nodes.txt': 'quanx',
    'free_surge_nodes.conf': 'surge&ver=4',
    'free_loon_nodes.conf': 'loon',
    'free_surfboard_nodes.conf': 'surfboard',
    'free_singbox_nodes.json': 'singbox',
}
# ===========================================

def get_latest_download_url():
    # Retrieve the download URL for the latest Subconverter Linux x64 release
    api_url = "https://api.github.com/repos/tindy2013/subconverter/releases/latest"
    try:
        print("Checking for the latest Subconverter version...")
        resp = requests.get(api_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        for asset in data.get('assets', []):
            name = asset['name'].lower()
            if 'linux64' in name and name.endswith('.tar.gz'):
                print(f"Found version: {data['tag_name']}")
                return asset['browser_download_url']
        raise Exception("No linux64.tar.gz asset found")
    except Exception as e:
        print(f"Failed to retrieve download URL: {e}")
        # Fallback to a fixed version for reliability
        return "https://github.com/tindy2013/subconverter/releases/download/v0.7.2/subconverter_linux64.tar.gz"

def download_and_extract():
    # Download and extract the Subconverter binary
    if os.path.exists("subconverter/subconverter"):
        print("Subconverter already exists, skipping download")
        return
  
    url = get_latest_download_url()
    print(f"Starting download of engine: {url}")
  
    try:
        resp = requests.get(url, stream=True, timeout=300)
        with open("sub.tar.gz", "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
      
        with tarfile.open("sub.tar.gz", "r:gz") as tar:
            tar.extractall()
      
        if os.path.exists("subconverter/subconverter"):
            os.chmod("subconverter/subconverter", 0o755)
        else:
            raise Exception("Subconverter executable not found after extraction")
          
    except Exception as e:
        print(f"Download or extraction failed: {e}")
        raise

def download_resource(url, save_path):
    # Download a remote resource file for local use
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(resp.text)
        print(f"Resource downloaded successfully: {save_path}")
        return True
    except Exception as e:
        print(f"Resource download failed {url}: {e}")
        return False

def start_local_file_server():
    # Start a local HTTP server to serve source and rule files
    try:
        server = HTTPServer(('127.0.0.1', 8000), SimpleHTTPRequestHandler)
        server.serve_forever()
    except Exception as e:
        print(f"Local file server failed to start (port may be in use): {e}")

def wait_for_port(port, timeout=10):
    # Wait for the specified port to become ready
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.5):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.5)
    return False

def convert_task(task_args):
    # Execute a single subscription conversion task
    filename, target_config, source_url, base_api = task_args
  
    params = {
        "url": source_url,
        "target": target_config.split('&')[0],
        "emoji": "false",  # Disabled to remove flag emojis and keep output clean
        "list": "false",
        "tfo": "false",
        "scv": "false",
        "fdn": "false",
        "sort": "false"
    }
  
    if '&' in target_config:
        for part in target_config.split('&')[1:]:
            if '=' in part:
                k, v = part.split('=', 1)
                params[k] = v
                
    try:
        resp = requests.get(base_api, params=params, timeout=60)
        if resp.status_code == 200 and len(resp.text) > 10:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(resp.text)
            print(f"{filename} generated successfully")
            return True
        else:
            print(f"{filename} generation failed - HTTP Code: {resp.status_code}")
            return False
    except Exception as e:
        print(f"Error occurred for {filename}: {e}")
        return False

def main():
    sub_process = None
  
    try:
        # Prepare Subconverter runtime environment
        download_and_extract()
       
        # Start local file server for Subconverter to access source file
        # (No rule file is downloaded or served — pure node output with default English templates)
        fs_thread = threading.Thread(target=start_local_file_server, daemon=True)
        fs_thread.start()
       
        # Start Subconverter main process
        print("Starting conversion engine...")
        if not os.path.exists("./subconverter/subconverter"):
            raise FileNotFoundError("Cannot find ./subconverter/subconverter - check download step")
        sub_process = subprocess.Popen(
            ["./subconverter/subconverter"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if wait_for_port(25500, timeout=10):
            print("Conversion engine started successfully (Port 25500 is ready)")
        else:
            raise TimeoutError("Subconverter startup timed out - port 25500 not responding")
           
        # Prepare conversion parameters and execute tasks concurrently
        source_url = f"http://127.0.0.1:8000/{SOURCE_FILE}"
        base_api = "http://127.0.0.1:25500/sub"
      
        tasks = []
        for filename, target_config in OUTPUT_CONFIGS.items():
            tasks.append((filename, target_config, source_url, base_api))
           
        print(f"Starting concurrent conversion of {len(tasks)} tasks...")
        start_time = time.time()
      
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(convert_task, tasks))
          
        elapsed = time.time() - start_time
        success_count = results.count(True)
        print(f"All tasks completed in {elapsed:.2f}s - Success: {success_count}/{len(tasks)}")
      
        if success_count == 0:
            raise Exception("All conversion tasks failed")
           
    except Exception as e:
        print(f"Error in main process: {e}")
        exit(1)
    finally:
        # Terminate Subconverter subprocess
        if sub_process:
            try:
                sub_process.kill()
                sub_process.wait()
            except:
                pass
      
        # Clean up temporary files
        if os.path.exists("sub.tar.gz"):
            os.remove("sub.tar.gz")

if __name__ == "__main__":
    main()
